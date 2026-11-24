"""AUDIO (AI-DMA), playback through pygame.mixer."""
from __future__ import annotations

import ctypes
import math
import threading
import time

import numpy as np

from ._display import display, pygame

AI_SAMPLERATE_32KHZ = 0
AI_SAMPLERATE_48KHZ = 1
_MIX_RATE = 48000


class _A:
    inited = False
    mixer = None          # True/False nach erstem Versuch
    rate = AI_SAMPLERATE_48KHZ
    dma_addr = 0
    dma_len = 0
    dma_on = False
    dma_start_t = 0.0
    channel = None
    cb = False
    events = 0
    timer_stop: threading.Event | None = None
    lock = threading.Lock()


def _mixer_ok() -> bool:
    if _A.mixer is None:
        _A.mixer = False
        if pygame is not None:
            try:
                pygame.mixer.init(frequency=_MIX_RATE, size=-16, channels=2, buffer=1024)
                _A.mixer = True
            except Exception:
                _A.mixer = False
    return bool(_A.mixer)


def _play(stereo: np.ndarray, rate: int, loops: int):
    """stereo: int16 (n, 2) in Host-Byteorder."""
    if not _mixer_ok() or len(stereo) == 0:
        return None
    if rate != _MIX_RATE:
        n_out = max(1, int(len(stereo) * _MIX_RATE / rate))
        x = np.linspace(0, len(stereo) - 1, n_out)
        stereo = np.stack([np.interp(x, np.arange(len(stereo)), stereo[:, c]) for c in (0, 1)],
                          axis=1).astype(np.int16)
    snd = pygame.sndarray.make_sound(np.ascontiguousarray(stereo))
    return snd.play(loops=loops)


def _hz() -> int:
    return 32000 if _A.rate == AI_SAMPLERATE_32KHZ else 48000


def _require_init() -> None:
    if not _A.inited:
        raise RuntimeError("AUDIO is not initialized; call the matching *_Init function first")


def AUDIO_Init() -> None:
    _A.inited = True
    _mixer_ok()
    return None


def AUDIO_InitDMA(startaddr: int, len: int) -> None:  # noqa: A002
    from ._system import _addr_range_ok
    startaddr, length = int(startaddr), int(len)
    _require_init()
    if not _addr_range_ok(startaddr, length):
        raise ValueError("AUDIO_InitDMA: startaddr/len outside valid RAM")
    if (startaddr & 31) or (length & 31):
        raise ValueError("AUDIO_InitDMA: startaddr and len must be 32-byte aligned")
    _A.dma_addr, _A.dma_len = startaddr, length
    return None


def AUDIO_StartDMA() -> None:
    AUDIO_StopDMA()
    if not _A.dma_addr or not _A.dma_len:
        return None
    raw = ctypes.string_at(_A.dma_addr, _A.dma_len)
    # Wii-AI liest 16-bit Big-Endian Stereo
    pcm = np.frombuffer(raw, dtype=">i2").astype(np.int16).reshape(-1, 2)
    _A.channel = _play(pcm, _hz(), loops=-1)
    _A.dma_on = True
    _A.dma_start_t = time.perf_counter()
    period = (_A.dma_len / 4) / _hz()
    stop = threading.Event()
    _A.timer_stop = stop

    def tick() -> None:
        while not stop.wait(period):
            if _A.cb:
                with _A.lock:
                    _A.events += 1

    threading.Thread(target=tick, name="wiitools-ai-dma", daemon=True).start()
    return None


def AUDIO_StopDMA() -> None:
    if _A.timer_stop is not None:
        _A.timer_stop.set()
        _A.timer_stop = None
    if _A.channel is not None:
        try:
            _A.channel.stop()
        except Exception:
            pass
        _A.channel = None
    _A.dma_on = False
    return None


def AUDIO_GetDMAEnableFlag() -> int:
    return 1 if _A.dma_on else 0


def AUDIO_GetDMABytesLeft() -> int:
    if not _A.dma_on or not _A.dma_len:
        return 0
    played = int((time.perf_counter() - _A.dma_start_t) * _hz() * 4)
    return (_A.dma_len - played % _A.dma_len) & ~31


def AUDIO_GetDMALength() -> int:
    return _A.dma_len


def AUDIO_GetDMAStartAddr() -> int:
    return _A.dma_addr


def AUDIO_SetDSPSampleRate(rate: int) -> None:
    _A.rate = int(rate) & 0xFF
    return None


def AUDIO_GetDSPSampleRate() -> int:
    return _A.rate


def AUDIO_RegisterDMACallback(enable: bool) -> None:
    _A.cb = bool(enable)
    return None


def AUDIO_GetDMAEvent() -> int:
    with _A.lock:
        n, _A.events = _A.events, 0
    return n


def audio_play_tone(freq: float = 440.0, ms: int = 500, volume: int = 8000) -> None:
    freq, ms, volume = float(freq), int(ms), int(volume)
    ms = max(1, min(3000, ms))
    volume = max(0, min(32767, volume))
    freq = max(1.0, freq)
    frames = (48000 * ms) // 1000
    nbytes = max(32, min(1048544, (frames * 4) & ~31))
    frames = nbytes // 4
    t = np.arange(frames, dtype=np.float64)
    mono = (volume * np.sin(2.0 * math.pi * freq / 48000.0 * t)).astype(np.int16)
    if not _A.inited:
        AUDIO_Init()
    AUDIO_StopDMA()
    ch = _play(np.stack([mono, mono], axis=1), 48000, loops=0)
    display.sleep(ms / 1000 + 0.02)
    if ch is not None:
        ch.stop()
    return None
