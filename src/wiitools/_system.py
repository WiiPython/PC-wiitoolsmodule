"""CONF, SYS, CON, memory, c_run, init(), and WiiStdin."""
from __future__ import annotations

import ctypes
import os
import select
import shutil
import struct
import sys
import threading
import time

from ._config import cfg
from ._input import inp

# ----------------------------------------------------------------- Konstanten
SYS_RESTART = 0
SYS_HOTRESET = 1
SYS_SHUTDOWN = 2
SYS_RETURNTOMENU = 3
SYS_POWEROFF = 4
SYS_POWEROFF_STANDBY = 5
SYS_POWEROFF_IDLE = 6

_CONF_ENOENT = -0x6002
_CONF_BIGARRAY, _CONF_SMALLARRAY, _CONF_BYTE, _CONF_SHORT, _CONF_LONG, _CONF_BOOL = 1, 2, 3, 4, 5, 7
_TB_CLOCK = 60_750_000           # Wii-Timebase (Bus 243 MHz / 4)
_EPOCH_2000 = 946684800          # The Wii RTC counts from 2000-01-01.
_MEM1, _MEM2 = 24 * 1024 * 1024, 64 * 1024 * 1024
_T0 = time.perf_counter()


# ----------------------------------------------------------------- CONF
def _region() -> tuple[int, int, int]:
    """(region, area, video) passend zur Sprache."""
    lang = cfg.language
    if lang == 0:
        return 0, 0, 0          # JP / JPN / NTSC
    if lang == 1:
        return 1, 1, 0          # US / USA / NTSC
    if lang == 9:
        return 4, 7, 0          # KR
    return 2, 2, 1              # EU / EUR / PAL


