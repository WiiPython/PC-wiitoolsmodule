import ast
import ctypes
import http.server
import inspect
import os
import threading
import time

import numpy as np
import pytest

import wiitools as w
from wiitools._display import display

PYI = os.path.join(os.path.dirname(__file__), "..", "wiitools.pyi")


@pytest.mark.skipif(not os.path.exists(PYI), reason="wiitools.pyi not found")
def test_api_matches_pyi():
    src = open(PYI, encoding="utf-8").read()
    missing, sigdiff = [], []
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.AnnAssign):
            names = [node.target.id]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets]
        else:
            continue
        for n in names:
            if not hasattr(w, n):
                missing.append(n)
            elif isinstance(node, ast.FunctionDef):
                want = [a.arg for a in node.args.args]
                have = [p for p, v in inspect.signature(getattr(w, n)).parameters.items()
                        if v.kind == v.POSITIONAL_OR_KEYWORD]
                if have[:len(want)] != want:
                    sigdiff.append(n)
    assert missing == [] and sigdiff == []


def test_constants_match_libogc():
    assert w.WPAD_BUTTON_A == 0x0008 and w.WPAD_CLASSIC_BUTTON_RIGHT == 0x80000000
    assert w.PAD_BUTTON_START == 0x1000 and w.WPAD_MAX_WIIMOTES == 6
    assert (w.POLLIN, w.POLLOUT, w.SOL_SOCKET, w.FIONBIO) == (3, 8, 0xFFFF, 0x8004667E)
    assert (w.width, w.height) == (802, 480)


def test_precondition_errors():
    w.WPAD_Shutdown()
    with pytest.raises(RuntimeError):
        w.WPAD_IR(0)
    w.WPAD_Init()
    with pytest.raises(ValueError):
        w.WPAD_Data(7)
    with pytest.raises(RuntimeError):
        w.WPAD_Data(2)  # kein Controller auf Kanal 2
    assert w.WPAD_Probe(0) == (0, 1)


def test_paths_and_files(sd):
    assert w.write_file("sd:/a.txt", "hi") == 2
    assert (sd / "a.txt").read_bytes() == b"hi"
    assert w.read_file("/a.txt") == b"hi"
    assert w.remove("sd:/a.txt") == 0 and w.remove("sd:/a.txt") == -1
    with pytest.raises(OSError):
        w.read_file("sd:/fehlt")


def test_rendering_letterbox_and_shapes():
    w.rendering_init()
    w.set_screen_size(480, 480)
    w.draw_rect(0, 0, 480, 480, (255, 0, 0, 255), 0.0)
    w.draw_rect(0, 0, 10, 10, (0, 0, 255, 10), 0.0)  # Alpha < 16 -> verworfen
    w.render_update()
    f = display.last_frame
    assert tuple(f[240, 100]) == (255, 0, 0)
    assert tuple(f[240, 0]) == (255, 255, 255)   # Outside scissor: clear color.
    assert tuple(f[2, 82]) == (255, 0, 0)
    w.set_screen_size(0, 0)


def test_text_like_c():
    assert w.text_length("ab\nä", 2) == 32  # 'ä' = 2 UTF-8-Bytes -> '??'
    assert w.text_length("", 1) == 0


def test_surfaces_and_png(sd):
    w.surface_new("s", 4, 2)
    w.surface_fill("s", (1, 2, 3, 255))
    w.surface_set_target("s")
    w.draw_rect(0, 0, 1, 1, (255, 255, 255, 255), 0.0)
    w.surface_clear_target()
    px = np.frombuffer(w.surface_get_pixels("s"), np.uint8).reshape(2, 4, 4)
    assert tuple(px[0, 0]) == (255, 255, 255, 255) and tuple(px[1, 3]) == (1, 2, 3, 255)
    assert w.surface_rotate_90("s", "r", 1) == (2, 4)
    w.png_use("s")
    assert w.png_save("sd:/s.png") == 0
    assert w.png_load_named("sd:/s.png", "t") == (4, 2)
    assert w.surface_get_pixels("t") == w.surface_get_pixels("s")
    with pytest.raises(KeyError):
        w.png_use("gibtsnicht")
    with pytest.raises(ValueError):
        w.surface_set_pixels("s", b"123")


def test_surface_blend_formula():
    w.surface_new("b", 1, 1)
    w.surface_fill("b", (0, 0, 255, 128))
    w.surface_set_target("b")
    w.draw_rect(0, 0, 1, 1, (255, 0, 0, 128), 0.0)
    w.surface_clear_target()
    # surface_blend_pixel: oa = 128 + 128*127/255 = 191
    assert tuple(w.surface_get_pixels("b")) == (170, 0, 85, 191)


def test_input_tap_registers_once():
    w.WPAD_Init()
    w.WPAD_ScanPads()
    assert w.WPAD_ButtonsDown(w.WPAD_BUTTON_A, w.WPAD_CHAN_ALL) == 0
    assert w.WPAD_ButtonsDown_all(0).buttons_raw == 0


def test_sockets_loopback():
    srv = w.net_socket()
    assert w.net_bind(srv, "127.0.0.1", 0) == 0 and w.net_listen(srv) == 0
    port = w.net_getsockname(srv)[1]
    cl = w.net_socket()
    assert w.net_connect(cl, "127.0.0.1", port) == 0
    fd, ip, _ = w.net_accept(srv)
    assert ip == "127.0.0.1"
    assert w.net_send(cl, b"ping") == 4
    assert w.net_poll([(fd, w.POLLIN)], 500) == [(fd, w.POLLIN)]
    assert w.net_recv(fd, 16) == b"ping"
    assert w.net_ioctl(fd, w.FIONBIO, 1) == 0
    assert w.net_recv(fd, 16) < 0
    for s in (cl, fd, srv):
        assert w.net_close(s) == 0
    assert w.inet_addr("1.2.3.4") == 0x01020304 and w.inet_ntoa(0x01020304) == "1.2.3.4"


@pytest.fixture
def http_url():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x" * 5000)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/"
    srv.shutdown()


def test_curl(sd, http_url):
    pytest.importorskip("pycurl")
    r = w.curl_get(http_url)
    assert r["ok"] == 1 and r["status"] == 200 and len(r["body"]) == 5000
    r = w.curl_download(http_url, "sd:/f.bin")
    assert r["ok"] is True and (sd / "f.bin").stat().st_size == 5000
    r = w.curl_download(http_url, "sd:/g.bin", progress=lambda d, t: False)
    assert r["aborted"] and not r["ok"]


def test_sys_alarm_and_c_run():
    h = w.SYS_CreateAlarm()
    w.SYS_SetAlarm(h, 0.01)
    time.sleep(0.1)
    assert w.SYS_GetAlarmEvent() == 1
    assert w.SYS_RemoveAlarm(h) == 0
    libc = ctypes.CDLL(None)
    assert w.c_run(ctypes.cast(libc.strlen, ctypes.c_void_p).value, b"abc") == 3
    with pytest.raises(ValueError):
        w.c_run(0)
