"""Virtual controllers: keyboard/mouse (channel 0) and gamepads (channels 0..3).

Belegung Tastatur/Maus (Kanal 0)::

    Pfeiltasten           D-Pad (Wiimote, Classic, GC)
    Enter / Leertaste     A          (auch linke Maustaste)
    Backspace             B          (also right mouse button)
    1 / 2                 Wiimote 1 / 2
    + / -                 PLUS (= GC START) / MINUS
    Esc / Pos1            HOME
    C / Z                 Nunchuk C / Z (Z auch GC-Z)
    X / Y                 Classic/GC X / Y
    Q / E                 L / R (shoulder buttons, fully pressed)
    R / F                 Classic ZL / ZR
    W A S D               linker Stick (Nunchuk / Classic links / GC Hauptstick)
    I J K L               rechter Stick (Classic rechts / GC C-Stick)
    Num 4/6, Num 8/2      Wiimote neigen (Roll / Pitch), Num 5 = gerade
    Maus                  IR-Pointer
    F4                    Power-Knopf,   F5  Reset-Knopf

Gamepad (Xbox-Layout): A/B -> A/B, X -> X+1, Y -> Y+2, LB -> C+ZL, RB -> Z+ZR,
LT/RT -> L/R analog, Start -> PLUS, Back -> MINUS, Guide -> HOME, Sticks, D-Pad.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ._display import display, pygame

try:  # pragma: no cover
    from pygame._sdl2 import controller as _ctrl
except Exception:
    _ctrl = None


@dataclass
class VState:
    btn: set = field(default_factory=set)
    lx: float = 0.0
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    lt: float = 0.0
    rt: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    pointer: tuple | None = None


def _keymap() -> dict:
    if pygame is None:
        return {}
    k = pygame
    m = {
        "up": [k.K_UP], "down": [k.K_DOWN], "left": [k.K_LEFT], "right": [k.K_RIGHT],
        "a": [k.K_RETURN, k.K_KP_ENTER, k.K_SPACE],
        "b": [k.K_BACKSPACE],
        "one": [k.K_1], "two": [k.K_2],
        "plus": [k.K_PLUS, k.K_KP_PLUS, k.K_EQUALS],
        "minus": [k.K_MINUS, k.K_KP_MINUS],
        "home": [k.K_ESCAPE, k.K_HOME],
        "c": [k.K_c], "z": [k.K_z], "x": [k.K_x], "y": [k.K_y],
        "l": [k.K_q], "r": [k.K_e], "zl": [k.K_r], "zr": [k.K_f],
        "power": [k.K_F4], "reset": [k.K_F5],
    }
    return m


class _Input:
    CONSUMERS = ("wpad", "pad", "sys")

    def __init__(self) -> None:
        self.keymap = _keymap()
        self._taps = {c: set() for c in self.CONSUMERS}
        self._mouse_taps = {c: set() for c in self.CONSUMERS}
        self.pads: list = []  # (kind, obj) je Gamepad
        self.quit_handlers: list = []   # Return True = handled.
        self.key_handlers: list = []    # f(name) bei Tastendruck (Power/Reset)
        self._started = False
        display.event_handlers.append(self._on_event)

    # ----------------------------------------------------------------- setup
    def start(self) -> None:
        if self._started or not display.ensure():
            return
        self._started = True
        if _ctrl is not None:
            try:
                _ctrl.init()
            except Exception:
                pass
        self._rescan()

    def _rescan(self) -> None:
        pads = []
        if pygame is None:
            self.pads = pads
            return
        try:
            n = pygame.joystick.get_count()
        except Exception:
            n = 0
        for i in range(n):
            try:
                if _ctrl is not None and _ctrl.is_controller(i):
                    pads.append(("ctrl", _ctrl.Controller(i)))
                else:
                    js = pygame.joystick.Joystick(i)
                    js.init()
                    pads.append(("joy", js))
            except Exception:
                continue
        self.pads = pads[:4]

    def _on_event(self, ev) -> None:
        t = ev.type
        if t == pygame.QUIT:
            if not any([h() for h in list(self.quit_handlers)]):
                raise SystemExit(0)
        elif t == pygame.KEYDOWN:
            for c in self.CONSUMERS:
                self._taps[c].add(ev.key)
            for name in ("power", "reset"):
                if ev.key in self.keymap.get(name, ()):
                    for h in list(self.key_handlers):
                        h(name)
        elif t == pygame.MOUSEBUTTONDOWN:
            for c in self.CONSUMERS:
                self._mouse_taps[c].add(ev.button)
        elif t in (getattr(pygame, "JOYDEVICEADDED", -1), getattr(pygame, "JOYDEVICEREMOVED", -1),
                   getattr(pygame, "CONTROLLERDEVICEADDED", -1),
                   getattr(pygame, "CONTROLLERDEVICEREMOVED", -1)):
            self._rescan()

    # ------------------------------------------------------------------ query
    def connected(self, chan: int) -> bool:
        if chan == 0:
            return True
        return 0 <= chan < 4 and chan < len(self.pads)

    def key_held(self, name: str) -> bool:
        if display.window is None:
            return False
        pressed = pygame.key.get_pressed()
        return any(pressed[k] for k in self.keymap.get(name, ()))

    def state(self, chan: int, consumer: str) -> VState | None:
        if not self.connected(chan):
            return None
        st = VState()
        if display.window is not None:
            if chan == 0:
                self._read_keyboard(st, consumer)
            if chan < len(self.pads):
                self._read_pad(st, self.pads[chan])
        return st

    def _read_keyboard(self, st: VState, consumer: str) -> None:
        pressed = pygame.key.get_pressed()
        taps = self._taps[consumer]
        self._taps[consumer] = set()
        mtaps = self._mouse_taps[consumer]
        self._mouse_taps[consumer] = set()
        mouse = pygame.mouse.get_pressed(3)
        for name, keys in self.keymap.items():
            if name in ("power", "reset"):
                continue
            if any(pressed[k] or k in taps for k in keys):
                st.btn.add(name)
        if mouse[0] or 1 in mtaps:
            st.btn.add("a")
        if mouse[2] or 3 in mtaps:
            st.btn.add("b")
        if "l" in st.btn:
            st.lt = 1.0
        if "r" in st.btn:
            st.rt = 1.0
        k = pygame
        st.lx = float(pressed[k.K_d]) - float(pressed[k.K_a])
        st.ly = float(pressed[k.K_w]) - float(pressed[k.K_s])
        st.rx = float(pressed[k.K_l]) - float(pressed[k.K_j])
        st.ry = float(pressed[k.K_i]) - float(pressed[k.K_k])
        st.roll = 45.0 * (float(pressed[k.K_KP6]) - float(pressed[k.K_KP4]))
        st.pitch = 45.0 * (float(pressed[k.K_KP8]) - float(pressed[k.K_KP2]))
        st.pointer = display.mouse_fb()

    @staticmethod
    def _read_pad(st: VState, pad) -> None:
        kind, obj = pad
        try:
            if kind == "ctrl":
                P = pygame
                b = obj.get_button
                ax = lambda a: obj.get_axis(a) / 32767.0  # noqa: E731
                mapping = {
                    P.CONTROLLER_BUTTON_A: ("a",), P.CONTROLLER_BUTTON_B: ("b",),
                    P.CONTROLLER_BUTTON_X: ("x", "one"), P.CONTROLLER_BUTTON_Y: ("y", "two"),
                    P.CONTROLLER_BUTTON_LEFTSHOULDER: ("c", "zl"),
                    P.CONTROLLER_BUTTON_RIGHTSHOULDER: ("z", "zr"),
                    P.CONTROLLER_BUTTON_START: ("plus",), P.CONTROLLER_BUTTON_BACK: ("minus",),
                    P.CONTROLLER_BUTTON_GUIDE: ("home",),
                    P.CONTROLLER_BUTTON_DPAD_UP: ("up",), P.CONTROLLER_BUTTON_DPAD_DOWN: ("down",),
                    P.CONTROLLER_BUTTON_DPAD_LEFT: ("left",), P.CONTROLLER_BUTTON_DPAD_RIGHT: ("right",),
                }
                for bt, names in mapping.items():
                    if b(bt):
                        st.btn.update(names)
                lx, ly = ax(P.CONTROLLER_AXIS_LEFTX), -ax(P.CONTROLLER_AXIS_LEFTY)
                rx, ry = ax(P.CONTROLLER_AXIS_RIGHTX), -ax(P.CONTROLLER_AXIS_RIGHTY)
                lt, rt = ax(P.CONTROLLER_AXIS_TRIGGERLEFT), ax(P.CONTROLLER_AXIS_TRIGGERRIGHT)
            else:
                js = obj
                nb, na = js.get_numbuttons(), js.get_numaxes()
                b = lambda i: i < nb and js.get_button(i)  # noqa: E731
                a = lambda i: js.get_axis(i) if i < na else 0.0  # noqa: E731
                for i, names in enumerate((("a",), ("b",), ("x", "one"), ("y", "two"),
                                           ("c", "zl"), ("z", "zr"), ("minus",), ("plus",),
                                           ("home",))):
                    if b(i):
                        st.btn.update(names)
                if js.get_numhats() > 0:
                    hx, hy = js.get_hat(0)
                    if hx < 0: st.btn.add("left")   # noqa: E701
                    if hx > 0: st.btn.add("right")  # noqa: E701
                    if hy > 0: st.btn.add("up")     # noqa: E701
                    if hy < 0: st.btn.add("down")   # noqa: E701
                lx, ly, rx, ry = a(0), -a(1), a(3), -a(4)
                lt, rt = (a(2) + 1) / 2 if na > 2 else 0.0, (a(5) + 1) / 2 if na > 5 else 0.0
        except Exception:
            return

        def dz(v: float) -> float:
            return 0.0 if abs(v) < 0.12 else max(-1.0, min(1.0, v))

        st.lx = max(-1.0, min(1.0, st.lx + dz(lx)))
        st.ly = max(-1.0, min(1.0, st.ly + dz(ly)))
        st.rx = max(-1.0, min(1.0, st.rx + dz(rx)))
        st.ry = max(-1.0, min(1.0, st.ry + dz(ry)))
        st.lt = max(st.lt, max(0.0, min(1.0, lt)))
        st.rt = max(st.rt, max(0.0, min(1.0, rt)))
        if st.lt > 0.9:
            st.btn.add("l")
        if st.rt > 0.9:
            st.btn.add("r")

    def rumble(self, chan: int, on: bool) -> None:
        if not (0 <= chan < len(self.pads)):
            return
        kind, obj = self.pads[chan]
        try:
            if on:
                obj.rumble(0.6, 0.6, 0)
            else:
                obj.stop_rumble()
        except Exception:
            pass


inp = _Input()
