"""Video/GX-Emulation: Framebuffer, PNG-Slots, Formen, Text, Surfaces."""
from __future__ import annotations

import io
import operator
import struct
import zlib

import numpy as np

from . import _raster as R
from ._config import cfg, map_path
from ._display import display, pygame

try:
    from PIL import Image as _PILImage
except Exception:  # pragma: no cover
    _PILImage = None

width = 802
height = 480


class _G:
    mode: str | None = None       # None | "console" | "gx"
    adopt = False
    fb: np.ndarray | None = None  # sichtbarer XFB im Konsolenmodus (H, W, 3)
    efb: np.ndarray | None = None  # GX-EFB (H, W, 3)
    clear = (255, 255, 255)
    logical: tuple[float, float] | None = None
    vp = (0.0, 0.0, 0.0, 0.0)
    dirty = False
    images: dict[str, np.ndarray] = {}
    current: str | None = None
    target: str | None = None


def _i(v) -> int:
    return operator.index(v)


def _rgba(obj) -> tuple[int, int, int, int]:
    if not isinstance(obj, tuple) or len(obj) != 4:
        raise TypeError("color must be a tuple (r, g, b, a)")
    return tuple(max(0, min(255, operator.index(c))) for c in obj)  # type: ignore[return-value]


def _phys() -> tuple[int, int]:
    return display.fb_size()


# ----------------------------------------------------------------- Ziele
def _screen_target() -> R.Target:
    pw, ph = _phys()
    if _G.logical is None:
        return R.Target(_G.efb, "gx")
    lw, lh = _G.logical
    vx, vy, vw, vh = _G.vp
    return R.Target(_G.efb, "gx", s=vw / lw, ox=vx, oy=vy,
                    clip=(int(vx), int(vy), int(vx) + int(vw), int(vy) + int(vh)))


def _surface_target(name: str) -> R.Target:
    return R.Target(_G.images[name], "sw")


def _active_surface() -> str | None:
    if _G.target is not None and _G.target not in _G.images:
        _G.target = None
    return _G.target


# ----------------------------------------------------------------- Init
def _new_fb(color) -> np.ndarray:
    pw, ph = _phys()
    fb = np.empty((ph, pw, 3), dtype=np.uint8)
    fb[:] = color
    return fb


def _console_init(clear: bool) -> None:
    display.ensure()
    if _G.fb is None or clear:
        _G.fb = _new_fb((0, 0, 0))
    if _G.mode is None:
        _G.mode = "console"
        display.present(_G.fb)


def terminal_init() -> None:
    _console_init(clear=True)


def rendering_init() -> None:
    display.ensure()
    _G.mode = "gx"
    _G.adopt = False
    _G.clear = (255, 255, 255)
    _G.efb = _new_fb(_G.clear)
    _G.logical = None
    _G.dirty = False
    display.present(_G.efb.copy())


def rendering_adopt(mode_ptr: int, fb_ptr: int, empty_q: int = 0) -> None:
    mode_ptr, fb_ptr, empty_q = _i(mode_ptr), _i(fb_ptr), _i(empty_q)
    if mode_ptr <= 0 or fb_ptr <= 0:
        raise ValueError("rendering_adopt: mode_ptr/fb_ptr outside valid RAM")
    display.ensure()
    _G.mode = "gx"
    _G.adopt = True
    _G.clear = (0, 0, 0)
    _G.efb = _new_fb(_G.clear)
    _G.logical = None
    _G.dirty = False


def gutil_prepare() -> None:
    if _G.mode == "gx":
        _G.dirty = True
    return None


def set_screen_size(w: int, h: int) -> None:
    w, h = _i(w), _i(h)
    if _G.mode != "gx":
        raise RuntimeError("graphics not initialized")
    if w <= 0 or h <= 0:
        _G.logical = None
        return None
    pw, ph = _phys()
    scale = min(pw / w, ph / h)
    vw, vh = w * scale, h * scale
    _G.logical = (float(w), float(h))
    _G.vp = ((pw - vw) * 0.5, (ph - vh) * 0.5, vw, vh)
    return None


# ----------------------------------------------------------------- Frame
def _flush() -> None:
    if _G.dirty:
        if _G.mode == "gx" and _G.efb is not None:
            display.present(_G.efb.copy())
            _G.efb[:] = _G.clear
        elif _G.mode == "console" and _G.fb is not None:
            display.present(_G.fb)
        _G.dirty = False
    display.wait_vsync()


