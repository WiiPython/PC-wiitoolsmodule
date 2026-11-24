"""Wiimote (WPAD), emulated with keyboard, mouse, and gamepads."""
from __future__ import annotations

import collections
import math
import struct
import threading

from ._config import cfg
from ._input import inp, VState

# ----------------------------------------------------------------- Konstanten
WPAD_BUTTON_2 = 0x0001
WPAD_BUTTON_1 = 0x0002
WPAD_BUTTON_B = 0x0004
WPAD_BUTTON_A = 0x0008
WPAD_BUTTON_MINUS = 0x0010
WPAD_BUTTON_HOME = 0x0080
WPAD_BUTTON_LEFT = 0x0100
WPAD_BUTTON_RIGHT = 0x0200
WPAD_BUTTON_DOWN = 0x0400
WPAD_BUTTON_UP = 0x0800
WPAD_BUTTON_PLUS = 0x1000

WPAD_NUNCHUK_BUTTON_Z = 0x0001 << 16
WPAD_NUNCHUK_BUTTON_C = 0x0002 << 16

WPAD_CLASSIC_BUTTON_UP = 0x0001 << 16
WPAD_CLASSIC_BUTTON_LEFT = 0x0002 << 16
WPAD_CLASSIC_BUTTON_ZR = 0x0004 << 16
WPAD_CLASSIC_BUTTON_X = 0x0008 << 16
WPAD_CLASSIC_BUTTON_A = 0x0010 << 16
WPAD_CLASSIC_BUTTON_Y = 0x0020 << 16
WPAD_CLASSIC_BUTTON_B = 0x0040 << 16
WPAD_CLASSIC_BUTTON_ZL = 0x0080 << 16
WPAD_CLASSIC_BUTTON_FULL_R = 0x0200 << 16
WPAD_CLASSIC_BUTTON_PLUS = 0x0400 << 16
WPAD_CLASSIC_BUTTON_HOME = 0x0800 << 16
WPAD_CLASSIC_BUTTON_MINUS = 0x1000 << 16
WPAD_CLASSIC_BUTTON_FULL_L = 0x2000 << 16
WPAD_CLASSIC_BUTTON_DOWN = 0x4000 << 16
WPAD_CLASSIC_BUTTON_RIGHT = 0x8000 << 16

WPAD_GUITAR_HERO_3_BUTTON_STRUM_UP = 0x0001 << 16
WPAD_GUITAR_HERO_3_BUTTON_YELLOW = 0x0008 << 16
WPAD_GUITAR_HERO_3_BUTTON_GREEN = 0x0010 << 16
WPAD_GUITAR_HERO_3_BUTTON_BLUE = 0x0020 << 16
WPAD_GUITAR_HERO_3_BUTTON_RED = 0x0040 << 16
WPAD_GUITAR_HERO_3_BUTTON_ORANGE = 0x0080 << 16
WPAD_GUITAR_HERO_3_BUTTON_PLUS = 0x0400 << 16
WPAD_GUITAR_HERO_3_BUTTON_MINUS = 0x1000 << 16
WPAD_GUITAR_HERO_3_BUTTON_STRUM_DOWN = 0x4000 << 16

WPAD_DATA_BUTTONS = 0x01
WPAD_THRESH_DEFAULT_BUTTONS = 0
WPAD_CHAN_ALL = -1
WPAD_CHAN_0 = 0
WPAD_CHAN_1 = 1
WPAD_CHAN_2 = 2
WPAD_CHAN_3 = 3
WPAD_BALANCE_BOARD = 4
WPAD_MAX_WIIMOTES = 6

# interne libogc-Werte
_ERR_NONE, _ERR_NO_CONTROLLER, _ERR_NOT_READY = 0, -1, -2
_ERR_BAD_CHANNEL, _ERR_QUEUE_EMPTY, _ERR_BADVALUE = -6, -7, -8
_EXP_NONE, _EXP_NUNCHUK, _EXP_CLASSIC, _EXP_GH3 = 0, 1, 2, 3
_FMT_BTNS_ACC_IR = 2
_WPADDATA_SIZE = 340       # sizeof(WPADData) im Wii-Build
_EXPANSION_SIZE = 92       # sizeof(struct expansion_t)
_STATE_DISABLED, _STATE_ENABLED = 0, 2

