"""Filesystem (SD/USB through libfat), mapped to local folders."""
from __future__ import annotations

import os

from ._config import cfg, map_path


def fatInitDefault() -> int:
    """Create the folders for ``sd:/`` and ``usb:/``. 1 = success."""
    try:
        os.makedirs(cfg.sd_root, exist_ok=True)
        os.makedirs(cfg.usb_root, exist_ok=True)
        return 1
    except OSError:
        return 0


def remove(path: str) -> int:
    try:
        os.remove(map_path(path))
        return 0
    except OSError:
        return -1


def read_file(path: str) -> bytes:
    p = map_path(path)
    try:
        with open(p, "rb") as f:
            return f.read()
    except OSError as exc:
        raise OSError(exc.errno, exc.strerror, path) from None


def write_file(path: str, data: bytes | bytearray | str) -> int:
    if isinstance(data, str):
        raw = data.encode("utf-8")
    elif isinstance(data, (bytes, bytearray, memoryview)):
        raw = bytes(data)
    else:
        raise TypeError("data must be bytes, bytearray or str")
    p = map_path(path)
    try:
        with open(p, "wb") as f:
            f.write(raw)
    except OSError as exc:
        raise OSError(exc.errno, exc.strerror, path) from None
    return len(raw)
