"""Networking (libogc net_*), using real host sockets.

Constants use the values from the Wii build (e.g. SOL_SOCKET = 0xffff,
POLLIN = 3) are translated internally to host values. Errors are returned as
negative errno values, as in libogc.
"""
from __future__ import annotations

import errno
import os
import select
import socket
import struct
import threading
import uuid

# Wii-Werte (aus libogc / newlib des devkitPPC)
AF_INET = 2
PF_INET = 2
SOCK_STREAM = 1
SOCK_DGRAM = 2
IPPROTO_IP = 0
IPPROTO_TCP = 6
IPPROTO_UDP = 17
SOL_SOCKET = 0xFFFF
SO_REUSEADDR = 0x0004
TCP_NODELAY = 0x01
POLLIN = 0x0003
POLLOUT = 0x0008
FIONBIO = 0x8004667E
O_NONBLOCK = 0o4000

_F_GETFL, _F_SETFL = 3, 4
_POLLPRI, _POLLERR, _POLLHUP, _POLLNVAL = 0x0004, 0x0020, 0x0040, 0x0080

_SOL_MAP = {  # Wii SO_* -> Host
    0x0004: socket.SO_REUSEADDR, 0x0008: socket.SO_KEEPALIVE, 0x0020: socket.SO_BROADCAST,
    0x1001: socket.SO_SNDBUF, 0x1002: socket.SO_RCVBUF,
}


class _N:
    ready = 0
    socks: dict[int, socket.socket] = {}
    lock = threading.Lock()


def _err(exc: OSError) -> int:
    return -(exc.errno or errno.EIO)


def _sock(fd: int) -> socket.socket | None:
    return _N.socks.get(int(fd))


def _start_net_thread() -> None:
    def worker() -> None:
        _N.ready = 1  # The host network is immediately available.
    threading.Thread(target=worker, name="wiitools-net", daemon=True).start()


def net_init() -> None:
    _start_net_thread()
    return None


def IsNetReady() -> int:
    return _N.ready


def net_get_status() -> int:
    return 0 if _N.ready else -errno.EBUSY


def net_deinit() -> None:
    _N.ready = 0
    with _N.lock:
        for s in _N.socks.values():
            try:
                s.close()
            except OSError:
                pass
        _N.socks.clear()
    return None


def net_wc24cleanup() -> None:
    return None