# ----------------------------------------------------------------- WPADState
_STATE_FIELDS = (
    "WPAD_BUTTON_2", "WPAD_BUTTON_1", "WPAD_BUTTON_B", "WPAD_BUTTON_A",
    "WPAD_BUTTON_MINUS", "WPAD_BUTTON_HOME", "WPAD_BUTTON_LEFT", "WPAD_BUTTON_RIGHT",
    "WPAD_BUTTON_DOWN", "WPAD_BUTTON_UP", "WPAD_BUTTON_PLUS",
    "WPAD_NUNCHUK_BUTTON_Z", "WPAD_NUNCHUK_BUTTON_C",
    "WPAD_CLASSIC_BUTTON_UP", "WPAD_CLASSIC_BUTTON_LEFT", "WPAD_CLASSIC_BUTTON_ZR",
    "WPAD_CLASSIC_BUTTON_X", "WPAD_CLASSIC_BUTTON_A", "WPAD_CLASSIC_BUTTON_Y",
    "WPAD_CLASSIC_BUTTON_B", "WPAD_CLASSIC_BUTTON_ZL", "WPAD_CLASSIC_BUTTON_FULL_R",
    "WPAD_CLASSIC_BUTTON_PLUS", "WPAD_CLASSIC_BUTTON_HOME", "WPAD_CLASSIC_BUTTON_MINUS",
    "WPAD_CLASSIC_BUTTON_FULL_L", "WPAD_CLASSIC_BUTTON_DOWN", "WPAD_CLASSIC_BUTTON_RIGHT",
)


class WPADState(collections.namedtuple("WPADState", _STATE_FIELDS + ("buttons_raw",))):
    """Named-tuple snapshot of all button states. Fields are True/False."""
    __slots__ = ()


WPADState.__module__ = "wiitools"


def _state_from_bits(bits: int) -> WPADState:
    g = globals()
    return WPADState(*[(bits & g[f]) != 0 for f in _STATE_FIELDS], bits)


# ----------------------------------------------------------------- Zustand
class _Chan:
    def __init__(self) -> None:
        self.held = 0
        self.prev = 0
        self.down = 0
        self.up = 0
        self.vstate: VState | None = None
        self.disconnected = False
        self.vres = (802, 480)
        self.fmt = _FMT_BTNS_ACC_IR
        self.motion_plus = 0
        self.speaker = 0
        self.event_bufs = 0
        self.events: collections.deque = collections.deque()
        self.dropped = 0


class _W:
    inited = False
    chans = [_Chan() for _ in range(4)]
    idle_timeout = 300
    power_cb = False
    battery_cb = False
    power_event = -999
    battery_event = -999
    lock = threading.Lock()


def _expansion_type() -> int:
    return {"nunchuk": _EXP_NUNCHUK, "classic": _EXP_CLASSIC,
            "guitar": _EXP_GH3, "none": _EXP_NONE}[cfg.expansion]


def _connected(chan: int) -> bool:
    return 0 <= chan < 4 and inp.connected(chan) and not _W.chans[chan].disconnected


