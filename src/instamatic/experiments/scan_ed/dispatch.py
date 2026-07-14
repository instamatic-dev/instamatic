from __future__ import annotations

import multiprocessing as mp
import os
import queue
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence, Union

import numpy as np
from typing_extensions import Literal, TypeAlias

from instamatic._typing import AnyPath
from instamatic.experiments.scan_ed.detection import DiffHuntResults, ring_percentile_detection
from instamatic.experiments.scan_ed.utils import SaveName
from instamatic.formats import read_tiff, write_tiff

if TYPE_CHECKING:
    from instamatic.experiments.scan_ed.state import State

N_PROCESSORS = 4

CommandKind = Literal['CONFIGURE', 'INIT', 'PROCESS', 'WRITE', 'TERMINATE']
FeedbackKind = Literal['PROCESSING', 'PROCESSED', 'WRITTEN']

Command: TypeAlias = tuple[CommandKind, dict[str, Any]]
Feedback: TypeAlias = tuple[FeedbackKind, dict[str, Any]]
MovieOrPaths: TypeAlias = Iterable[Union[tuple[np.ndarray, Optional[dict]], AnyPath]]


class DiffHuntDispatcher:
    """Proxy class: ask workers on other processes if image has diffraction."""

    def __init__(self, state: State, shape: tuple[int, int], dtype: np.dtype) -> None:
        self.state: State = state  # directly affect the state: fill scans, steps
        self.shape: tuple[int, int] = shape
        self.dtype: np.dtype = np.dtype(dtype)

        self.command_queues: list[mp.Queue[Command]] = []
        self.feedback_queue: mp.Queue[Feedback] = mp.Queue()

        self._workers: list[DiffHuntWorker] = []
        self._spawn_workers()
        self._busy_workers: dict[int, Optional[int]] = {}  # worker ID: pointer
        self._free_workers: set[int] = set()  # IDs of worker not running a task

        self.region_line_scan: Optional[tuple[int, int, int]] = None
        self._shm: Optional[SharedMemory] = None
        self._frames: Optional[np.ndarray] = None
        self._n_frames: int = 0

        self.hits: Optional[np.ndarray] = None
        self.headers: list[Optional[dict]] = []

    @staticmethod
    def _create_shm(name: str, size: int) -> SharedMemory:
        """Initialize shared memory, try to close previous one if needed."""
        exc = None
        for _ in range(500):
            try:
                return SharedMemory(name=name, create=True, size=size)
            except FileExistsError as e:
                old = SharedMemory(name=name, create=False)
                old.close()
                old.unlink()
                exc = e
                sleep(0.01)
        else:
            raise FileExistsError(f'Could not init shared memory {name}') from exc

    def _spawn_workers(self) -> None:
        """Run once at the start of experiment to spawn eval processes."""
        for wid in range(N_PROCESSORS):
            w = DiffHuntWorker(wid, (q := mp.Queue()), self.feedback_queue, self.dtype)
            w.start()
            self.command_queues.append(q)
            self._workers.append(w)

    @property
    def buffer_name(self) -> str:
        return str(SaveName(*self.region_line_scan))

    def emit(self, task: CommandKind, **kwargs) -> None:
        """Shorthand to create and put Command in free self.commands queue."""
        wid = self._free_workers.pop()
        self._busy_workers[wid] = kwargs.get('buffer_pointer', None)
        self.command_queues[wid].put((task, kwargs))

    def emit_all(self, task: CommandKind, **kwargs) -> None:
        """Shorthand to create and put Command in ALL self.commands queues."""
        for q in self.command_queues:
            q.put((task, kwargs))

    def begin_scan(self, region: int, line: int, scan: int, n_frames: int) -> None:
        """Allocate a new shared buffer and reset all tracking for one scan."""
        self.region_line_scan = region, line, scan
        self._n_frames = int(n_frames)
        self._free_workers = set(range(N_PROCESSORS))
        self._busy_workers = {}
        shape3 = (self._n_frames, self.shape[0], self.shape[1])
        size = int(np.prod(shape3) * self.dtype.itemsize)
        self._shm = self._create_shm(name=self.buffer_name, size=size)
        self._frames = np.ndarray(shape3, dtype=self.dtype, buffer=self._shm.buf)
        self.hits = np.zeros(self._n_frames, dtype=bool)
        self.headers = [None] * self._n_frames
        self.emit_all('INIT', buffer_name=self.buffer_name, buffer_shape=shape3)

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
            self.region_line_scan = None
            self._n_frames = 0
            self.hits = None
            self.headers = []

    def _handle_feedback(self) -> None:
        """Receive one feedback item and apply it to state and bookkeeping.

        PROCESSING: update the state table (no worker freed yet — still running).
        PROCESSED:  record result, discard from in-flight, mark worker free.
        WRITTEN:    discard from write-pending, mark worker free.
        """
        try:
            fb_name, fb_kwargs = self.feedback_queue.get(timeout=15)
        except queue.Empty as e:
            raise RuntimeError('Did not receive feedback within 15 s') from e

        wid = int(fb_kwargs['worker_id'])
        ptr = int(self._busy_workers.get(wid, -1))

        if fb_name == 'PROCESSING':
            self.state.mark_processing(*self.region_line_scan, ptr)

        elif fb_name == 'PROCESSED':
            d: DiffHuntResults = fb_kwargs['details']
            p = len(d.peaks)
            self.state.fill_step(*self.region_line_scan, ptr, d.success, d.light, p)
            if self.hits is not None:
                self.hits[ptr] = d.success

        if fb_name in {'PROCESSED', 'WRITTEN'}:
            self._busy_workers.pop(wid, None)
            self._free_workers.add(wid)

    def process_scan(self, movie: MovieOrPaths) -> None:
        """Write `movie` frames into shared buffer, dispatch PROCESS tasks."""
        if self._frames is None:
            raise RuntimeError('Call begin_scan() first.')

        for ptr, src in enumerate(movie):  # if given movie, iterate one-by-one
            if isinstance(src, tuple):
                frame, header = src
            else:  # if given a path list, inherit pointer from the path name
                frame, header = read_tiff(src)
                ptr = SaveName(Path(src).stem).as_dict()['frame']
            if ptr >= self._n_frames:
                raise RuntimeError('Buffer overflow for active scan.')

            while not self._free_workers:  # Block until some worker finishes.
                self._handle_feedback()

            self._frames[ptr] = frame
            self.headers[ptr] = header
            self.emit('PROCESS', buffer_pointer=ptr)

        while self._busy_workers:  # drain until every worker is accounted for
            self._handle_feedback()

    def write_scan(self, path: AnyPath, all_: bool = False) -> None:
        """Send WRITE for all hit frames, block until every write completes."""
        if self.hits is None:
            raise RuntimeError('Call begin_scan() first.')

        for ptr, hit in enumerate(self.hits):
            h: dict = self.headers[ptr]
            p: list[str] = []
            if all_:
                p.append(str(Path(path) / 'all'))
            if hit:
                p.append(str(Path(path) / 'tiff'))
            if not p:
                continue

            while not self._free_workers:
                self._handle_feedback()
            self.emit('WRITE', paths=p, header=h, buffer_pointer=ptr)

        while self._busy_workers:  # drain until every worker is accounted for
            self._handle_feedback()

    def terminate_workers(self) -> None:
        """Command all workers to terminate and join them."""
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
        self.buffer_name: Optional[str] = None
        self.shm: Optional[SharedMemory] = None
        self.frames: Optional[np.ndarray] = None
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
        self.buffer_name = buffer_name
        self.shm = SharedMemory(name=buffer_name)
        self.frames = np.ndarray(buffer_shape, dtype=self.dtype, buffer=self.shm.buf)

    def cmd_configure(self, **diffhunt_kwargs) -> None:
        """CONFIGURE: Pass kwargs to self.config to be used at peak finding"""
        self.config.update(**diffhunt_kwargs)

    def cmd_process(self, *, buffer_pointer: int) -> None:
        """PROCESS: Eval diffraction results for image at assigned pointer"""
        ptr = int(buffer_pointer)
        self.emit('PROCESSING')
        try:
            d = ring_percentile_detection(frame=self.frames[ptr], **self.config)
        except Exception as _:
            d = DiffHuntResults(success=False)
        finally:
            self.emit('PROCESSED', details=d)

    def cmd_write(
        self,
        *,
        paths: Sequence[AnyPath],
        buffer_pointer: int,
        header: Optional[dict[str, Any]],
    ) -> None:
        """WRITE: save image at assigned pointer on drive under buffer name"""
        try:
            dirs = [Path(p).resolve() for p in paths]
            filename = f'{self.buffer_name}_{buffer_pointer:06d}.tiff'
            frame = self.frames[buffer_pointer]
            first = dirs[0] / filename
            first.parent.mkdir(parents=True, exist_ok=True)
            if not first.exists():
                write_tiff(fname=str(first), data=frame, header=header)
            for d in dirs[1:]:  # I assume no cross-device and won't raise
                d.mkdir(parents=True, exist_ok=True)
                target = d / filename
                if target.exists() or target.is_symlink():
                    target.unlink()
                os.link(first, target)
        finally:
            self.emit('WRITTEN')

    def cmd_terminate(self) -> None:
        self.terminating = True
        if self.shm is not None:
            self.shm.close()