def _conf_table() -> dict[str, tuple[int, bytes]]:
    nick = cfg.nickname.encode("utf-16-be")[:20]
    region, area, _video = _region()
    return {
        "IPL.LNG": (_CONF_BYTE, bytes([cfg.language])),
        "IPL.AR": (_CONF_BYTE, bytes([1 if cfg.widescreen else 0])),
        "IPL.SND": (_CONF_BYTE, bytes([_SYS["sound"]])),
        "IPL.PGS": (_CONF_BYTE, bytes([0])),
        "IPL.E60": (_CONF_BYTE, bytes([1])),
        "IPL.SSV": (_CONF_BYTE, bytes([1])),
        "IPL.EULA": (_CONF_BOOL, bytes([1])),
        "IPL.IDL": (_CONF_SMALLARRAY, bytes([0, 0])),
        "IPL.CB": (_CONF_LONG, struct.pack(">I", _counter_bias())),
        "IPL.DH": (_CONF_BYTE, bytes([0])),
        "IPL.NIK": (_CONF_SMALLARRAY, nick.ljust(20, b"\0") + struct.pack(">H", len(nick) // 2)),
        "IPL.SADR": (_CONF_BIGARRAY, bytes([area]) + bytes(0x1007 - 1)),
        "BT.SENS": (_CONF_LONG, struct.pack(">I", 3)),
        "BT.BAR": (_CONF_BYTE, bytes([0])),
        "BT.SPKV": (_CONF_BYTE, bytes([0x58])),
        "BT.MOT": (_CONF_BYTE, bytes([1])),
        "NET.WCFG": (_CONF_LONG, struct.pack(">I", 0)),
        "SYS.REGION": (_CONF_BYTE, bytes([region])),
    }


def _counter_bias() -> int:
    return int(time.time()) - _EPOCH_2000


def CONF_Init() -> int:
    return 0


def CONF_GetLength(name: str) -> int:
    e = _conf_table().get(name)
    return len(e[1]) if e else _CONF_ENOENT


def CONF_GetType(name: str) -> int:
    e = _conf_table().get(name)
    return e[0] if e else _CONF_ENOENT


def CONF_Get(name: str) -> bytes:
    e = _conf_table().get(name)
    if e is None:
        raise KeyError("CONF entry not found")
    return e[1]


def CONF_GetShutdownMode() -> int: return 0
def CONF_GetIdleLedMode() -> int: return 0
def CONF_GetProgressiveScan() -> int: return 0
def CONF_GetEuRGB60() -> int: return 1
def CONF_GetIRSensitivity() -> int: return 3
def CONF_GetSensorBarPosition() -> int: return 0
def CONF_GetPadSpeakerVolume() -> int: return 0x58
def CONF_GetPadMotorMode() -> int: return 1
def CONF_GetSoundMode() -> int: return 1
def CONF_GetLanguage() -> int: return cfg.language
def CONF_GetScreenSaverMode() -> int: return 1
def CONF_GetAspectRatio() -> int: return 1 if cfg.widescreen else 0
def CONF_GetEULA() -> int: return 1
def CONF_GetWiiConnect24() -> int: return 0
def CONF_GetRegion() -> int: return _region()[0]
def CONF_GetArea() -> int: return _region()[1]
def CONF_GetVideo() -> int: return _region()[2]
def CONF_GetCounterBias() -> int: return _counter_bias()
def CONF_GetDisplayOffsetH() -> int: return 0
def CONF_GetNickName() -> str: return cfg.nickname
def CONF_GetParentalPassword() -> str | None: return None
def CONF_GetParentalAnswer() -> str | None: return None


def CONF_GetPadDevices() -> int:
    return sum(1 for c in range(4) if inp.connected(c))


# ----------------------------------------------------------------- SYS
_SYS = {"counter_bias": None, "display_offset": 0, "eurgb60": 1, "language": None,
        "progressive": 0, "sound": 1, "video": None, "gbs": 0, "wireless": {}}


def SYS_Time() -> int:
    return int((time.perf_counter() - _T0) * _TB_CLOCK)


def SYS_ResetButtonDown() -> int:
    return 1 if inp.key_held("reset") else 0


def SYS_GetHollywoodRevision() -> int: return 0x11
def SYS_GetCounterBias() -> int:
    v = _SYS["counter_bias"]
    return _counter_bias() if v is None else v
def SYS_SetCounterBias(bias: int) -> None: _SYS["counter_bias"] = int(bias) & 0xFFFFFFFF
def SYS_GetDisplayOffsetH() -> int: return _SYS["display_offset"]
def SYS_SetDisplayOffsetH(offset: int) -> None: _SYS["display_offset"] = ((int(offset) + 128) % 256) - 128
def SYS_GetEuRGB60() -> int: return _SYS["eurgb60"]
def SYS_SetEuRGB60(enable: int) -> None: _SYS["eurgb60"] = int(enable) & 0xFF
def SYS_GetLanguage() -> int:
    v = _SYS["language"]
    return cfg.language if v is None else v
def SYS_SetLanguage(lang: int) -> None: _SYS["language"] = int(lang) & 0xFF
def SYS_GetProgressiveScan() -> int: return _SYS["progressive"]
def SYS_SetProgressiveScan(enable: int) -> None: _SYS["progressive"] = int(enable) & 0xFF
def SYS_GetSoundMode() -> int: return _SYS["sound"]
def SYS_SetSoundMode(mode: int) -> None: _SYS["sound"] = int(mode) & 0xFF
def SYS_GetVideoMode() -> int:
    v = _SYS["video"]
    return _region()[2] if v is None else v
def SYS_SetVideoMode(mode: int) -> None: _SYS["video"] = int(mode) & 0xFF
def SYS_GetWirelessID(chan: int) -> int: return _SYS["wireless"].get(int(chan), 0)
def SYS_SetWirelessID(chan: int, id: int) -> None: _SYS["wireless"][int(chan)] = int(id) & 0xFFFF  # noqa: A002
def SYS_GetGBSMode() -> int: return _SYS["gbs"]
def SYS_SetGBSMode(mode: int) -> None: _SYS["gbs"] = int(mode) & 0xFFFF
def SYS_GetFontEncoding() -> int: return 1 if cfg.language == 0 else 0


def _meminfo() -> tuple[int, int]:
    """(available, process RSS), in bytes."""
    avail = rss = 0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) * 1024
    except OSError:
        pass
    try:
        with open("/proc/self/statm") as f:
            rss = int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError):
        pass
    return avail, rss


def SYS_GetArena1Size() -> int:
    return min(_meminfo()[0], _MEM1)


def SYS_GetArena2Size() -> int:
    avail = _meminfo()[0]
    return min(max(0, avail - _MEM1), _MEM2)