def _bits_from_vstate(st: VState) -> int:
    b = st.btn
    bits = 0
    core = {"two": WPAD_BUTTON_2, "one": WPAD_BUTTON_1, "b": WPAD_BUTTON_B, "a": WPAD_BUTTON_A,
            "minus": WPAD_BUTTON_MINUS, "home": WPAD_BUTTON_HOME, "left": WPAD_BUTTON_LEFT,
            "right": WPAD_BUTTON_RIGHT, "down": WPAD_BUTTON_DOWN, "up": WPAD_BUTTON_UP,
            "plus": WPAD_BUTTON_PLUS}
    for name, mask in core.items():
        if name in b:
            bits |= mask
    exp = _expansion_type()
    if exp == _EXP_NUNCHUK:
        if "z" in b:
            bits |= WPAD_NUNCHUK_BUTTON_Z
        if "c" in b:
            bits |= WPAD_NUNCHUK_BUTTON_C
    elif exp == _EXP_CLASSIC:
        cl = {"up": WPAD_CLASSIC_BUTTON_UP, "left": WPAD_CLASSIC_BUTTON_LEFT,
              "zr": WPAD_CLASSIC_BUTTON_ZR, "x": WPAD_CLASSIC_BUTTON_X, "a": WPAD_CLASSIC_BUTTON_A,
              "y": WPAD_CLASSIC_BUTTON_Y, "b": WPAD_CLASSIC_BUTTON_B, "zl": WPAD_CLASSIC_BUTTON_ZL,
              "r": WPAD_CLASSIC_BUTTON_FULL_R, "plus": WPAD_CLASSIC_BUTTON_PLUS,
              "home": WPAD_CLASSIC_BUTTON_HOME, "minus": WPAD_CLASSIC_BUTTON_MINUS,
              "l": WPAD_CLASSIC_BUTTON_FULL_L, "down": WPAD_CLASSIC_BUTTON_DOWN,
              "right": WPAD_CLASSIC_BUTTON_RIGHT}
        for name, mask in cl.items():
            if name in b:
                bits |= mask
    elif exp == _EXP_GH3:
        gh = {"up": WPAD_GUITAR_HERO_3_BUTTON_STRUM_UP, "down": WPAD_GUITAR_HERO_3_BUTTON_STRUM_DOWN,
              "a": WPAD_GUITAR_HERO_3_BUTTON_GREEN, "b": WPAD_GUITAR_HERO_3_BUTTON_RED,
              "x": WPAD_GUITAR_HERO_3_BUTTON_YELLOW, "y": WPAD_GUITAR_HERO_3_BUTTON_BLUE,
              "l": WPAD_GUITAR_HERO_3_BUTTON_ORANGE, "plus": WPAD_GUITAR_HERO_3_BUTTON_PLUS,
              "minus": WPAD_GUITAR_HERO_3_BUTTON_MINUS}
        for name, mask in gh.items():
            if name in b:
                bits |= mask
    return bits & 0xFFFFFFFF


def _norm_chan(chan: int) -> list[int]:
    if chan == WPAD_CHAN_ALL or chan == 0xFFFFFFFF:
        return [0, 1, 2, 3]
    return [chan] if 0 <= chan < 4 else []


def _on_power_key(name: str) -> None:
    if name == "power" and _W.power_cb:
        _W.power_event = 0


inp.key_handlers.append(_on_power_key)


def _quit_as_power() -> bool:
    if _W.power_cb:
        _W.power_event = 0
        return True
    return False


inp.quit_handlers.append(_quit_as_power)


# ----------------------------------------------------------------- Checks
def _require_ready(chan: int) -> None:
    """Pendant zu wt_wpad_channel_ready() aus wiitoolsmodule.c."""
    if not _W.inited:
        raise RuntimeError("WPAD is not initialized; call the matching *_Init function first")
    if chan < 0 or chan >= WPAD_MAX_WIIMOTES:
        raise ValueError("chan must be 0..3")
    pr = WPAD_Probe(chan)[0]
    if pr != _ERR_NONE:
        raise RuntimeError(f"kein Controller auf Kanal {chan} (WPAD_Probe={pr})")


# ----------------------------------------------------------------- API
def WPAD_Init() -> int:
    inp.start()
    _W.inited = True
    for c in _W.chans:
        c.disconnected = False
        c.fmt = _FMT_BTNS_ACC_IR
        c.vres = (802, 480)
    return 0


def WPAD_ScanPads() -> None:
    from ._display import display
    display.pump()
    if not _W.inited:
        return None
    for i, c in enumerate(_W.chans):
        st = inp.state(i, "wpad") if inp.connected(i) else None
        if st is not None and c.disconnected and st.btn:
            c.disconnected = False  # Knopfdruck verbindet neu (wie echte Wiimote)
        if st is None or c.disconnected:
            st = None
        c.vstate = st
        c.prev = c.held
        c.held = _bits_from_vstate(st) if st is not None else 0
        c.down = c.held & ~c.prev
        c.up = c.prev & ~c.held
        if c.event_bufs and st is not None:
            with _W.lock:
                if len(c.events) >= c.event_bufs:
                    c.events.popleft()
                    c.dropped += 1
                c.events.append(_raw_wpaddata(i))
    return None


