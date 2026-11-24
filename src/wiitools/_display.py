"""Window, presentation, and VSync timing (pygame; headless without pygame)."""
from __future__ import annotations

import os
import time

import numpy as np

from ._config import cfg

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:  # pragma: no cover - depends on the installation
    import pygame
except Exception:  # pygame unavailable -> headless
    pygame = None


class _Display:
    def __init__(self) -> None:
        self.window = None
        self.opened = False
        self._t0 = time.perf_counter()
        self._last_vsync_index = -1
        self._view = (0, 0, 1, 1)  # Image area in the window (x, y, w, h).
        self.event_handlers: list = []
        self.last_frame: np.ndarray | None = None

    # ------------------------------------------------------------------ setup
    @property
    def available(self) -> bool:
        return pygame is not None and not cfg.headless

    def fb_size(self) -> tuple[int, int]:
        return cfg.fb_size

    def ensure(self) -> bool:
        """Open the window once. Returns False when running headless."""
        if self.opened:
            return self.window is not None
        self.opened = True
        if not self.available:
            return False
        try:
            pygame.display.init()
            pygame.joystick.init()
            fw, fh = self.fb_size()
            disp_w = round(fh * 16 / 9) if cfg.widescreen else fw
            size = (max(1, int(disp_w * cfg.scale)), max(1, int(fh * cfg.scale)))
            self.window = pygame.display.set_mode(size, pygame.RESIZABLE)
            pygame.display.set_caption("wiitools (PC)")
            self.window.fill((0, 0, 0))
            pygame.display.flip()
        except Exception as exc:  # z. B. kein Display vorhanden
            print(f"[wiitools] cannot open a window ({exc}); continuing headless")
            self.window = None
        return self.window is not None

    # ----------------------------------------------------------------- events
    def pump(self) -> None:
        if self.window is None:
            return
        for ev in pygame.event.get():
            if ev.type == pygame.VIDEORESIZE:
                self._redraw()
            for handler in self.event_handlers:
                handler(ev)

    # ------------------------------------------------------------ presentation
    def _compute_view(self) -> tuple[int, int, int, int]:
        ww, wh = self.window.get_size()
        fw, fh = self.fb_size()
        aspect = (16 / 9) if cfg.widescreen else (fw / fh)
        if ww / max(1, wh) > aspect:
            vh = wh
            vw = int(round(wh * aspect))
        else:
            vw = ww
            vh = int(round(ww / aspect))
        return ((ww - vw) // 2, (wh - vh) // 2, max(1, vw), max(1, vh))

    def present(self, rgb: np.ndarray) -> None:
        self.last_frame = rgb
        if self.window is None:
            return
        self._redraw()

    def _redraw(self) -> None:
        if self.window is None or self.last_frame is None:
            return
        rgb = self.last_frame
        h, w = rgb.shape[:2]
        surf = pygame.image.frombuffer(np.ascontiguousarray(rgb).tobytes(), (w, h), "RGB")
        self._view = self._compute_view()
        x, y, vw, vh = self._view
        self.window.fill((0, 0, 0))
        self.window.blit(pygame.transform.scale(surf, (vw, vh)), (x, y))
        pygame.display.flip()

    def mouse_fb(self) -> tuple[float, float] | None:
        """Mouse position in framebuffer pixels, or None when outside/unfocused."""
        if self.window is None or not pygame.mouse.get_focused():
            return None
        mx, my = pygame.mouse.get_pos()
        x, y, vw, vh = self._compute_view()
        fw, fh = self.fb_size()
        fx = (mx - x) / vw * fw
        fy = (my - y) / vh * fh
        if 0 <= fx < fw and 0 <= fy < fh:
            return fx, fy
        return None

    # ------------------------------------------------------------------ timing
    def wait_vsync(self) -> None:
        """Wait until the next vertical retrace (fixed 1/Hz interval)."""
        period = 1.0 / cfg.hz
        now = time.perf_counter() - self._t0
        idx = int(now / period) + 1
        if idx <= self._last_vsync_index:
            idx = self._last_vsync_index + 1
        target = idx * period
        while True:
            self.pump()
            remaining = target - (time.perf_counter() - self._t0)
            if remaining <= 0:
                break
            time.sleep(min(remaining, 0.005))
        self._last_vsync_index = idx

    def sleep(self, seconds: float) -> None:
        end = time.perf_counter() + seconds
        while True:
            self.pump()
            remaining = end - time.perf_counter()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.01 if self.window is not None else remaining))


display = _Display()
