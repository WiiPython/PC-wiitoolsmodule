"""HTTP through libcurl (pycurl), using the same options as wiitoolsmodule.c."""
from __future__ import annotations

import os
from typing import Callable

from ._config import map_path

try:
    import pycurl
except Exception:  # pragma: no cover
    pycurl = None


def _require() -> None:
    if pycurl is None:
        raise RuntimeError("curl_* requires pycurl (pip install pycurl)")


def _bytes(data) -> bytes | None:
    if data is None:
        return None
    if isinstance(data, str):
        return data.encode("utf-8")
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    raise TypeError("data must be bytes, str or None")


def _headers(headers) -> list[str] | None:
    if headers is None:
        return None
    if not isinstance(headers, (list, tuple)):
        raise TypeError("headers must be a list or tuple of str")
    out = []
    for h in headers:
        if not isinstance(h, str):
            raise TypeError("headers must contain only str")
        out.append(h)
    return out


def _setup(c, method, url, data, headers, timeout_ms, verify_peer, verify_host,
           follow_redirects, user_agent, ca_file, verbose, debug_log) -> None:
    c.setopt(pycurl.URL, url)
    c.setopt(pycurl.NOSIGNAL, 1)
    c.setopt(pycurl.FOLLOWLOCATION, 1 if follow_redirects else 0)
    c.setopt(pycurl.SSL_VERIFYPEER, 1 if verify_peer else 0)
    c.setopt(pycurl.SSL_VERIFYHOST, 2 if verify_host else 0)
    if user_agent:
        c.setopt(pycurl.USERAGENT, user_agent)
    if ca_file:
        c.setopt(pycurl.CAINFO, map_path(ca_file))
    if headers:
        c.setopt(pycurl.HTTPHEADER, headers)
    if verbose:
        c.setopt(pycurl.VERBOSE, 1)
        c.setopt(pycurl.DEBUGFUNCTION, lambda _t, msg: debug_log.append(msg))
    if timeout_ms > 0:
        # As on Wii, only a connect timeout is used (seconds, rounded up).
        c.setopt(pycurl.CONNECTTIMEOUT, (timeout_ms + 999) // 1000)
    m = method or "GET"
    if m in ("HEAD", "head"):
        c.setopt(pycurl.NOBODY, 1)
    elif m in ("POST", "post"):
        c.setopt(pycurl.POST, 1)
        if data is not None:
            c.setopt(pycurl.POSTFIELDSIZE, len(data))
            c.setopt(pycurl.COPYPOSTFIELDS, data)
    elif m not in ("GET", "get"):
        c.setopt(pycurl.CUSTOMREQUEST, m)
        if data is not None:
            c.setopt(pycurl.POSTFIELDSIZE, len(data))
            c.setopt(pycurl.COPYPOSTFIELDS, data)


def _error_text(code: int, msg: str) -> str:
    if code == 0:
        return ""
    return msg or f"curl error {code}"


def _perform(method, url, data, headers, timeout_ms, verify_peer, verify_host,
             follow_redirects, user_agent, ca_file, verbose) -> dict:
    _require()
    data_b = _bytes(data)
    hdrs = _headers(headers)
    body, resp_headers, debug_log = [], [], []
    c = pycurl.Curl()
    try:
        _setup(c, method, url, data_b, hdrs, int(timeout_ms), verify_peer, verify_host,
               follow_redirects, user_agent, ca_file, verbose, debug_log)
        c.setopt(pycurl.WRITEFUNCTION, body.append)
        c.setopt(pycurl.HEADERFUNCTION, resp_headers.append)
        code, msg = 0, ""
        try:
            c.perform()
        except pycurl.error as exc:
            code, msg = exc.args[0], (exc.args[1] if len(exc.args) > 1 else "")
        res = {
            "ok": int(code == 0),
            "status": int(c.getinfo(pycurl.RESPONSE_CODE)),
            "body": b"".join(body),
            "headers": b"".join(resp_headers),
            "error": _error_text(code, msg),
            "url": c.getinfo(pycurl.EFFECTIVE_URL) or "",
            "curl_code": int(code),
        }
        if debug_log:
            res["verbose"] = b"".join(debug_log)
        return res
    finally:
        c.close()


def curl_request(method: str, url: str, data: bytes | str | None = None,
                 headers: list[str] | tuple[str, ...] | None = None,
                 timeout_ms: int = 30000, verify_peer: int = 0,
                 verify_host: int = 0, follow_redirects: int = 1,
                 user_agent: str | None = None, ca_file: str | None = None,
                 verbose: int = 0) -> dict:
    return _perform(method, url, data, headers, timeout_ms, verify_peer, verify_host,
                    follow_redirects, user_agent, ca_file, verbose)


def curl_get(url: str, headers: list[str] | tuple[str, ...] | None = None,
             timeout_ms: int = 30000, verify_peer: int = 0,
             verify_host: int = 0, follow_redirects: int = 1,
             user_agent: str | None = None, ca_file: str | None = None,
             verbose: int = 0) -> dict:
    return _perform("GET", url, None, headers, timeout_ms, verify_peer, verify_host,
                    follow_redirects, user_agent, ca_file, verbose)


def curl_post(url: str, data: bytes | str,
              headers: list[str] | tuple[str, ...] | None = None,
              timeout_ms: int = 30000, verify_peer: int = 0,
              verify_host: int = 0, follow_redirects: int = 1,
              user_agent: str | None = None, ca_file: str | None = None,
              verbose: int = 0) -> dict:
    if data is None:
        raise TypeError("curl_post() requires data")
    return _perform("POST", url, data, headers, timeout_ms, verify_peer, verify_host,
                    follow_redirects, user_agent, ca_file, verbose)


def curl_download(url: str, dest_path: str, method: str = "GET",
                  data: bytes | str | None = None,
                  headers: list[str] | tuple[str, ...] | None = None,
                  timeout_ms: int = 30000, verify_peer: int = 0,
                  verify_host: int = 0, follow_redirects: int = 1,
                  user_agent: str | None = None, ca_file: str | None = None,
                  resume: bool = False,
                  progress: Callable[[int, int], object] | None = None,
                  verbose: int = 0) -> dict:
    _require()
    if progress is not None and not callable(progress):
        raise TypeError("progress must be callable or None")
    data_b = _bytes(data)
    hdrs = _headers(headers)
    path = map_path(dest_path)
    resume_from = 0
    if resume:
        try:
            resume_from = os.path.getsize(path)
        except OSError:
            resume_from = 0
    try:
        fp = open(path, "ab" if resume else "wb")
    except OSError:
        raise OSError(f"cannot open '{dest_path}' for writing") from None

    written = 0
    aborted = False
    cb_exc: BaseException | None = None
    debug_log: list[bytes] = []

    def write_cb(chunk: bytes):
        nonlocal written
        n = fp.write(chunk)
        written += n
        return None if n == len(chunk) else 0

    def xfer_cb(dltotal, dlnow, ultotal, ulnow):
        nonlocal aborted, cb_exc
        if cb_exc is not None:
            return 1
        try:
            r = progress(int(dlnow), int(dltotal))
        except BaseException as exc:  # Re-raised after perform().
            cb_exc = exc
            return 1
        if r is False:
            aborted = True
            return 1
        return 0

    c = pycurl.Curl()
    try:
        _setup(c, method, url, data_b, hdrs, int(timeout_ms), verify_peer, verify_host,
               follow_redirects, user_agent, ca_file, verbose, debug_log)
        c.setopt(pycurl.WRITEFUNCTION, write_cb)
        if resume_from > 0:
            c.setopt(pycurl.RESUME_FROM_LARGE, resume_from)
        if progress is not None:
            c.setopt(pycurl.NOPROGRESS, 0)
            c.setopt(pycurl.XFERINFOFUNCTION, xfer_cb)
        code, msg = 0, ""
        try:
            c.perform()
        except pycurl.error as exc:
            code, msg = exc.args[0], (exc.args[1] if len(exc.args) > 1 else "")
        fp.flush()
        try:
            os.fsync(fp.fileno())
        except OSError:
            pass
        status = int(c.getinfo(pycurl.RESPONSE_CODE))
        eff = c.getinfo(pycurl.EFFECTIVE_URL) or ""
    finally:
        fp.close()
        c.close()
    if cb_exc is not None:
        raise cb_exc
    res = {
        "ok": code == 0 and not aborted,
        "status": status,
        "path": dest_path,
        "bytes_written": written,
        "resumed_from": resume_from,
        "aborted": aborted,
        "error": "download aborted by progress callback" if aborted else _error_text(code, msg),
        "url": eff,
        "curl_code": int(code),
    }
    if debug_log:
        res["verbose"] = b"".join(debug_log)
    return res
