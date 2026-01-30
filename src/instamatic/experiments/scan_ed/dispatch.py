from __future__ import annotations

import multiprocessing as mp
import queue
import uuid
from dataclasses import dataclass
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
from typing_extensions import Literal

from instamatic._typing import AnyPath
from instamatic.experiments.scan_ed.detection import DiffHuntResults, ring_percentile_detection
from instamatic.formats import write_tiff

if TYPE_CHECKING:
    from instamatic.experiments.scan_ed.state import State

N_PROCESSORS = 4

Task = Literal['INIT', 'PROCESS', 'WRITE', 'TERMINATE']
Event = Literal['PROCESSING', 'PROCESSED']


@dataclass(frozen=True)
class Command:
    """Schema used to communicate commands from dispatcher to any worker."""

    task: Task
    buffer_name: Optional[str] = None
    buffer_pointer: Optional[int] = None
    buffer_shape: Optional[tuple[int, int, int]] = None
    kwargs: Optional[dict] = None


@dataclass(frozen=True)
class Feedback:
    """Schema used to communicate feedback from any worker to dispatcher."""

    event: Event
    worker_id: int
    buffer_pointer: Optional[int] = None
    details: Optional[DiffHuntResults] = None


class DiffHuntDispatcher:
    """Proxy class: ask workers on other processes if image has diffraction"""

    def __init__(self, shape: tuple[int, int], dtype: np.dtype) -> None:
        self.shape: tuple[int, int] = shape
        self.dtype: np.dtype = np.dtype(dtype)
        self.commands: mp.Queue[Command] = mp.Queue()
        self.feedback: mp.Queue[Feedback] = mp.Queue()

        self._workers: list[mp.Process] = []
        self._spawn_workers()

        self._buffer_name: str = ''
        self._shm: Optional[SharedMemory] = None
        self._frames: Optional[np.ndarray] = None

        self._n_frames: int = 0
        self._next_ptr: int = 0
        self._in_flight: set[int] = set()

        self.hits: Optional[np.ndarray] = None
        self.headers: list[Optional[dict]] = []

    def _spawn_workers(self) -> None:
        """Run once at the start of experiment to spawn eval processes."""
        for wid in range(N_PROCESSORS):
            worker = DiffHuntWorker(wid, self.commands, self.feedback, self.dtype)
            worker.start()
            self._workers.append(worker)

    def emit(self, task: Task, *args, **kwargs) -> None:
        """Shorthand to create and put Command in the self.commands queue."""
        self.commands.put(Command(task, *args, **kwargs))

    def begin_scan(self, n_frames: int, name: Optional[str] = None) -> None:
        """Allocate a new shared buffer and reset all tracking for one scan."""
        self._buffer_name = name or uuid.uuid4().hex
        self._n_frames = int(n_frames)
        self._next_ptr = 0
        self._in_flight.clear()
        shape3 = (self._n_frames, self.shape[0], self.shape[1])
        size = int(np.prod(shape3) * self.dtype.itemsize)
        self._shm = SharedMemory(name=self._buffer_name, create=True, size=size)
        self._frames = np.ndarray(shape3, dtype=self.dtype, buffer=self._shm.buf)
        self.hits = np.zeros(self._n_frames, dtype=bool)
        self.headers = [None] * self._n_frames
        for _ in self._workers:
            self.emit('INIT', buffer_name=self._buffer_name, buffer_shape=shape3)

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
            self.hits = None
            self.headers = []

    def submit(self, frame: np.ndarray, header: Optional[dict]) -> int:
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

        self.commands.put(Command('PROCESS', buffer_pointer=ptr))
        return ptr

    def all_frames_processed(self) -> bool:
        """All submitted frames have been processed and scan is complete."""
        return (self._next_ptr == self._n_frames) and (not self._in_flight)

    def write_scan(self, path: AnyPath) -> None:
        """Request workers to write all hit frames from the active scan."""
        for pointer, hit in enumerate(self.hits):
            if hit:
                bn = self._buffer_name
                kwargs = {'path': path, 'header': self.headers[pointer]}
                self.emit('WRITE', buffer_name=bn, buffer_pointer=pointer, kwargs=kwargs)

    # HANDLE FEEDBACK INCOMING FROM THE WORKERS

    def drain_feedback(self, state: State, window: int, scan: int) -> None:
        """Drains feedback queue; If using tk, call from main thread only!"""
        for _ in range(2 * self._n_frames):
            try:
                fb: Feedback = self.feedback.get(timeout=15)
            except queue.Empty as e:
                raise RuntimeError('Did not receive Feedback within 15s') from e

            pointer = int(fb.buffer_pointer)

            if fb.event == 'PROCESSING':
                state.mark_processing(window, scan, pointer)

            elif fb.event == 'PROCESSED':
                d: DiffHuntResults = fb.details
                state.fill_step(window, scan, pointer, d.success, len(d.peaks))
                if self.hits is not None:
                    self.hits[pointer] = d.success
                self._in_flight.discard(pointer)

    def terminate_workers(self) -> None:
        """Command all workers to 'TERMINATE' and report the success."""
        for _ in self._workers:
            self.emit('TERMINATE')
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
        self._frames: Optional[np.ndarray] = None
        self._shm: Optional[SharedMemory] = None

    def run(self) -> None:
        while True:
            cmd: Command = self.commands.get()

            if cmd.task == 'INIT':
                if self._shm is not None:
                    self._shm.close()
                self._shm = SharedMemory(name=cmd.buffer_name)
                self._frames = np.ndarray(
                    cmd.buffer_shape, dtype=self.dtype, buffer=self._shm.buf
                )

            elif cmd.task == 'PROCESS':
                ptr = int(cmd.buffer_pointer)
                frame = self._frames[ptr]
                d = ring_percentile_detection(frame=frame)
                self.feedback.put(
                    Feedback('PROCESSED', self.worker_id, buffer_pointer=ptr, details=d)
                )

            elif cmd.task == 'WRITE':
                path = Path(cmd.kwargs['path']).resolve()
                filename = f'{cmd.buffer_name}_{cmd.buffer_pointer:06d}.tiff'
                frame = self._frames[cmd.buffer_pointer]
                header = cmd.kwargs.get('header', {})
                write_tiff(fname=str(path / filename), data=frame, header=header)

            elif cmd.task == 'TERMINATE':
                if self._shm is not None:
                    self._shm.close()
                return
