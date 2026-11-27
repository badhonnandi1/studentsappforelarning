"""UUIDv7 ids (RFC 9562 §5.7), time-ordered so B-tree inserts stay local.

Python 3.14 adds ``uuid.uuid7``; on 3.13 this vendored version is used. Within one
millisecond the 12-bit ``rand_a`` field is a counter, so ids from one process are monotonic.
"""

from __future__ import annotations

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_counter = 0
_COUNTER_MAX = 0xFFF


def _parts() -> tuple[int, int]:
    global _last_ms, _counter
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms > _last_ms:
            _last_ms = ms
            _counter = int.from_bytes(os.urandom(2)) & 0x7FF  # leave headroom to count up
        else:
            _counter += 1
            if _counter > _COUNTER_MAX:  # counter exhausted: borrow the next millisecond
                _last_ms += 1
                _counter = 0
        return _last_ms, _counter


def uuid7() -> uuid.UUID:
    ms, counter = _parts()
    rand_b = int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= counter << 64
    value |= 0b10 << 62
    value |= rand_b
    return uuid.UUID(int=value)


def uuid7_time_ms(value: uuid.UUID) -> int:
    """The Unix millisecond timestamp embedded in a UUIDv7."""
    return value.int >> 80