def VIDEO_WaitVSync() -> None:
    display.wait_vsync()


def usleep(microseconds: int) -> None:
    display.sleep(max(0, _i(microseconds)) / 1_000_000)


def render_update() -> None:
    _flush()


def update() -> None:
    from ._pad import PAD_ScanPads
    from ._wpad import WPAD_ScanPads
    WPAD_ScanPads()
    PAD_ScanPads()
    _flush()


def input_update() -> None:
    from ._pad import PAD_ScanPads
    from ._wpad import WPAD_ScanPads
    WPAD_ScanPads()
    PAD_ScanPads()


# ----------------------------------------------------------------- PNG I/O
def _decode_png(data: bytes, what: str) -> np.ndarray:
    try:
        if _PILImage is not None:
            img = _PILImage.open(io.BytesIO(data))
            if img.format != "PNG":
                raise ValueError("not a PNG file")
            return np.array(img.convert("RGBA"), dtype=np.uint8)
        if pygame is not None:
            surf = pygame.image.load(io.BytesIO(data), "x.png")
            arr = pygame.image.tobytes(surf, "RGBA")
            return np.frombuffer(arr, np.uint8).reshape(surf.get_height(), surf.get_width(), 4).copy()
    except Exception as exc:
        raise OSError(f"{what}: decode failed ({exc}, bytes={len(data)})") from None
    raise OSError(f"{what}: no PNG decoder (install Pillow or pygame)")


