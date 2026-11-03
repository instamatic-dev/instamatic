from __future__ import annotations

import base64

import numpy as np


def encode_hits(h: np.ndarray) -> str:
    packed = np.packbits(np.asarray(h, np.bool_), bitorder='little').tobytes()
    return base64.b64encode(packed).decode('ascii')


def decode_hits(b64: str, n: int) -> np.ndarray:
    raw = base64.b64decode(b64.encode('ascii'))
    bits = np.unpackbits(np.frombuffer(raw, np.uint8), bitorder='little')
    return bits[:n].astype(np.bool_)


def encode_i16(a: np.ndarray) -> str:
    a = np.asarray(a, dtype=np.int16)
    return base64.b64encode(a.tobytes()).decode('ascii')


def decode_i16(s: str) -> np.ndarray:
    raw = base64.b64decode(s.encode('ascii'))
    return np.frombuffer(raw, dtype=np.int16)


def encode_u32(a: np.ndarray) -> str:
    a = np.asarray(a, dtype=np.uint32)
    return base64.b64encode(a.tobytes()).decode('ascii')


def decode_u32(s: str) -> np.ndarray:
    raw = base64.b64decode(s.encode('ascii'))
    return np.frombuffer(raw, dtype=np.uint32)