def _query(button: int, chan: int, attr: str) -> int:
    for ch in _norm_chan(chan):
        if getattr(_W.chans[ch], attr) & (button & 0xFFFFFFFF):
            return 1
    return 0


def WPAD_ButtonsDown(button: int, chan: int) -> int:
    return _query(button, chan, "down")


def WPAD_ButtonsUp(button: int, chan: int) -> int:
    return _query(button, chan, "up")


def WPAD_ButtonsHeld(button: int, chan: int) -> int:
    return _query(button, chan, "held")


def _collect(chan: int, attr: str) -> int:
    r = 0
    for ch in _norm_chan(chan):
        r |= getattr(_W.chans[ch], attr)
    return r


def WPAD_ButtonsDown_all(chan: int) -> WPADState:
    return _state_from_bits(_collect(chan, "down"))


def WPAD_ButtonsUp_all(chan: int) -> WPADState:
    return _state_from_bits(_collect(chan, "up"))


def WPAD_ButtonsHeld_all(chan: int) -> WPADState:
    return _state_from_bits(_collect(chan, "held"))


def WPAD_Probe(chan: int) -> tuple[int, int]:
    if not _W.inited:
        return (_ERR_NOT_READY, 0)
    if chan < 0 or chan >= WPAD_MAX_WIIMOTES:
        return (_ERR_BAD_CHANNEL, 0)
    if not _connected(chan):
        return (_ERR_NO_CONTROLLER, 0)
    return (_ERR_NONE, _expansion_type())


def WPAD_GetStatus() -> int:
    return _STATE_ENABLED if _W.inited else _STATE_DISABLED


def _chan_or_all(chan: int):
    return [_W.chans[c] for c in _norm_chan(chan)]


def WPAD_SetDataFormat(chan: int, fmt: int) -> int:
    if not 0 <= fmt <= 2:
        return _ERR_BADVALUE
    for c in _chan_or_all(chan):
        c.fmt = fmt
    return _ERR_NONE


def WPAD_SetMotionPlus(chan: int, enable: int) -> int:
    for c in _chan_or_all(chan):
        c.motion_plus = 1 if enable else 0
    return _ERR_NONE


def WPAD_SetVRes(chan: int, xres: int, yres: int) -> int:
    for c in _chan_or_all(chan):
        c.vres = (int(xres), int(yres))
    return _ERR_NONE


def WPAD_ControlSpeaker(chan: int, enable: int) -> int:
    for c in _chan_or_all(chan):
        c.speaker = 1 if enable else 0
    return _ERR_NONE


def WPAD_IsSpeakerEnabled(chan: int) -> int:
    return _W.chans[chan].speaker if 0 <= chan < 4 else 0


def WPAD_SendStreamData(chan: int, data_bytes: bytes) -> int:
    bytes(data_bytes)  # Type check like y#.
    if not (0 <= chan < 4) or not _connected(chan):
        return _ERR_NO_CONTROLLER
    return _ERR_NONE  # kein Wiimote-Lautsprecher am PC


def WPAD_Disconnect(chan: int) -> int:
    if not (0 <= chan < 4):
        return _ERR_BAD_CHANNEL
    _W.chans[chan].disconnected = True
    return _ERR_NONE


def WPAD_Shutdown() -> None:
    _W.inited = False
    for c in _W.chans:
        c.held = c.prev = c.down = c.up = 0
        c.events.clear()


def WPAD_SetIdleTimeout(seconds: int) -> None:
    _W.idle_timeout = int(seconds)


def WPAD_SetPowerButtonCallback(enable: int) -> None:
    _W.power_cb = bool(enable)


def WPAD_SetBatteryDeadCallback(enable: int) -> None:
    _W.battery_cb = bool(enable)


def WPAD_GetPowerButtonEvent() -> int:
    v, _W.power_event = _W.power_event, -999
    return v


def WPAD_GetBatteryDeadEvent() -> int:
    v, _W.battery_event = _W.battery_event, -999
    return v


def WPAD_Rumble(chan: int, status: int) -> int:
    for ch in _norm_chan(chan):
        inp.rumble(ch, bool(status))
    return _ERR_NONE