def mem_free() -> dict:
    """Host memory limited to Wii-sized regions (MEM1 24 MB, MEM2 64 MB)."""
    avail, rss = _meminfo()
    arena1 = min(avail, _MEM1)
    arena2 = min(max(0, avail - _MEM1), _MEM2)
    return {"usable": arena1 + arena2, "freelist": 0, "arena1": arena1, "arena2": arena2,
            "arena_used": rss, "arena_total": rss}


def SYS_STDIO_Report(enable: bool) -> None:
    return None


def SYS_Report(msg: str) -> None:
    sys.stderr.write(str(msg))
    sys.stderr.flush()


def SYS_ResetSystem(reset: int, code: int = 0, force_menu: bool = False) -> None:
    reset = int(reset)
    if reset == SYS_SHUTDOWN:
        return None
    if reset == SYS_HOTRESET:
        sys.stdout.flush()
        os.execv(sys.executable, [sys.executable] + list(getattr(sys, "orig_argv", sys.argv)[1:]))
    raise SystemExit(0)


class _Ev:
    power_cb = False
    reset_cb = False
    power = 0
    reset = 0
    alarm = 0
    lock = threading.Lock()


def _on_key(name: str) -> None:
    with _Ev.lock:
        if name == "power" and _Ev.power_cb:
            _Ev.power += 1
        elif name == "reset" and _Ev.reset_cb:
            _Ev.reset += 1


def _on_quit() -> bool:
    if _Ev.power_cb:
        with _Ev.lock:
            _Ev.power += 1
        return True
    return False


inp.key_handlers.append(_on_key)
inp.quit_handlers.append(_on_quit)


def SYS_SetPowerCallback(enable: bool) -> None:
    _Ev.power_cb = bool(enable)


def SYS_GetPowerEvent() -> int:
    with _Ev.lock:
        n, _Ev.power = _Ev.power, 0
    return n


def SYS_SetResetCallback(enable: bool) -> None:
    _Ev.reset_cb = bool(enable)


def SYS_GetResetEvent() -> int:
    with _Ev.lock:
        n, _Ev.reset = _Ev.reset, 0
    return n


# ---- Alarme ----------------------------------------------------------------
class _Alarm:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None

    def cancel(self) -> None:
        self.stop.set()
        self.stop = threading.Event()

    def start(self, first: float, period: float | None) -> None:
        self.cancel()
        stop = self.stop

        def run() -> None:
            if stop.wait(max(0.0, first)):
                return
            while True:
                with _Ev.lock:
                    _Ev.alarm += 1
                if not period or stop.wait(period):
                    return

        self.thread = threading.Thread(target=run, name="wiitools-alarm", daemon=True)
        self.thread.start()


_alarms: dict[int, _Alarm] = {}
_next_alarm = [1]


def SYS_CreateAlarm() -> int:
    h = _next_alarm[0]
    _next_alarm[0] += 1
    _alarms[h] = _Alarm()
    return h


def SYS_SetAlarm(handle: int, seconds: float) -> int:
    a = _alarms.get(int(handle))
    if a is None:
        return -1
    a.start(float(seconds), None)
    return 0


def SYS_SetPeriodicAlarm(handle: int, start_s: float, period_s: float) -> int:
    a = _alarms.get(int(handle))
    if a is None:
        return -1
    a.start(float(start_s), max(1e-4, float(period_s)))
    return 0


def SYS_RemoveAlarm(handle: int) -> int:
    a = _alarms.pop(int(handle), None)
    if a is None:
        return -1
    a.cancel()
    return 0


def SYS_CancelAlarm(handle: int) -> int:
    a = _alarms.get(int(handle))
    if a is None:
        return -1
    a.cancel()
    return 0


def SYS_GetAlarmEvent() -> int:
    with _Ev.lock:
        n, _Ev.alarm = _Ev.alarm, 0
    return n


# ----------------------------------------------------------------- Console
class _Con:
    col = 0
    row = 0


def _track(text: str) -> None:
    cols, rows = CON_GetMetrics()
    for ch in text:
        if ch == "\n":
            _Con.col, _Con.row = 0, _Con.row + 1
        elif ch == "\r":
            _Con.col = 0
        else:
            _Con.col += 1
            if _Con.col >= cols:
                _Con.col, _Con.row = 0, _Con.row + 1
    _Con.row = min(_Con.row, max(0, rows - 1))


def terminal_print(msg: str) -> None:
    sys.stdout.write(msg)
    sys.stdout.flush()
    _track(msg)


