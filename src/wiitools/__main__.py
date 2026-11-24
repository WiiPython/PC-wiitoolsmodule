"""Run a Wii Python program on a PC.

    python -m wiitools spiel.py [Argumente ...]
    python -m wiitools --sd ./meine_sd --scale 2 --expansion classic spiel.py

Options set the corresponding WIITOOLS_* environment variables.
"""
from __future__ import annotations

import argparse
import os
import runpy
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m wiitools",
                                 description="Run a wiitools program on a PC.")
    ap.add_argument("--sd", help="Folder for sd:/ (default: ./sd)")
    ap.add_argument("--usb", help="Folder for usb:/ (default: ./usb)")
    ap.add_argument("--scale", type=float, help="Window scale")
    ap.add_argument("--aspect", choices=("4:3", "16:9"), help="Display aspect ratio")
    ap.add_argument("--expansion", choices=("nunchuk", "classic", "guitar", "none"),
                    help="emulierte Wiimote-Erweiterung")
    ap.add_argument("--headless", action="store_true", help="Run without a window or input")
    ap.add_argument("--no-map-absolute", action="store_true",
                    help="Do not map absolute paths to the SD card")
    ap.add_argument("script", help="Python script to run")
    ap.add_argument("args", nargs=argparse.REMAINDER)
    ns = ap.parse_args(argv)

    env = {"WIITOOLS_SD": ns.sd, "WIITOOLS_USB": ns.usb,
           "WIITOOLS_SCALE": None if ns.scale is None else str(ns.scale),
           "WIITOOLS_ASPECT": ns.aspect, "WIITOOLS_EXPANSION": ns.expansion,
           "WIITOOLS_HEADLESS": "1" if ns.headless else None,
           "WIITOOLS_MAP_ABSOLUTE": "0" if ns.no_map_absolute else None}
    for k, v in env.items():
        if v is not None:
            os.environ[k] = v

    from ._config import cfg
    cfg.reload()

    script = os.path.abspath(ns.script)
    sys.argv = [script] + ns.args
    sys.path.insert(0, os.path.dirname(script))
    runpy.run_path(script, run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