def WPAD_SetIdleThresholds(chan: int, btns: int, ir: int, accel: int, js: int, wb: int, mp: int) -> int:
    return _ERR_NONE


# ---- Ereignis-API ----------------------------------------------------------
def WPAD_SetEventBufs(chan: int, cnt: int) -> int:
    _require_ready(chan)
    if not 1 <= cnt <= 8:
        raise ValueError("cnt must be 1..8")
    c = _W.chans[chan]
    with _W.lock:
        c.event_bufs = int(cnt)
        c.events = collections.deque()
    return _ERR_NONE


def WPAD_ReadEvent(chan: int) -> tuple[int, bytes]:
    _require_ready(chan)
    with _W.lock:
        q = _W.chans[chan].events
        if q:
            return (_ERR_NONE, q.popleft())
    return (_ERR_QUEUE_EMPTY, bytes(_WPADDATA_SIZE))


def WPAD_DroppedEvents(chan: int) -> int:
    if not 0 <= chan < 4:
        return _ERR_BAD_CHANNEL
    v, _W.chans[chan].dropped = _W.chans[chan].dropped, 0
    return v


def WPAD_Flush(chan: int) -> int:
    _require_ready(chan)
    with _W.lock:
        n = len(_W.chans[chan].events)
        _W.chans[chan].events.clear()
    return n


def WPAD_ReadPending(chan: int) -> int:
    return WPAD_Flush(chan)


# ---- Bewegungs-/IR-Daten ---------------------------------------------------
def _vs(chan: int) -> VState:
    return _W.chans[chan].vstate or VState()


def _orient(chan: int) -> tuple[float, float, float, float, float]:
    st = _vs(chan)
    return (float(st.roll), float(st.pitch), 0.0, float(st.roll), float(st.pitch))


def _gforce(chan: int) -> tuple[float, float, float]:
    st = _vs(chan)
    r, p = math.radians(st.roll), math.radians(st.pitch)
    return (math.sin(r) * math.cos(p), -math.sin(p), math.cos(r) * math.cos(p))


def _accel(chan: int) -> tuple[int, int, int]:
    gx, gy, gz = _gforce(chan)
    return (int(round(512 + 104 * gx)), int(round(512 + 104 * gy)), int(round(512 + 104 * gz)))


def _ir(chan: int) -> dict:
    st = _vs(chan)
    c = _W.chans[chan]
    from ._display import display
    fw, fh = display.fb_size()
    if st.pointer is None or c.fmt < _FMT_BTNS_ACC_IR:
        return {"valid": 0, "x": 0.0, "y": 0.0, "ax": 0.0, "ay": 0.0,
                "angle": 0.0, "distance": 0.0, "z": 0.0}
    x = st.pointer[0] / fw * c.vres[0]
    y = st.pointer[1] / fh * c.vres[1]
    return {"valid": 1, "x": float(x), "y": float(y), "ax": float(x), "ay": float(y),
            "angle": float(st.roll), "distance": 240.0, "z": 2.0}


def _js_raw(v: float, center: int, span: int) -> float:
    return float(int(round(center + v * span)))


def _expansion(chan: int):
    st = _vs(chan)
    exp = _expansion_type()
    bits = _W.chans[chan].held
    if exp == _EXP_NONE:
        return None
    if exp == _EXP_NUNCHUK:
        return {"type": "nunchuk", "btns": (bits >> 16) & 0xFF,
                "js_x": _js_raw(st.lx, 128, 100), "js_y": _js_raw(st.ly, 128, 100),
                "orient": (0.0, 0.0, 0.0), "gforce": (0.0, 0.0, 1.0), "accel": (512, 512, 712)}
    if exp == _EXP_CLASSIC:
        return {"type": "classic", "btns": (bits >> 16) & 0xFFFF,
                "ljs_x": _js_raw(st.lx, 32, 28), "ljs_y": _js_raw(st.ly, 32, 28),
                "rjs_x": _js_raw(st.rx, 16, 14), "rjs_y": _js_raw(st.ry, 16, 14),
                "l_shoulder": float(st.lt), "r_shoulder": float(st.rt)}
    return {"type": "guitar", "btns": (bits >> 16) & 0xFFFF, "whammy": float(st.rt),
            "js_x": _js_raw(st.lx, 32, 28), "js_y": _js_raw(st.ly, 32, 28)}


