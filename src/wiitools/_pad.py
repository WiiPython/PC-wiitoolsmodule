"""GameCube controller (PAD), emulated with keyboard/gamepads."""
from __future__ import annotations

import time

from ._config import cfg
from ._input import inp, VState

PAD_BUTTON_LEFT = 0x0001
PAD_BUTTON_RIGHT = 0x0002
PAD_BUTTON_DOWN = 0x0004
PAD_BUTTON_UP = 0x0008
PAD_TRIGGER_Z = 0x0010
PAD_TRIGGER_R = 0x0020
PAD_TRIGGER_L = 0x0040
PAD_BUTTON_A = 0x0100
PAD_BUTTON_B = 0x0200
PAD_BUTTON_X = 0x0400
PAD_BUTTON_Y = 0x0800
PAD_BUTTON_MENU = 0x1000
PAD_BUTTON_START = 0x1000
PAD_CHAN_ALL = -1
PAD_CHAN0 = 0
PAD_CHAN1 = 1
PAD_CHAN2 = 2
PAD_CHAN3 = 3
PAD_CHANMAX = 4

_CHAN_BITS = (0x80000000, 0x40000000, 0x20000000, 0x10000000)
_ERR_NONE, _ERR_NO_CONTROLLER = 0, -1
_KEYS = ("button", "stickX", "stickY", "substickX", "substickY",
         "triggerL", "triggerR", "analogA", "analogB", "err")


class _P:
    inited = False
    held = [0, 0, 0, 0]
    prev = [0, 0, 0, 0]
    down = [0, 0, 0, 0]
    up = [0, 0, 0, 0]
    analog = [dict.fromkeys(_KEYS, 0) for _ in range(4)]
    status = [dict(dict.fromkeys(_KEYS, 0), err=_ERR_NO_CONTROLLER) for _ in range(4)]
    sampling_cb = False
    sampling_t = 0.0


def _status_from_vstate(st: VState | None) -> dict:
    if st is None:
        return dict(dict.fromkeys(_KEYS, 0), err=_ERR_NO_CONTROLLER)
    b = st.btn
    m = {"left": PAD_BUTTON_LEFT, "right": PAD_BUTTON_RIGHT, "down": PAD_BUTTON_DOWN,
         "up": PAD_BUTTON_UP, "z": PAD_TRIGGER_Z, "r": PAD_TRIGGER_R, "l": PAD_TRIGGER_L,
         "a": PAD_BUTTON_A, "b": PAD_BUTTON_B, "x": PAD_BUTTON_X, "y": PAD_BUTTON_Y,
         "plus": PAD_BUTTON_START}
    bits = 0
    for name, mask in m.items():
        if name in b:
            bits |= mask

    def s8(v: float) -> int:
        return max(-128, min(127, int(round(v * 100))))

    return {"button": bits, "stickX": s8(st.lx), "stickY": s8(st.ly),
            "substickX": s8(st.rx), "substickY": s8(st.ry),
            "triggerL": int(round(st.lt * 255)), "triggerR": int(round(st.rt * 255)),
            "analogA": 255 if "a" in b else 0, "analogB": 255 if "b" in b else 0,
            "err": _ERR_NONE}


def PAD_Init() -> int:
    inp.start()
    _P.inited = True
    return 1


def PAD_Sync() -> int:
    return 1


def PAD_ScanPads() -> int:
    from ._display import display
    display.pump()
    if not _P.inited:
        return 0
    connected = 0
    for ch in range(4):
        s = _status_from_vstate(inp.state(ch, "pad"))
        _P.analog[ch] = s
        _P.prev[ch] = _P.held[ch]
        _P.held[ch] = s["button"] if s["err"] == _ERR_NONE else 0
        _P.down[ch] = _P.held[ch] & ~_P.prev[ch]
        _P.up[ch] = _P.prev[ch] & ~_P.held[ch]
        if s["err"] == _ERR_NONE:
            connected |= 1 << ch
    return connected


def PAD_Read() -> tuple[int, list[dict]]:
    from ._display import display
    display.pump()
    mask = 0
    for ch in range(4):
        st = inp.state(ch, "sys") if _P.inited else None
        _P.status[ch] = _status_from_vstate(st)
        if _P.status[ch]["err"] == _ERR_NONE:
            mask |= _CHAN_BITS[ch]
    return mask, [dict(s) for s in _P.status]


def PAD_Reset(mask: int) -> int:
    return 1


def PAD_Recalibrate(mask: int) -> int:
    return 1


def _clamp_stick(x: int, y: int, lo: int, hi: int) -> tuple[int, int]:
    def one(v: int) -> int:
        if -lo < v < lo:
            return 0
        v = v - lo if v > 0 else v + lo
        return max(-hi, min(hi, v))
    return one(x), one(y)


def PAD_Clamp() -> list[dict]:
    for s in _P.status:
        s["stickX"], s["stickY"] = _clamp_stick(s["stickX"], s["stickY"], 15, 72 - 15)
        s["substickX"], s["substickY"] = _clamp_stick(s["substickX"], s["substickY"], 15, 59 - 15)
        for k in ("triggerL", "triggerR"):
            v = s[k]
            s[k] = 0 if v <= 30 else min(180, v) - 30
    return [dict(s) for s in _P.status]


def PAD_ControlMotor(chan: int, cmd: int) -> None:
    inp.rumble(chan, cmd == 1)


def PAD_SetSpec(spec: int) -> None:
    return None


def _query(button: int, chan: int, arr: list[int]) -> int:
    chans = range(4) if chan < 0 else ([chan] if chan < 4 else [])
    return 1 if any(arr[c] & (button & 0xFFFF) for c in chans) else 0


def PAD_ButtonsUp(button: int, chan: int) -> int:
    return _query(button, chan, _P.up)


def PAD_ButtonsDown(button: int, chan: int) -> int:
    return _query(button, chan, _P.down)


def PAD_ButtonsHeld(button: int, chan: int) -> int:
    return _query(button, chan, _P.held)


def _an(pad: int, key: str) -> int:
    return int(_P.analog[pad][key]) if 0 <= pad < 4 else 0


def PAD_StickX(pad: int) -> int:
    return _an(pad, "stickX")


def PAD_StickY(pad: int) -> int:
    return _an(pad, "stickY")


def PAD_SubStickX(pad: int) -> int:
    return _an(pad, "substickX")


def PAD_SubStickY(pad: int) -> int:
    return _an(pad, "substickY")


def PAD_TriggerL(pad: int) -> int:
    return _an(pad, "triggerL")


def PAD_TriggerR(pad: int) -> int:
    return _an(pad, "triggerR")


def PAD_SetSamplingCallback(enable: bool) -> None:
    _P.sampling_cb = bool(enable)
    _P.sampling_t = time.perf_counter()


def PAD_GetSamplingEvent() -> int:
    """The PAD sampling callback fires once per field on Wii."""
    if not _P.sampling_cb:
        return 0
    now = time.perf_counter()
    n = int((now - _P.sampling_t) * cfg.hz)
    _P.sampling_t += n / cfg.hz
    return n
