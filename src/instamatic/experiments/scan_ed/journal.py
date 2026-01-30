from __future__ import annotations

import inspect
import json
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np

from instamatic._typing import AnyPath
from instamatic.grid.window import ConvexPolygonWindow


class Journal:
    """Stores, retrieves and parses SPED State progress in a json file."""

    def __init__(self, path: AnyPath) -> None:
        self.path: Path = Path(path)
        self.writing: bool = True
        self._seq: int = 0
        self._init_seq_from_file()

    def _init_seq_from_file(self) -> None:
        """Initialize sequence counter from existing journal file (if any)."""
        if not self.path.exists():
            return

        last = 0
        with self.path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    break  # tolerate truncated last line
                seq = rec.get('seq')
                if isinstance(seq, int) and seq > last:
                    last = seq

        self._seq = last

    def write(self, method: str, kwargs: dict[str, Any]) -> None:
        """Write the new event record directly to the journal."""
        if not self.writing:
            return

        self._seq += 1
        record = {'seq': self._seq, 'ts': time.time(), 'method': method, 'kwargs': kwargs}
        line = json.dumps(record, separators=(',', ':')) + '\n'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a', encoding='utf-8') as f:
            f.write(line)
            f.flush()

    def events(self) -> Iterator[dict]:
        """Yield JSONL records of event, stops on a (truncated) final line."""
        if not self.path.exists():
            return
        with self.path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    break

    @contextmanager
    def writing_off(self):
        was_writing_before = self.writing
        self.writing = False
        try:
            yield
        finally:
            self.writing = was_writing_before


def serialize(obj):
    """Serialize complex numpy objects to JSON-readable ones."""

    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, (ConvexPolygonWindow,)):
        return repr(obj)
    return obj


def edits_journal(method: Callable) -> Callable:
    """Method decorator that logs its calls to object's journal attribute."""
    method_signature = inspect.signature(method)

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        out = method(self, *args, **kwargs)
        if (journal := getattr(self, 'journal', None)) is not None:
            bound = method_signature.bind(self, *args, **kwargs)
            bound.apply_defaults()
            payload = {k: serialize(v) for k, v in bound.arguments.items() if k != 'self'}
            journal.write(method.__name__, payload)
        return out

    return wrapper