def _data_present(chan: int) -> int:
    fmt = _W.chans[chan].fmt
    p = WPAD_DATA_BUTTONS
    if fmt >= 1:
        p |= 0x02
    if fmt >= 2:
        p |= 0x08
    if _expansion_type() != _EXP_NONE:
        p |= 0x04
    return p


def _raw_wpaddata(chan: int) -> bytes:
    c = _W.chans[chan]
    head = struct.pack(">h2xIB3xIIII", 0, _data_present(chan), 0xC0, c.held, c.prev, c.down, c.up)
    return head + bytes(_WPADDATA_SIZE - len(head))


def WPAD_Data(chan: int) -> dict | None:
    _require_ready(chan)
    c = _W.chans[chan]
    return {
        "err": 0,
        "data_present": _data_present(chan),
        "battery_level": 0xC0,
        "btns_h": c.held, "btns_l": c.prev, "btns_d": c.down, "btns_u": c.up,
        "ir": _ir(chan),
        "orient": _orient(chan),
        "gforce": _gforce(chan),
        "accel": _accel(chan),
        "expansion": _expansion(chan),
    }


def WPAD_BatteryLevel(chan: int) -> int:
    return 4 if _connected(chan) and _W.inited else 0


def WPAD_IR(chan: int) -> dict:
    _require_ready(chan)
    return _ir(chan)


def WPAD_Orientation(chan: int) -> tuple[float, float, float, float, float]:
    _require_ready(chan)
    return _orient(chan)


def WPAD_GForce(chan: int) -> tuple[float, float, float]:
    _require_ready(chan)
    return _gforce(chan)


def WPAD_Accel(chan: int) -> tuple[int, int, int]:
    _require_ready(chan)
    return _accel(chan)


def WPAD_Expansion(chan: int):
    _require_ready(chan)
    return _expansion(chan)


# ---- Lautsprecher-Codec (Yamaha 4-bit ADPCM wie libogc) --------------------
_YAMAHA_INDEXSCALE = (230, 230, 230, 230, 307, 409, 512, 614,
                      230, 230, 230, 230, 307, 409, 512, 614)
_YAMAHA_DIFFLOOKUP = (1, 3, 5, 7, 9, 11, 13, 15, -1, -3, -5, -7, -9, -11, -13, -15)


def WPAD_EncodeData(flag: int, pcm_bytes: bytes, out_len: int) -> tuple[bytes, bytes]:
    pcm = bytes(pcm_bytes)
    if len(pcm) % 2:
        raise ValueError("pcm byte length must be even (s16 samples)")
    if out_len <= 0 or out_len > 8192:
        raise ValueError("out_len must be 1..8192")
    # Wii is big-endian: s16 samples are stored there in big-endian order.
    samples = list(struct.unpack(f">{len(pcm) // 2}h", pcm))
    predictor, step = 0, 0  # Reset state, as in the C wrapper.

    def enc(sample: int) -> int:
        nonlocal predictor, step
        if not step:
            predictor, step = 0, 127
        delta = sample - predictor
        nib = min(7, (abs(delta) * 4) // step) + (8 if delta < 0 else 0)
        predictor += (step * _YAMAHA_DIFFLOOKUP[nib]) // 8 if step * _YAMAHA_DIFFLOOKUP[nib] >= 0 \
            else -((-step * _YAMAHA_DIFFLOOKUP[nib]) // 8)
        predictor = max(-32768, min(32767, predictor))
        step = max(127, min(24567, (step * _YAMAHA_INDEXSCALE[nib]) >> 8))
        return nib

    out = bytearray(out_len)
    for n in range(min(out_len, (len(samples) + 1) // 2)):
        s0 = samples[2 * n]
        s1 = samples[2 * n + 1] if 2 * n + 1 < len(samples) else 0
        out[n] = ((enc(s0) << 4) | enc(s1)) & 0xFF
    status = struct.pack(">ii", predictor, step) + bytes(24)
    return (status, bytes(out))
