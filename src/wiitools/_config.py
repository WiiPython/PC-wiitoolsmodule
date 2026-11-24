"""Runtime configuration for the PC emulation (through environment variables).

All variables are optional:

=========================  ===============================================
WIITOOLS_SD                Folder used as ``sd:/`` (default ``./sd``)
WIITOOLS_USB               Folder used as ``usb:/`` (default ``./usb``)
WIITOOLS_MAP_ABSOLUTE      ``1`` (default): absolute paths such as ``/apps/x`` are
                           mapped to the SD card as on Wii;
                           ``0``: absolute Pfade bleiben echte PC-Pfade
WIITOOLS_HEADLESS          ``1``: no window or input (tests/CI)
WIITOOLS_SCALE             Window scale (default ``1``)
WIITOOLS_FB_SIZE           Physical framebuffer ``WxH`` (default ``640x480``)
WIITOOLS_ASPECT            ``4:3`` (default) or ``16:9`` (window is stretched
                           like a widescreen TV)
WIITOOLS_HZ                Refresh rate for VSync (default ``60``)
WIITOOLS_EXPANSION         Emulated Wiimote expansion: ``nunchuk`` (default),
                           ``classic``, ``guitar``, or ``none``
WIITOOLS_LANGUAGE          CONF/SYS language 0..9 (default 2 = German)
WIITOOLS_NICKNAME          Console nickname for CONF_GetNickName (default ``Wii``)
WIITOOLS_EMBEDDED_PNG      PNG file loaded by png_load_embedded() (otherwise a
                           built-in test image)
=========================  ===============================================
"""
from __future__ import annotations

import os
import re

__all__ = ["cfg", "map_path"]


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.strip().lower() not in ("0", "false", "no", "off")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _env_size(name: str, default: tuple[int, int]) -> tuple[int, int]:
    v = os.environ.get(name)
    if not v:
        return default
    m = re.fullmatch(r"\s*(\d+)\s*[xX*,]\s*(\d+)\s*", v)
    if not m:
        return default
    w, h = int(m.group(1)), int(m.group(2))
    return (w, h) if w > 0 and h > 0 else default


class _Cfg:
    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        cwd = os.getcwd()
        self.sd_root = os.path.abspath(os.environ.get("WIITOOLS_SD") or os.path.join(cwd, "sd"))
        self.usb_root = os.path.abspath(os.environ.get("WIITOOLS_USB") or os.path.join(cwd, "usb"))
        self.map_absolute = _env_bool("WIITOOLS_MAP_ABSOLUTE", os.name == "posix")
        self.headless = _env_bool("WIITOOLS_HEADLESS", False)
        self.scale = max(0.25, _env_float("WIITOOLS_SCALE", 1.0))
        self.fb_size = _env_size("WIITOOLS_FB_SIZE", (640, 480))
        aspect = os.environ.get("WIITOOLS_ASPECT", "4:3").strip()
        self.widescreen = aspect in ("16:9", "16x9", "wide", "1")
        self.hz = max(1.0, _env_float("WIITOOLS_HZ", 60.0))
        exp = os.environ.get("WIITOOLS_EXPANSION", "nunchuk").strip().lower()
        self.expansion = exp if exp in ("nunchuk", "classic", "guitar", "none") else "nunchuk"
        self.language = min(9, max(0, _env_int("WIITOOLS_LANGUAGE", 2)))
        self.nickname = os.environ.get("WIITOOLS_NICKNAME", "Wii")[:10]
        self.embedded_png = os.environ.get("WIITOOLS_EMBEDDED_PNG") or None


cfg = _Cfg()

# Device prefixes recognized by libfat/libogc on Wii.
_DEVICE_RE = re.compile(r"^(sd|usb|fat|carda|cardb|gcsda|gcsdb|sdgecko|dvd):/*(.*)$", re.IGNORECASE)


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), root]) == root
    except ValueError:
        return False


def map_path(path: str | os.PathLike) -> str:
    """Map a Wii path (``sd:/...``, ``usb:/...``, ``/apps/...``) to a PC path."""
    p = os.fspath(path)
    if isinstance(p, bytes):
        p = p.decode("utf-8", "surrogateescape")
    m = _DEVICE_RE.match(p)
    if m:
        dev, rest = m.group(1).lower(), m.group(2)
        root = cfg.usb_root if dev == "usb" else cfg.sd_root
        return os.path.join(root, *[part for part in rest.split("/") if part])
    if cfg.map_absolute and p.startswith("/") and not (
        _inside(p, cfg.sd_root) or _inside(p, cfg.usb_root)
    ):
        return os.path.join(cfg.sd_root, *[part for part in p.split("/") if part])
    return p
