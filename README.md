# wiitools for PC

Runs Python programs written for the `wiitools` module in the Wii CPython build
unchanged on a PC. The API matches `wiitools.pyi` (same constants, return
formats, error messages, and precondition checks).

| API                         | PC implementation                                  |
|-----------------------------|----------------------------------------------------|
| `WPAD_*` / `PAD_*`          | Keyboard, mouse, and gamepads                      |
| `VIDEO_*` / `GX_*`          | NumPy software renderer; pygame window             |
| `AUDIO_*`                   | pygame.mixer                                       |
| `fat*` / `read_file`        | Local folders `sd/` and `usb/`                     |
| `net_*` sockets             | Host sockets (Wii constants are translated)        |
| `curl_*` (libcurl)          | libcurl through pycurl                             |

## Installation

```sh
pip install -e .          # installs numpy, pygame, Pillow, pycurl
```

## Usage

```sh
python -m wiitools game.py              # or: wiitools-run game.py
```

## Controls (channel 0)

| Keyboard / mouse                  | Wii button                         |
|-----------------------------------|------------------------------------|
| Arrow keys                        | D-Pad                              |
| Z                                 | A                                  |
| X                                 | B                                  |
| Enter                             | HOME                               |
| Backspace, right mouse button     | B                                  |
| Left mouse button                 | A                                  |
| Mouse movement                    | IR pointer                         |
| Q / E                             | L / R (shoulder buttons, fully pressed) |

Gamepads are detected as channels 0–3 (Xbox layout; X = X+1, Y = Y+2,
LB = C+ZL, RB = Z+ZR, LT/RT = analog L/R). Closing the window exits the
program, unless a power callback is active; in that case it counts as a
POWER event.

## Configuration (environment variables)

| Variable                | Meaning                                              |
|-------------------------|------------------------------------------------------|
| `WIITOOLS_SD` / `_USB`  | Folders for `sd:/` and `usb:/`                      |
| `WIITOOLS_MAP_ABSOLUTE` | `1` (default): `/apps/x` → `sd:/apps/x`, as on Wii  |
| `WIITOOLS_ASPECT`       | `4:3` or `16:9`                                     |
| `WIITOOLS_LANGUAGE`     | CONF language 0–9 (default 2 = German)               |
| `WIITOOLS_NICKNAME`     | Console name for `CONF_GetNickName`                 |
| `WIITOOLS_EMBEDDED_PNG` | Image loaded by `png_load_embedded()`                |

## Differences from Wii

* As in the original, `sd:/` paths apply only to `wiitools` functions, not to
  Python's `open()` or `os` functions.
* `print()` and `terminal_print()` write to the PC terminal, not the window.
* The Wiimote speaker is not emulated (`WPAD_SendStreamData` succeeds but
  produces no sound).
* Host memory is limited to Wii-sized regions (MEM1 24 MB, MEM2 64 MB).
* `c_run` and `AUDIO_InitDMA` check addresses against `/proc/self/maps` (Linux).

## Tests

```sh
python -m pytest
```