def _encode_png(rgba: np.ndarray) -> bytes:
    h, w = rgba.shape[:2]
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _embedded_png() -> bytes:
    if cfg.embedded_png:
        with open(map_path(cfg.embedded_png), "rb") as f:
            return f.read()
    # eingebautes 64x64-Testbild (Schachbrett mit Rand)
    y, x = np.mgrid[0:64, 0:64]
    img = np.zeros((64, 64, 4), np.uint8)
    checker = ((x // 8 + y // 8) % 2).astype(bool)
    img[checker] = (230, 60, 60, 255)
    img[~checker] = (240, 240, 240, 255)
    border = (x < 2) | (y < 2) | (x > 61) | (y > 61)
    img[border] = (40, 40, 160, 255)
    return _encode_png(img)


def _store(name: str, rgba: np.ndarray) -> tuple[int, int]:
    _G.images[name] = np.ascontiguousarray(rgba, dtype=np.uint8)
    _G.current = name
    h, w = rgba.shape[:2]
    return (w, h)


def png_load_named(path: str, name: str) -> tuple[int, int]:
    what = f"png_load_named('{path}','{name}')"
    try:
        with open(map_path(path), "rb") as f:
            data = f.read()
    except OSError as exc:
        raise OSError(f"{what}: file read failed (errno={exc.errno}: {exc.strerror})") from None
    return _store(name, _decode_png(data, what))


def png_load(path: str) -> tuple[int, int]:
    return png_load_named(path, "__default__")


def png_load_embedded_named(name: str) -> tuple[int, int]:
    return _store(name, _decode_png(_embedded_png(), f"png_load_embedded_named('{name}')"))


def png_load_embedded() -> tuple[int, int]:
    return png_load_embedded_named("__default__")


def png_use(name: str) -> None:
    if name not in _G.images:
        raise KeyError(f"PNG name not found: '{name}'")
    _G.current = name
    return None


def _require_current() -> np.ndarray:
    if _G.current is None or _G.current not in _G.images:
        raise RuntimeError("no PNG selected/loaded")
    return _G.images[_G.current]


def png_info() -> tuple[int, int] | None:
    if _G.current is None or _G.current not in _G.images:
        return None
    h, w = _G.images[_G.current].shape[:2]
    return (w, h)


def _remove(name: str) -> None:
    _G.images.pop(name, None)
    if _G.current == name:
        _G.current = None
    if _G.target == name:
        _G.target = None


def png_unload() -> None:
    if _G.current is not None:
        _remove(_G.current)
    return None


def png_unload_all() -> None:
    _G.images.clear()
    _G.current = None
    _G.target = None
    return None


def png_save(path: str) -> int:
    img = _require_current()
    data = _encode_png(img)
    with open(map_path(path), "wb") as f:
        f.write(data)
    return 0


# ----------------------------------------------------------------- Blits
def _blit_region(img: np.ndarray, sx, sy, sw, sh, dx, dy, dw, dh, *, to_screen: bool = False) -> None:
    surf = None if to_screen else _active_surface()
    if surf is not None:
        R.blit_fixed(_surface_target(surf), img, sx, sy, sw, sh, dx, dy, dw, dh)
        return
    if _G.mode == "gx":
        R.blit_gx(_screen_target(), img, sx, sy, sw, sh, dx, dy, dw, dh)
        _G.dirty = True
        return
    if _G.mode == "console" and _G.fb is not None:
        R.blit_fixed(R.Target(_G.fb, "xfb"), img, sx, sy, sw, sh, dx, dy, dw, dh)
        _G.dirty = True
        return
    raise RuntimeError("framebuffer not initialized")


def png_show(x: int, y: int) -> None:
    x, y = _i(x), _i(y)
    img = _require_current()
    h, w = img.shape[:2]
    _blit_region(img, 0, 0, w, h, x, y, w, h)


def png_show_region(sx: int, sy: int, sw: int, sh: int, dx: int, dy: int) -> None:
    sx, sy, sw, sh, dx, dy = map(_i, (sx, sy, sw, sh, dx, dy))
    _blit_region(_require_current(), sx, sy, sw, sh, dx, dy, sw, sh)


def png_show_region_scaled(sx: int, sy: int, sw: int, sh: int,
                           dx: int, dy: int, dw: int, dh: int) -> None:
    a = tuple(map(_i, (sx, sy, sw, sh, dx, dy, dw, dh)))
    _blit_region(_require_current(), *a)


def png_show_scaled(dx: int, dy: int, dw: int, dh: int) -> None:
    dx, dy, dw, dh = map(_i, (dx, dy, dw, dh))
    img = _require_current()
    h, w = img.shape[:2]
    _blit_region(img, 0, 0, w, h, dx, dy, dw, dh)


def png_show_fullscreen() -> None:
    img = _require_current()
    if _G.mode is None:
        raise RuntimeError("framebuffer not initialized")
    pw, ph = _phys()
    h, w = img.shape[:2]
    _blit_region(img, 0, 0, w, h, 0, 0, pw, ph)


def png(screen_x: int, screen_y: int, image_x: int, image_y: int, image_width: int,
        image_height: int, screen_width: int, screen_height: int) -> None:
    dx, dy, sx, sy, sw, sh, dw, dh = map(_i, (screen_x, screen_y, image_x, image_y, image_width,
                                              image_height, screen_width, screen_height))
    _blit_region(_require_current(), sx, sy, sw, sh, dx, dy, dw, dh)


def png_quad(x1: float, y1: float, x2: float, y2: float, x3: float, y3: float, x4: float, y4: float,
             image_x: int, image_y: int, image_width: int, image_height: int) -> None:
    pts = [(float(x1), float(y1)), (float(x2), float(y2)), (float(x3), float(y3)), (float(x4), float(y4))]
    sx, sy, sw, sh = map(_i, (image_x, image_y, image_width, image_height))
    img = _require_current()
    if _G.mode != "gx":
        raise RuntimeError("png_quad requires rendering_init() and GX texture path")
    R.blit_quad(_screen_target(), img, pts, sx, sy, sw, sh)
    _G.dirty = True


# ----------------------------------------------------------------- Formen/Text
def _shape_target() -> R.Target:
    surf = _active_surface()
    if surf is not None:
        return _surface_target(surf)
    if _G.mode != "gx":
        raise RuntimeError("rendering not initialized")
    _G.dirty = True
    return _screen_target()


def draw_rect(x: int, y: int, width: int, height: int, rgba, angle_deg: float) -> None:
    x, y, w, h = map(_i, (x, y, width, height))
    angle = float(angle_deg)
    color = _rgba(rgba)
    if w <= 0 or h <= 0:
        return None
    R.draw_rect(_shape_target(), x, y, w, h, color, angle)


def draw_circle(x: int, y: int, radius: int, rgba) -> None:
    x, y, r = map(_i, (x, y, radius))
    color = _rgba(rgba)
    if r <= 0:
        return None
    R.draw_circle(_shape_target(), x, y, r, color)


def draw_oval(x: int, y: int, width: int, height: int, rgba, angle_deg: float) -> None:
    x, y, w, h = map(_i, (x, y, width, height))
    angle = float(angle_deg)
    color = _rgba(rgba)
    if w <= 0 or h <= 0:
        return None
    R.draw_oval(_shape_target(), x, y, w, h, color, angle)


def render_text(x: int, y: int, text: str, size: int, shadow: int, rgba, angle_deg: float) -> None:
    x, y, size, shadow = map(_i, (x, y, size, shadow))
    if not isinstance(text, str):
        raise TypeError("render_text() argument 3 must be str")
    angle = float(angle_deg)
    color = _rgba(rgba)
    R.render_text(_shape_target(), x, y, text, size, shadow, color, angle)


def text_length(text: str, size: int) -> int:
    if not isinstance(text, str):
        raise TypeError("text_length() argument 1 must be str")
    return R.text_length(text, _i(size))


# ----------------------------------------------------------------- Surfaces
def _surface(name: str, what: str = "surface") -> np.ndarray:
    img = _G.images.get(name)
    if img is None:
        raise KeyError(f"{what} not found: '{name}'")
    return img


def surface_new(name: str, width: int, height: int) -> tuple[int, int]:
    w, h = _i(width), _i(height)
    if w <= 0 or h <= 0:
        raise ValueError("width and height must be positive")
    _G.images[name] = np.zeros((h, w, 4), dtype=np.uint8)
    return (w, h)


def surface_set_target(name: str) -> None:
    _surface(name)
    _G.target = name
    return None


def surface_clear_target() -> None:
    _G.target = None
    return None


def surface_fill(name: str, rgba) -> None:
    color = _rgba(rgba)
    _surface(name)[:] = color
    return None


def surface_get_size(name: str) -> tuple[int, int] | None:
    img = _G.images.get(name)
    if img is None:
        return None
    return (img.shape[1], img.shape[0])


def blit(name: str, x: int, y: int) -> None:
    x, y = _i(x), _i(y)
    img = _surface(name)
    h, w = img.shape[:2]
    _blit_region(img, 0, 0, w, h, x, y, w, h, to_screen=True)


def surface_blit(src: str, dst: str | None, x: int, y: int,
                 sx: int = 0, sy: int = 0, sw: int = -1, sh: int = -1) -> None:
    x, y, sx, sy, sw, sh = map(_i, (x, y, sx, sy, sw, sh))
    s = _surface(src, "source surface")
    if dst is None:
        dname = _active_surface()
        if dname is None:
            raise RuntimeError("no active render target — call surface_set_target() first")
    else:
        if not isinstance(dst, str):
            raise TypeError("dst must be a surface name (str) or None")
        dname = dst
        _surface(dname, "destination surface")
    if sw < 0:
        sw = s.shape[1] - sx
    if sh < 0:
        sh = s.shape[0] - sy
    R.blit_fixed(_surface_target(dname), s.copy() if dname == src else s, sx, sy, sw, sh, x, y, sw, sh)


def surface_get_pixels(name: str) -> bytes:
    return _surface(name).tobytes()


def surface_set_pixels(name: str, data) -> None:
    img = _surface(name)
    buf = memoryview(data).cast("B")
    h, w = img.shape[:2]
    if buf.nbytes != w * h * 4:
        raise ValueError(f"data length {buf.nbytes} != surface size {w * h * 4} (w={w} h={h})")
    img[:] = np.frombuffer(buf, np.uint8).reshape(h, w, 4)
    return None


def surface_flip(name: str, flip_x: int, flip_y: int) -> None:
    img = _surface(name)
    out = img
    if flip_x:
        out = out[:, ::-1]
    if flip_y:
        out = out[::-1]
    img[:] = out.copy()
    return None


def surface_rotate_90(src: str, dst: str, times: int) -> tuple[int, int]:
    s = _surface(src, "source")
    times = _i(times) % 4
    # identisch zur Indexrechnung in wiitoolsmodule.c (1 = np.rot90 k=1, 3 = k=3)
    out = np.ascontiguousarray(np.rot90(s, k=times))
    _G.images[dst] = out
    return (out.shape[1], out.shape[0])
