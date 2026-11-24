import os
import sys

os.environ["WIITOOLS_HEADLESS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402


@pytest.fixture
def sd(tmp_path, monkeypatch):
    from wiitools._config import cfg
    monkeypatch.setenv("WIITOOLS_SD", str(tmp_path / "sd"))
    monkeypatch.setenv("WIITOOLS_USB", str(tmp_path / "usb"))
    cfg.reload()
    import wiitools
    wiitools.fatInitDefault()
    yield tmp_path / "sd"
    monkeypatch.delenv("WIITOOLS_SD")
    monkeypatch.delenv("WIITOOLS_USB")
    cfg.reload()