def CON_GetMetrics() -> tuple[int, int]:
    size = shutil.get_terminal_size((80, 24))
    return (size.columns, size.lines)


def CON_GetPosition() -> tuple[int, int]:
    """Cursor position based on characters written through terminal_print()."""
    return (_Con.col, _Con.row)


def CON_EnableGecko(channel: int, safe: bool = False) -> None:
    return None


# ----------------------------------------------------------------- c_run
def _mapped(addr: int, length: int, need_exec: bool) -> bool | None:
    """Check via /proc/self/maps whether [addr, addr+len) is mapped. None = unknown."""
    try:
        with open("/proc/self/maps") as f:
            lines = f.readlines()
    except OSError:
        return None
    end = addr + max(1, length)
    for line in lines:
        rng, perms = line.split()[:2]
        lo, hi = (int(x, 16) for x in rng.split("-"))
        if lo <= addr and end <= hi:
            return perms[0] == "r" and (not need_exec or perms[2] == "x")
    return False


def c_run(func_addr: int, *args: int | bytes | bytearray) -> int:
    """Native Funktion an *func_addr* (z. B. aus ctypes) mit bis zu 8 Wort-Argumenten aufrufen.

    PC equivalent of the PowerPC EABI call: all arguments are passed as
    Pass integers as machine words (size_t), and bytes/bytearray as pointers to
    their buffers; the return value is an unsigned machine word.
    """
    if not isinstance(func_addr, int):
        raise TypeError("c_run(func_addr, *args): func_addr must be int")
    if len(args) > 8:
        raise TypeError("c_run supports at most 8 arguments")
    addr = func_addr
    if addr == 0:
        raise ValueError("c_run: NULL function address")
    if addr < 0 or _mapped(addr, 4, need_exec=True) is False:
        raise ValueError(f"c_run: function address 0x{addr & ((1 << 64) - 1):08x} outside valid RAM")
    words: list[int] = []
    keep: list = []
    for i, o in enumerate(args, start=1):
        if isinstance(o, bool) or isinstance(o, int):
            words.append(int(o) & ((1 << (8 * ctypes.sizeof(ctypes.c_size_t))) - 1))
        elif isinstance(o, bytes):
            buf = ctypes.c_char_p(o)
            keep.append(buf)
            words.append(ctypes.cast(buf, ctypes.c_void_p).value or 0)
        elif isinstance(o, bytearray):
            buf = (ctypes.c_char * len(o)).from_buffer(o) if o else ctypes.create_string_buffer(0)
            keep.append(buf)
            words.append(ctypes.addressof(buf))
        else:
            raise TypeError(f"c_run: argument {i} must be int or bytes-like")
    words += [0] * (8 - len(words))
    proto = ctypes.CFUNCTYPE(ctypes.c_size_t, *([ctypes.c_size_t] * 8))
    return int(proto(addr)(*words))


def _addr_range_ok(addr: int, length: int) -> bool:
    if addr <= 0:
        return False
    r = _mapped(addr, length, need_exec=False)
    return True if r is None else r


# ----------------------------------------------------------------- WiiStdin
class WiiStdin:
    """sys.stdin replacement. On PC, reads directly from the real console."""

    def readline(self, *args) -> str:
        src = sys.__stdin__
        if src is None:
            return "\n"
        try:
            fd = src.fileno()
        except (AttributeError, OSError, ValueError):
            return src.readline()

        # Keep the pygame event loop alive while waiting for terminal input.
        # Otherwise input() blocks the main thread and leaves the emulation
        # window unresponsive until the user submits a line.
        from ._display import display
        while not select.select([fd], [], [], 0.05)[0]:
            display.pump()
        display.pump()
        line = src.readline()
        return line if line else "\n"

    def read(self, *args) -> str:
        return self.readline()

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        return 0


WiiStdin.__module__ = "wiitools"


# ----------------------------------------------------------------- init()
def init() -> None:
    from . import _gfx
    from ._fs import fatInitDefault
    from ._net import net_init
    from ._pad import PAD_Init
    from ._wpad import WPAD_Init
    sys.stdin = WiiStdin()
    _gfx._console_init(clear=False)
    fatInitDefault()
    net_init()
    WPAD_Init()
    PAD_Init()
    return None
