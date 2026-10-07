"""Bridge sandbox-local HTTP proxy traffic to the worker's Unix socket."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import fcntl
import os
import signal
import socket
import struct
import sys

_PR_SET_NO_NEW_PRIVS = 38
_LINUX_CAPABILITY_VERSION_3 = 0x20080522


class _CapabilityHeader(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]


class _CapabilityData(ctypes.Structure):
    _fields_ = [
        ("effective", ctypes.c_uint32),
        ("permitted", ctypes.c_uint32),
        ("inheritable", ctypes.c_uint32),
    ]


def _drop_capabilities() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    libc.prctl.restype = ctypes.c_int
    if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))

    libc.capset.argtypes = [
        ctypes.POINTER(_CapabilityHeader),
        ctypes.POINTER(_CapabilityData),
    ]
    libc.capset.restype = ctypes.c_int
    header = _CapabilityHeader(_LINUX_CAPABILITY_VERSION_3, 0)
    data = (_CapabilityData * 2)()
    if libc.capset(ctypes.byref(header), data) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _bring_loopback_up() -> None:
    request = bytearray(40)
    request[:16] = b"lo"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        current = fcntl.ioctl(control.fileno(), 0x8913, bytes(request))
        flags = struct.unpack_from("H", current, 16)[0]
        if flags & 0x1:
            return
        struct.pack_into("H", request, 16, flags | 0x1)
        fcntl.ioctl(control.fileno(), 0x8914, bytes(request))


async def _pipe(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    while chunk := await reader.read(64 * 1024):
        writer.write(chunk)
        await writer.drain()
    try:
        writer.write_eof()
        await writer.drain()
    except (AttributeError, OSError, RuntimeError):
        pass


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    socket_path: str,
) -> None:
    remote_writer: asyncio.StreamWriter | None = None
    try:
        remote_reader, remote_writer = await asyncio.open_unix_connection(socket_path)
        await asyncio.gather(
            _pipe(reader, remote_writer),
            _pipe(remote_reader, writer),
        )
    except (ConnectionError, OSError):
        pass
    finally:
        if remote_writer is not None:
            remote_writer.close()
            try:
                await remote_writer.wait_closed()
            except OSError:
                pass
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


async def _run(socket_path: str, command: list[str]) -> int:
    if not command:
        raise ValueError("A sandbox command is required")
    _bring_loopback_up()
    _drop_capabilities()
    server = await asyncio.start_server(
        lambda reader, writer: _handle_client(reader, writer, socket_path),
        host="127.0.0.1",
        port=0,
    )
    address = server.sockets[0].getsockname()
    proxy_url = f"http://127.0.0.1:{address[1]}"
    env = dict(os.environ)
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "npm_config_proxy",
        "npm_config_https_proxy",
    ):
        env[key] = proxy_url
    for key in ("NO_PROXY", "no_proxy", "npm_config_noproxy"):
        env[key] = ""

    process = None
    try:
        process = await asyncio.create_subprocess_exec(*command, env=env)
        return await process.wait()
    finally:
        if process is not None and process.returncode is None:
            try:
                process.send_signal(signal.SIGTERM)
                await asyncio.wait_for(process.wait(), timeout=2)
            except (ProcessLookupError, asyncio.TimeoutError):
                process.kill()
                await process.wait()
        server.close()
        await server.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy-socket", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    try:
        exit_code = asyncio.run(_run(args.proxy_socket, command))
    except Exception as exc:
        print(
            f"Sandbox network bridge failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
