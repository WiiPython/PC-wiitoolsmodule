"""Software rasterizer (numpy) for the screen (GX emulation), surfaces, and XFB.

Drei Zielarten, entsprechend den drei Pfaden in wiitoolsmodule.c:

* ``gx``  – EFB-Emulation: Alpha-Blending SRCALPHA/INVSRCALPHA, Alpha-Compare
            ``a >= 16`` (wie GX_SetAlphaCompare im rendering_init), logische
            Coordinates are scaled through the viewport/scissor (set_screen_size).
* ``sw``  – Off-screen surfaces: exact blend formula from surface_blend_pixel().
* ``xfb`` – direkter Framebuffer-Zugriff ohne GX (Konsolenmodus): Pixel mit
            Alpha 0 pixels are skipped; others are written without blending.
"""
from __future__ import annotations

import math

import numpy as np

from ._font import FONT8X8_BASIC

_GLYPHS = np.zeros((128, 8, 8), dtype=bool)
for _i, _g in enumerate(FONT8X8_BASIC):
    for _r, _bits in enumerate(_g):
        for _c in range(8):
            _GLYPHS[_i, _r, _c] = bool((_bits >> _c) & 1)


class Target:
    """A drawing target. ``arr`` is (H, W, 3) for gx/xfb and (H, W, 4) for sw.

    Logical coordinate L maps to pixel P = o + s * L; ``center`` is the sample
    point within a pixel (0.5 for GX, 0.0 for software renderers that use
    integer pixels, as in the C code).
    """

    __slots__ = ("arr", "kind", "s", "ox", "oy", "clip", "center")

    def __init__(self, arr: np.ndarray, kind: str, s: float = 1.0, ox: float = 0.0,
                 oy: float = 0.0, clip: tuple[int, int, int, int] | None = None):
        self.arr = arr
        self.kind = kind
        self.s = s
        self.ox = ox
        self.oy = oy
        h, w = arr.shape[:2]
        if clip is None:
            clip = (0, 0, w, h)
        x0, y0, x1, y1 = clip
        self.clip = (max(0, x0), max(0, y0), min(w, x1), min(h, y1))
        self.center = 0.5 if kind == "gx" else 0.0


# --------------------------------------------------------------------------
# Compositing
# --------------------------------------------------------------------------

