"""TypedDicts from wiitools.pyi (return formats of WPAD_Data, PAD_Read, etc.)."""
from __future__ import annotations

from typing import TypedDict


class WPADNunchukDict(TypedDict):
    """Dict returned by WPAD_Expansion() for a Nunchuk."""
    type:   str                       # "nunchuk"
    btns:   int                       # button bitmask (WPAD_NUNCHUK_BUTTON_*)
    js_x:   float                     # raw joystick X position
    js_y:   float                     # raw joystick Y position
    orient: tuple[float, float, float]  # roll, pitch, yaw in degrees
    gforce: tuple[float, float, float]  # x, y, z g-forces
    accel:  tuple[int, int, int]


class WPADClassicDict(TypedDict):
    """Dict returned by WPAD_Expansion() for a Classic Controller."""
    type:       str    # "classic"
    btns:       int    # button bitmask (WPAD_CLASSIC_BUTTON_*)
    ljs_x:      float  # left joystick X
    ljs_y:      float  # left joystick Y
    rjs_x:      float  # right joystick X
    rjs_y:      float  # right joystick Y
    l_shoulder: float  # left shoulder (0.0–1.0)
    r_shoulder: float


class WPADGuitarDict(TypedDict):
    """Dict returned by WPAD_Expansion() for a Guitar Hero 3 controller."""
    type:   str    # "guitar"
    btns:   int    # button bitmask (WPAD_GUITAR_HERO_3_BUTTON_*)
    whammy: float  # whammy bar (0.0–1.0)
    js_x:   float  # joystick X
    js_y:   float


class WPADUnknownDict(TypedDict):
    """Dict returned by WPAD_Expansion() for an unrecognised expansion."""
    type: str    # "unknown"
    raw:  bytes


class WPADIRDict(TypedDict):
    """IR pointer position dict returned inside WPADDataDict and by WPAD_IR()."""
    valid:    int    # 1 if the bounded position is valid
    x:        float  # bounded X coordinate (0..screen width)
    y:        float  # bounded Y coordinate (0..screen height)
    ax:       float  # raw X coordinate
    ay:       float  # raw Y coordinate
    angle:    float  # angle of the Wiimote to the sensor bar (degrees)
    distance: float  # pixel width of the sensor bar
    z:        float


class WPADDataDict(TypedDict):
    """Dict returned by WPAD_Data()."""
    err:          int
    data_present: int
    battery_level: int
    btns_h:       int   # buttons held
    btns_l:       int   # buttons released this frame
    btns_d:       int   # buttons pressed this frame
    btns_u:       int   # buttons up this frame
    ir:           WPADIRDict
    orient:       tuple[float, float, float, float, float]  # roll, pitch, yaw, a_roll, a_pitch
    gforce:       tuple[float, float, float]                # x, y, z g-forces
    accel:        tuple[int, int, int]                      # raw accelerometer x, y, z
    expansion:    WPADNunchukDict | WPADClassicDict | WPADGuitarDict | WPADUnknownDict | None


class PADStatusDict(TypedDict):
    """Dict returned per channel by PAD_Read() and PAD_Clamp(). All fields are ints."""
    button:    int
    stickX:    int
    stickY:    int
    substickX: int
    substickY: int
    triggerL:  int
    triggerR:  int
    analogA:   int
    analogB:   int
    err:       int


