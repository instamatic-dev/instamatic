from __future__ import annotations

import multiprocessing as mp
import os
import queue
import uuid
from itertools import count
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, Any, Optional, Sequence

import numpy as np
from typing_extensions import Literal, TypeAlias

from instamatic._typing import AnyPath
from instamatic.experiments.scan_ed.detection import DiffHuntResults, ring_percentile_detection
from instamatic.formats import write_tiff

if TYPE_CHECKING:
    from instamatic.experiments.scan_ed.state import State

N_PROCESSORS = 4

CommandKind = Literal['CONFIGURE', 'INIT', 'PROCESS', 'WRITE', 'TERMINATE']
FeedbackKind = Literal['PROCESSING', 'PROCESSED', 'WRITTEN']

Command: TypeAlias = tuple[CommandKind, dict[str, Any]]
Feedback: TypeAlias = tuple[FeedbackKind, dict[str, Any]]


class DiffHuntDispatcher:
    """Proxy class: ask workers on other processes if image has diffraction"""

    def __init__(self, shape: tuple[int, int], dtype: np.dtype) -> None:
        self.shape: tuple[int, int] = shape
        self.dtype: np.dtype = np.dtype(dtype)
        self.command_queues: list[mp.Queue[Command]] = []
        self.feedback_queue: mp.Queue[Feedback] = mp.Queue()

        self._round_robin = count()
        self._workers: list[DiffHuntWorker] = []
        self._spawn_workers()

        self._buffer_name: str = ''
        self._shm: Optional[SharedMemory] = None
        self._frames: Optional[np.ndarray] = None

        self._n_frames: int = 0
        self._next_ptr: int = 0
        self._in_flight: set[int] = set()
        self._write_pending: set[int] = set()

        self.scan_finished: Event = Event()
        self.scan_processed: Event = Event()
        self.hits: Optional[np.ndarray] = None
        self.headers: list[Optional[dict]] = []

    def _spawn_workers(self) -> None:
        """Run once at the start of experiment to spawn eval processes."""
        for wid in range(N_PROCESSORS):
            w = DiffHuntWorker(wid, (q := mp.Queue()), self.feedback_queue, self.dtype)
            w.start()
            self.command_queues.append(q)
            self._workers.append(w)

    def emit(self, task: CommandKind, **kwargs) -> None:
        """Shorthand to create and put Command in next self.commands queue."""
        q = self.command_queues[next(self._round_robin) % N_PROCESSORS]
        q.put((task, kwargs))

    def emit_all(self, task: CommandKind, **kwargs) -> None:
        """Shorthand to create and put Command in ALL self.commands queues."""
        for q in self.command_queues:
            q.put((task, kwargs))

    def begin_scan(self, n_frames: int, name: Optional[str] = None) -> None:
        """Allocate a new shared buffer and reset all tracking for one scan."""
        self._buffer_name = name or uuid.uuid4().hex
        self._n_frames = int(n_frames)
        self._next_ptr = 0
        self._in_flight.clear()
        self._write_pending.clear()
        shape3 = (self._n_frames, self.shape[0], self.shape[1])
        size = int(np.prod(shape3) * self.dtype.itemsize)
        self._shm = SharedMemory(name=self._buffer_name, create=True, size=size)
        self._frames = np.ndarray(shape3, dtype=self.dtype, buffer=self._shm.buf)
        self.scan_finished.clear()
        self.scan_processed.clear()
        self.hits = np.zeros(self._n_frames, dtype=bool)
        self.headers = [None] * self._n_frames
        self.emit_all('INIT', buffer_name=self._buffer_name, buffer_shape=shape3)

    def end_scan(self) -> None:
        """Release shared memory for the active scan."""
        if self._shm is None:
            return
        try:
            self._shm.close()
            self._shm.unlink()
        finally:
            self._shm = None
            self._frames = None
            self._buffer_name = ''
            self._n_frames = 0
            self._next_ptr = 0
            self._in_flight.clear()
            self._write_pending.clear()
            self.hits = None
            self.headers = []

    def process(self, frame: np.ndarray, header: Optional[dict]) -> int:
        """Copy a frame into the shared buffer and enqueue processing."""
        if self._frames is None:
            raise RuntimeError('Call begin_scan() first.')
        if self._next_ptr >= self._n_frames:
            raise RuntimeError('Buffer overflow for active scan.')

        ptr = self._next_ptr
        self._frames[ptr, :, :] = frame
        self.headers[ptr] = header
        self._in_flight.add(ptr)
        self._next_ptr += 1

        self.emit('PROCESS', buffer_pointer=ptr)
        return ptr

    def write_scan(self, path: AnyPath, all_: bool = False) -> None:
        """Request workers to write all hit frames from the active scan."""
        if not self.scan_processed.is_set():
            raise RuntimeError('Call handle_feedback() to completion before write_scan().')
        bn = self._buffer_name
        for ptr, hit in enumerate(self.hits):
            paths = []
            if all_:
                paths.append(str(Path(path) / 'all'))
            if hit:
                paths.append(str(Path(path) / 'tiff'))
            if not paths:
                continue
            self._write_pending.add(ptr)
            kwargs = {'paths': paths, 'header': self.headers[ptr]}
            self.emit('WRITE', buffer_name=bn, buffer_pointer=ptr, **kwargs)

    def handle_feedback(self, state: State, region: int, line: int, scan: int) -> None:
        """Continuously drain the feedback queue until scan is fully processed.

        This call modifies the decorated State table. Thus, either it
        must be run from the main thread, or a proxy Progress table must
        be used.
        """
        while (not self.scan_finished.is_set()) or self._in_flight or self._write_pending:
            try:
                fb_name, fb_kwargs = self.feedback_queue.get(timeout=15)
            except queue.Empty as e:
                raise RuntimeError('Did not receive Feedback within 15s') from e

            ptr = int(fb_kwargs['buffer_pointer'])

            if fb_name == 'PROCESSING':
                state.mark_processing(region, line, scan, ptr)

            elif fb_name == 'PROCESSED':
                d: DiffHuntResults = fb_kwargs['details']
                state.fill_step(region, line, scan, ptr, d.success, d.light, len(d.peaks))
                if self.hits is not None:
                    self.hits[ptr] = d.success
                self._in_flight.discard(ptr)

            elif fb_name == 'WRITTEN':
                self._write_pending.discard(ptr)

        self.scan_processed.set()

    def terminate_workers(self) -> None:
        """Command all workers to 'TERMINATE' and report the success."""
        self.emit_all('TERMINATE')
        for p in self._workers:
            p.join()
            p.close()
        self._workers.clear()