def _composite(t: Target, x0: int, y0: int, mask: np.ndarray, rgb, a) -> None:
    """Blend (rgb, a) into pixels in arr[y0:y0+h, x0:x0+w] wherever mask is true."""
    h, w = mask.shape
    if h == 0 or w == 0:
        return
    region = t.arr[y0:y0 + h, x0:x0 + w]
    a_full = np.broadcast_to(np.asarray(a, dtype=np.int32), (h, w))
    if t.kind == "gx":
        m = mask & (a_full >= 16)
    else:
        m = mask & (a_full != 0)
    if not m.any():
        return
    src = np.broadcast_to(np.asarray(rgb, dtype=np.int32), (h, w, 3))[m]
    sa = a_full[m]
    if t.kind == "xfb":
        region[m, :3] = src.astype(np.uint8)
        return
    if t.kind == "gx":
        dst = region[m].astype(np.int32)
        sa3 = sa[:, None]
        region[m] = ((src * sa3 + dst * (255 - sa3)) // 255).astype(np.uint8)
        return
    # sw: surface_blend_pixel()
    dst = region[m].astype(np.int64)
    da = dst[:, 3]
    out = np.empty_like(dst)
    out[:, :3] = src
    out[:, 3] = sa
    blend = ~((sa == 255) | (da == 0))
    if blend.any():
        sab = sa[blend].astype(np.int64)
        dab = da[blend]
        inv = 255 - sab
        oa = np.minimum(sab + dab * inv // 255, 255)
        for ch in range(3):
            sc = src[blend, ch].astype(np.int64)
            dc = dst[blend, ch]
            out[blend, ch] = (sc * sab + dc * dab * inv // 255) // oa
        out[blend, 3] = oa
    region[m] = out.astype(np.uint8)


# --------------------------------------------------------------------------
# Rasterization with inverse mapping
# --------------------------------------------------------------------------

def _grid(t: Target, lx0: float, ly0: float, lx1: float, ly1: float):
    """Logical bounding box -> (px0, py0, LX[1,w], LY[h,1]) or None."""
    cx0, cy0, cx1, cy1 = t.clip
    px0 = max(cx0, int(math.floor(t.ox + t.s * lx0)) - 1)
    py0 = max(cy0, int(math.floor(t.oy + t.s * ly0)) - 1)
    px1 = min(cx1, int(math.ceil(t.ox + t.s * lx1)) + 2)
    py1 = min(cy1, int(math.ceil(t.oy + t.s * ly1)) + 2)
    if px1 <= px0 or py1 <= py0:
        return None
    xs = (np.arange(px0, px1, dtype=np.float64) + t.center - t.ox) / t.s
    ys = (np.arange(py0, py1, dtype=np.float64) + t.center - t.oy) / t.s
    return px0, py0, xs[None, :], ys[:, None]


def _rot(angle_deg: float) -> tuple[float, float]:
    rad = float(angle_deg) * (math.pi / 180.0)
    return math.cos(rad), math.sin(rad)


def draw_rect(t: Target, x: int, y: int, w: int, h: int, rgba, angle_deg: float) -> None:
    if w <= 0 or h <= 0:
        return
    cx, cy = x + w * 0.5, y + h * 0.5
    hw, hh = w * 0.5, h * 0.5
    cs, sn = _rot(angle_deg)
    diag = math.sqrt(hw * hw + hh * hh) + 1.5
    g = _grid(t, cx - diag, cy - diag, cx + diag, cy + diag)
    if g is None:
        return
    px0, py0, LX, LY = g
    dx, dy = LX - cx, LY - cy
    lx = dx * cs + dy * sn
    ly = -dx * sn + dy * cs
    mask = (lx >= -hw) & (lx <= hw) & (ly >= -hh) & (ly <= hh)
    if t.kind == "gx":  # Pixel centers: half-open edges, as on the GPU.
        mask = (lx >= -hw) & (lx < hw) & (ly >= -hh) & (ly < hh)
    _composite(t, px0, py0, mask, rgba[:3], rgba[3])


def draw_circle(t: Target, x: int, y: int, radius: int, rgba) -> None:
    if radius <= 0:
        return
    g = _grid(t, x - radius, y - radius, x + radius + 1, y + radius + 1)
    if g is None:
        return
    px0, py0, LX, LY = g
    mask = (LX - x) ** 2 + (LY - y) ** 2 <= float(radius) * float(radius)
    _composite(t, px0, py0, mask, rgba[:3], rgba[3])


def draw_oval(t: Target, x: int, y: int, w: int, h: int, rgba, angle_deg: float) -> None:
    if w <= 0 or h <= 0:
        return
    cx, cy = x + w * 0.5, y + h * 0.5
    rx, ry = w * 0.5, h * 0.5
    cs, sn = _rot(angle_deg)
    diag = max(rx, ry) + 1.5
    g = _grid(t, cx - diag, cy - diag, cx + diag, cy + diag)
    if g is None:
        return
    px0, py0, LX, LY = g
    dx, dy = LX - cx, LY - cy
    lx = dx * cs + dy * sn
    ly = -dx * sn + dy * cs
    mask = (lx / rx) ** 2 + (ly / ry) ** 2 <= 1.0
    _composite(t, px0, py0, mask, rgba[:3], rgba[3])


# --------------------------------------------------------------------------
# Text (8x8-Font)
# --------------------------------------------------------------------------

def text_bytes(text: str) -> bytes:
    """As in the C code: UTF-8 bytes; each byte > 127 becomes '?'."""
    if "\x00" in text:
        raise ValueError("embedded null character")
    raw = text.encode("utf-8", "surrogateescape")
    return bytes(b if b < 128 else 0x3F for b in raw)


def text_length(text: str, size: int) -> int:
    scale = 1 if size <= 0 else size
    cur = maxw = 0
    for b in text_bytes(text):
        if b == 0x0A:
            maxw = max(maxw, cur)
            cur = 0
        else:
            cur += 8 * scale
    return max(maxw, cur)


def _text_bitmap(data: bytes) -> np.ndarray:
    lines = data.split(b"\n")
    cols = max((len(line) for line in lines), default=0)
    bm = np.zeros((9 * len(lines), max(1, 8 * cols)), dtype=bool)
    for li, line in enumerate(lines):
        for ci, ch in enumerate(line):
            bm[9 * li:9 * li + 8, 8 * ci:8 * ci + 8] = _GLYPHS[ch]
    return bm


def render_text(t: Target, x: int, y: int, text: str, size: int, shadow: int,
                rgba, angle_deg: float) -> None:
    data = text_bytes(text)
    if not data:
        return
    scale = 1 if size <= 0 else size
    shadow_off = max(1, scale // 4)
    bm = _text_bitmap(data)
    bh, bw = bm.shape
    cs, sn = _rot(angle_deg)
    ext_w = bw * scale + shadow_off
    ext_h = bh * scale + shadow_off
    corners = [(0, 0), (ext_w, 0), (0, ext_h), (ext_w, ext_h)]
    xs = [x + u * cs - v * sn for u, v in corners]
    ys = [y + u * sn + v * cs for u, v in corners]
    g = _grid(t, min(xs), min(ys), max(xs), max(ys))
    if g is None:
        return
    px0, py0, LX, LY = g
    dx, dy = LX - x, LY - y
    ux = dx * cs + dy * sn
    uy = -dx * sn + dy * cs

    def sample(offset: int) -> np.ndarray:
        iu = np.floor((ux - offset) / scale).astype(np.int64)
        iv = np.floor((uy - offset) / scale).astype(np.int64)
        ok = (iu >= 0) & (iu < bw) & (iv >= 0) & (iv < bh)
        return ok & bm[np.clip(iv, 0, bh - 1), np.clip(iu, 0, bw - 1)]

    if shadow:
        _composite(t, px0, py0, sample(shadow_off), (0, 0, 0), rgba[3])
    _composite(t, px0, py0, sample(0), rgba[:3], rgba[3])


# --------------------------------------------------------------------------
# Bilder
# --------------------------------------------------------------------------

def _next_pow2(v: int) -> int:
    p = 1
    while p < v:
        p <<= 1
    return p


def _tex_lookup(img: np.ndarray, u: np.ndarray, v: np.ndarray):
    """Nearest texel with GX_CLAMP on the power-of-two-padded texture."""
    ih, iw = img.shape[:2]
    tw, th = _next_pow2(iw), _next_pow2(ih)
    iu = np.clip(np.floor(u).astype(np.int64), 0, tw - 1)
    iv = np.clip(np.floor(v).astype(np.int64), 0, th - 1)
    ok = (iu < iw) & (iv < ih)
    px = img[np.minimum(iv, ih - 1), np.minimum(iu, iw - 1)]
    return ok, px


def blit_gx(t: Target, img: np.ndarray, sx: int, sy: int, sw: int, sh: int,
            dx: int, dy: int, dw: int, dh: int) -> None:
    """Texturiertes Quad (GX-Pfad von png_blit_region_scaled)."""
    if dw <= 0 or dh <= 0 or sw <= 0 or sh <= 0:
        return
    g = _grid(t, dx, dy, dx + dw, dy + dh)
    if g is None:
        return
    px0, py0, LX, LY = g
    inside = (LX >= dx) & (LX < dx + dw) & (LY >= dy) & (LY < dy + dh)
    u = np.broadcast_to(sx + (LX - dx) * (sw / dw), inside.shape)
    v = np.broadcast_to(sy + (LY - dy) * (sh / dh), inside.shape)
    ok, px = _tex_lookup(img, u, v)
    _composite(t, px0, py0, inside & ok, px[..., :3], px[..., 3])


def blit_quad(t: Target, img: np.ndarray, pts, sx: int, sy: int, sw: int, sh: int) -> None:
    """png_quad: two triangles (1,2,3) and (1,3,4) with affine texture coordinates."""
    if sw <= 0 or sh <= 0:
        return
    uv = [(sx, sy), (sx + sw, sy), (sx + sw, sy + sh), (sx, sy + sh)]
    for tri in ((0, 1, 2), (0, 2, 3)):
        (x1, y1), (x2, y2), (x3, y3) = (pts[i] for i in tri)
        den = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
        if abs(den) < 1e-12:
            continue
        g = _grid(t, min(x1, x2, x3), min(y1, y2, y3), max(x1, x2, x3), max(y1, y2, y3))
        if g is None:
            continue
        px0, py0, LX, LY = g
        w1 = ((y2 - y3) * (LX - x3) + (x3 - x2) * (LY - y3)) / den
        w2 = ((y3 - y1) * (LX - x3) + (x1 - x3) * (LY - y3)) / den
        w3 = 1.0 - w1 - w2
        inside = (w1 >= 0) & (w2 >= 0) & (w3 >= 0)
        (u1, v1), (u2, v2), (u3, v3) = (uv[i] for i in tri)
        u = w1 * u1 + w2 * u2 + w3 * u3
        v = w1 * v1 + w2 * v2 + w3 * v3
        ok, px = _tex_lookup(img, u, v)
        _composite(t, px0, py0, inside & ok, px[..., :3], px[..., 3])


def blit_fixed(t: Target, img: np.ndarray, sx: int, sy: int, sw: int, sh: int,
               dx: int, dy: int, dw: int, dh: int) -> None:
    """Software-Blit mit 16.16-Festkomma wie surface_sw_blit_img / XFB-Pfad."""
    if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
        return
    ih, iw = img.shape[:2]
    H, W = t.arr.shape[:2]
    sx_step = ((sw << 16) // dw) & 0xFFFFFFFF
    sy_step = ((sh << 16) // dh) & 0xFFFFFFFF
    tx = np.arange(dw, dtype=np.int64)
    ty = np.arange(dh, dtype=np.int64)
    dxi = dx + tx
    dyi = dy + ty
    sxi = sx + (((tx * sx_step) & 0xFFFFFFFF) >> 16)
    syi = sy + (((ty * sy_step) & 0xFFFFFFFF) >> 16)
    okx = (dxi >= 0) & (dxi < W) & (sxi >= 0) & (sxi < iw)
    oky = (dyi >= 0) & (dyi < H) & (syi >= 0) & (syi < ih)
    if not okx.any() or not oky.any():
        return
    # Determine the contiguous destination region.
    xa, xb = max(dx, 0), min(dx + dw, W)
    ya, yb = max(dy, 0), min(dy + dh, H)
    sel_x = slice(xa - dx, xb - dx)
    sel_y = slice(ya - dy, yb - dy)
    mask = oky[sel_y][:, None] & okx[sel_x][None, :]
    px = img[np.clip(syi[sel_y], 0, ih - 1)[:, None], np.clip(sxi[sel_x], 0, iw - 1)[None, :]]
    _composite(t, xa, ya, mask, px[..., :3], px[..., 3])