def _local_ip() -> str:
    """Primary IPv4 address via UDP 'connect' (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return ""
    finally:
        s.close()


def get_local_ip() -> str:
    return _local_ip() if _N.ready else ""


def net_gethostip() -> str:
    return _local_ip() if _N.ready else "0.0.0.0"


def net_get_mac_address() -> str:
    node = uuid.getnode()
    return ":".join(f"{(node >> s) & 0xFF:02x}" for s in range(40, -1, -8))


def net_gethostbyname(name: str) -> str | None:
    try:
        return socket.gethostbyname(name)
    except OSError:
        return None


# Wii is big-endian: s_addr (network byte order) as u32 = 0xAABBCCDD
def inet_addr(ip: str) -> int:
    v = inet_aton(ip)
    return 0xFFFFFFFF if v is None else v


def inet_aton(ip: str) -> int | None:
    try:
        return struct.unpack(">I", socket.inet_aton(ip))[0]
    except OSError:
        return None


def inet_ntoa(addr: int) -> str:
    return socket.inet_ntoa(struct.pack(">I", int(addr) & 0xFFFFFFFF))


def _netmask_gateway(ip: str) -> tuple[str, str]:
    netmask = gateway = ""
    try:  # Linux: Standard-Gateway aus /proc/net/route
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) > 2 and parts[1] == "00000000":
                    gateway = socket.inet_ntoa(struct.pack("<I", int(parts[2], 16)))
                    break
    except OSError:
        pass
    try:
        import fcntl  # Linux: SIOCGIFNETMASK for the interface with this IP.
        for _idx, ifname in socket.if_nameindex():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                req = struct.pack("256s", ifname.encode()[:15])
                addr = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, req)[20:24])
                if addr == ip:
                    netmask = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x891B, req)[20:24])
                    break
            except OSError:
                continue
            finally:
                s.close()
    except Exception:
        pass
    return netmask or "255.255.255.0", gateway


def if_config(use_dhcp: bool = True, retries: int = 20) -> dict | int:
    ip = _local_ip()
    if not ip:
        return -errno.ENETUNREACH
    _N.ready = 1
    nm, gw = _netmask_gateway(ip)
    return {"ip": ip, "netmask": nm, "gateway": gw}


# ----------------------------------------------------------------- Sockets
def net_socket(domain: int = AF_INET, type: int = SOCK_STREAM, proto: int = 0) -> int:  # noqa: A002
    if domain not in (AF_INET, PF_INET):
        return -errno.EAFNOSUPPORT
    kind = {SOCK_STREAM: socket.SOCK_STREAM, SOCK_DGRAM: socket.SOCK_DGRAM}.get(type)
    if kind is None:
        return -errno.EPROTONOSUPPORT
    try:
        s = socket.socket(socket.AF_INET, kind, proto)
    except OSError as exc:
        return _err(exc)
    fd = s.fileno()
    with _N.lock:
        _N.socks[fd] = s
    return fd


def _addr(ip: str, port: int) -> tuple[str, int]:
    if ip:
        if inet_aton(ip) is None:
            raise ValueError("invalid IP")
        return (ip, int(port))
    return ("0.0.0.0", int(port))


def _call(fd: int, fn) -> int:
    s = _sock(fd)
    if s is None:
        return -errno.EBADF
    try:
        r = fn(s)
        return 0 if r is None else r
    except BlockingIOError:
        return -errno.EAGAIN
    except socket.timeout:
        return -errno.ETIMEDOUT
    except OSError as exc:
        return _err(exc)


def net_bind(fd: int, ip: str, port: int) -> int:
    addr = _addr(ip, port)
    return _call(fd, lambda s: s.bind(addr))


def net_connect(fd: int, ip: str, port: int) -> int:
    addr = _addr(ip, port)
    return _call(fd, lambda s: s.connect(addr))


def net_listen(fd: int, backlog: int = 5) -> int:
    return _call(fd, lambda s: s.listen(int(backlog)))


def net_accept(fd: int) -> tuple[int, str | None, int]:
    s = _sock(fd)
    if s is None:
        return (-errno.EBADF, None, 0)
    try:
        c, peer = s.accept()
    except BlockingIOError:
        return (-errno.EAGAIN, None, 0)
    except OSError as exc:
        return (_err(exc), None, 0)
    nfd = c.fileno()
    with _N.lock:
        _N.socks[nfd] = c
    return (nfd, peer[0], peer[1])


def net_close(fd: int) -> int:
    with _N.lock:
        s = _N.socks.pop(int(fd), None)
    if s is None:
        return -errno.EBADF
    try:
        s.close()
        return 0
    except OSError as exc:
        return _err(exc)


def net_shutdown(fd: int, how: int) -> int:
    return _call(fd, lambda s: s.shutdown(int(how)))


def net_send(fd: int, data: bytes, flags: int = 0) -> int:
    buf = memoryview(data)
    return _call(fd, lambda s: s.send(buf, int(flags)))


def net_write(fd: int, data: bytes) -> int:
    return net_send(fd, data, 0)


def net_sendto(fd: int, data: bytes, ip: str, port: int, flags: int = 0) -> int:
    buf = memoryview(data)
    addr = _addr(ip, port)
    return _call(fd, lambda s: s.sendto(buf, int(flags), addr))


def net_recv(fd: int, maxlen: int, flags: int = 0) -> bytes | int:
    s = _sock(fd)
    if s is None:
        return -errno.EBADF
    try:
        return s.recv(max(0, int(maxlen)), int(flags))
    except BlockingIOError:
        return -errno.EAGAIN
    except socket.timeout:
        return -errno.ETIMEDOUT
    except OSError as exc:
        return _err(exc)


def net_read(fd: int, maxlen: int) -> bytes | int:
    return net_recv(fd, maxlen, 0)


def net_recvfrom(fd: int, maxlen: int, flags: int = 0) -> tuple[bytes | None, str | None, int]:
    s = _sock(fd)
    if s is None:
        return (None, None, -errno.EBADF)
    try:
        data, peer = s.recvfrom(max(0, int(maxlen)), int(flags))
    except BlockingIOError:
        return (None, None, -errno.EAGAIN)
    except OSError as exc:
        return (None, None, _err(exc))
    if not peer:
        return (data, "0.0.0.0", 0)
    return (data, peer[0], peer[1])


def net_getsockname(fd: int) -> tuple[str, int] | None:
    s = _sock(fd)
    if s is None:
        return None
    try:
        ip, port = s.getsockname()[:2]
        return (ip, port)
    except OSError:
        return None


def net_setsockopt(fd: int, level: int, optname: int, value: int) -> int:
    if level == SOL_SOCKET:
        hl, ho = socket.SOL_SOCKET, _SOL_MAP.get(optname)
    elif level == IPPROTO_TCP and optname == TCP_NODELAY:
        hl, ho = socket.IPPROTO_TCP, socket.TCP_NODELAY
    else:
        hl, ho = level, optname
    if ho is None:
        return -errno.ENOPROTOOPT
    return _call(fd, lambda s: s.setsockopt(hl, ho, int(value)))


def net_fcntl(fd: int, cmd: int, flags: int) -> int:
    s = _sock(fd)
    if s is None:
        return -errno.EBADF
    if cmd == _F_GETFL:
        return O_NONBLOCK if s.getblocking() is False else 0
    if cmd == _F_SETFL:
        s.setblocking(not (int(flags) & O_NONBLOCK))
        return 0
    return -errno.EINVAL


def net_ioctl(fd: int, cmd: int, arg: int = 0) -> int:
    s = _sock(fd)
    if s is None:
        return -errno.EBADF
    if (int(cmd) & 0xFFFFFFFF) == FIONBIO:
        s.setblocking(not int(arg))
        return 0
    return -errno.EINVAL


def net_poll(fds: list[tuple[int, int]], timeout_ms: int) -> list[tuple[int, int]]:
    entries = [(int(fd), int(ev)) for fd, ev in list(fds)]
    p = select.poll()
    for fd, ev in entries:
        hev = 0
        if ev & POLLIN:
            hev |= select.POLLIN
        if ev & _POLLPRI:
            hev |= select.POLLPRI
        if ev & POLLOUT:
            hev |= select.POLLOUT
        if _sock(fd) is not None:
            p.register(fd, hev)
    res = dict(p.poll(int(timeout_ms)))
    out = []
    for fd, ev in entries:
        if _sock(fd) is None:
            out.append((fd, _POLLNVAL))
            continue
        h = res.get(fd, 0)
        r = 0
        if h & select.POLLIN:
            r |= ev & POLLIN or POLLIN
        if h & select.POLLPRI:
            r |= _POLLPRI
        if h & select.POLLOUT:
            r |= POLLOUT
        if h & select.POLLERR:
            r |= _POLLERR
        if h & select.POLLHUP:
            r |= _POLLHUP
        if h & select.POLLNVAL:
            r |= _POLLNVAL
        out.append((fd, r))
    return out



if os.name != "posix":  # pragma: no cover
    def net_poll(fds, timeout_ms):  # type: ignore[no-redef]
        """Fallback ohne select.poll (Windows)."""
        entries = [(int(fd), int(ev)) for fd, ev in list(fds)]
        rl = [_sock(fd) for fd, ev in entries if ev & POLLIN and _sock(fd)]
        wl = [_sock(fd) for fd, ev in entries if ev & POLLOUT and _sock(fd)]
        r, w, _ = select.select(rl, wl, [], max(0, timeout_ms) / 1000 if timeout_ms >= 0 else None)
        out = []
        for fd, ev in entries:
            s = _sock(fd)
            rev = (POLLIN if s in r else 0) | (POLLOUT if s in w else 0)
            out.append((fd, rev if s else _POLLNVAL))
        return out