class DiffHuntWorker(mp.Process):
    def __init__(self, worker_id: int, commands: mp.Queue, feedback: mp.Queue, dtype: np.dtype):
        super().__init__(daemon=True)
        self.worker_id = worker_id
        self.commands = commands
        self.feedback = feedback
        self.dtype = np.dtype(dtype)
        self.config: dict[str, Any] = {}
        self.frames: Optional[np.ndarray] = None
        self.shm: Optional[SharedMemory] = None
        self.terminating: bool = False

    def emit(self, kind: FeedbackKind, **kwargs) -> None:
        kwargs['worker_id'] = self.worker_id
        self.feedback.put((kind, kwargs))

    def run(self) -> None:
        """Run the worker, continuously await and run `self.cmd_*` commands."""
        while not self.terminating:
            cmd_name, cmd_kwargs = self.commands.get()
            cmd_method = getattr(self, f'cmd_{cmd_name.lower()}')
            cmd_method(**cmd_kwargs)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~ self.cmd_COMMANDS ~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

    def cmd_init(self, *, buffer_name: str, buffer_shape: tuple[int, ...]) -> None:
        """INIT: Close previous buffer if exists and reattach to a new one."""
        if self.shm is not None:
            self.shm.close()
        self.shm = SharedMemory(name=buffer_name)
        self.frames = np.ndarray(buffer_shape, dtype=self.dtype, buffer=self.shm.buf)

    def cmd_configure(self, **diffhunt_kwargs) -> None:
        """CONFIGURE: Pass kwargs to self.config to be used at peak finding"""
        self.config.update(**diffhunt_kwargs)

    def cmd_process(self, *, buffer_pointer: int) -> None:
        """PROCESS: Eval diffraction results for image at assigned pointer"""
        ptr = int(buffer_pointer)
        self.emit('PROCESSING', buffer_pointer=ptr)
        try:
            d = ring_percentile_detection(frame=self.frames[ptr], **self.config)
        except Exception as e:
            d = DiffHuntResults(success=False)
        finally:
            self.emit('PROCESSED', buffer_pointer=ptr, details=d)

    def cmd_write(
        self,
        *,
        paths: Sequence[AnyPath],
        buffer_name: str,
        buffer_pointer: int,
        header: dict[str, Any],
    ) -> None:
        """WRITE: save image at assigned pointer on drive under buffer name"""
        try:
            dirs = [Path(p).resolve() for p in paths]
            filename = f'{buffer_name}_{buffer_pointer:06d}.tiff'
            frame = self.frames[buffer_pointer]
            first = dirs[0] / filename
            first.parent.mkdir(parents=True, exist_ok=True)
            write_tiff(fname=str(first), data=frame, header=header)
            for d in dirs[1:]:  # I assume no cross-device and won't raise
                d.mkdir(parents=True, exist_ok=True)
                target = d / filename
                if target.exists() or target.is_symlink():
                    target.unlink()
                os.link(first, target)
        finally:
            self.emit('WRITTEN', buffer_pointer=buffer_pointer)

    def cmd_terminate(self) -> None:
        self.terminating = True
        if self.shm is not None:
            self.shm.close()
