import asyncio
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.sandbox import network_bridge


@pytest.mark.parametrize(
    ("prctl_result", "capset_result", "raises"),
    [(0, 0, False), (-1, 0, True), (0, -1, True)],
)
def test_drop_capabilities_fails_closed_on_kernel_errors(
    monkeypatch, prctl_result, capset_result, raises
):
    libc = SimpleNamespace(
        prctl=Mock(return_value=prctl_result), capset=Mock(return_value=capset_result)
    )
    monkeypatch.setattr(network_bridge.ctypes, "CDLL", Mock(return_value=libc))

    if raises:
        with pytest.raises(OSError):
            network_bridge._drop_capabilities()
    else:
        network_bridge._drop_capabilities()

    libc.prctl.assert_called_once_with(network_bridge._PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
    if prctl_result != 0:
        libc.capset.assert_not_called()
    else:
        libc.capset.assert_called_once()


@pytest.mark.parametrize(("flags", "expected_calls"), [(1, 1), (0, 2)])
def test_loopback_setup_is_idempotent(monkeypatch, flags, expected_calls):
    request = bytearray(40)
    network_bridge.struct.pack_into("H", request, 16, flags)
    calls = []

    class ControlSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def fileno(self):
            return 7

    def ioctl(fd, operation, payload):
        calls.append((fd, operation, payload))
        return bytes(request)

    monkeypatch.setattr(network_bridge.socket, "socket", lambda *_args: ControlSocket())
    monkeypatch.setattr(network_bridge.fcntl, "ioctl", ioctl)

    network_bridge._bring_loopback_up()

    assert len(calls) == expected_calls
    assert all(fd == 7 for fd, _, _ in calls)
    if expected_calls == 2:
        assert network_bridge.struct.unpack_from("H", calls[1][2], 16)[0] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [AttributeError, OSError, RuntimeError])
async def test_pipe_forwards_bytes_and_tolerates_missing_eof_support(error_type):
    reader = SimpleNamespace(read=AsyncMock(side_effect=[b"payload", b""]))
    writer = SimpleNamespace(
        write=Mock(),
        drain=AsyncMock(),
        write_eof=Mock(side_effect=error_type("closed")),
    )

    await network_bridge._pipe(reader, writer)

    writer.write.assert_called_once_with(b"payload")
    writer.write_eof.assert_called_once_with()
    writer.drain.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_client_connection_failure_closes_local_writer(monkeypatch):
    reader = object()
    writer = SimpleNamespace(
        close=Mock(), wait_closed=AsyncMock(side_effect=OSError("already closed"))
    )
    open_connection = AsyncMock(side_effect=ConnectionRefusedError("unavailable"))
    monkeypatch.setattr(network_bridge.asyncio, "open_unix_connection", open_connection)

    await network_bridge._handle_client(reader, writer, "/tmp/proxy.sock")

    open_connection.assert_awaited_once_with("/tmp/proxy.sock")
    writer.close.assert_called_once_with()
    writer.wait_closed.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_client_connection_closes_both_streams_after_relay(monkeypatch):
    remote_reader = object()
    remote_writer = SimpleNamespace(
        close=Mock(), wait_closed=AsyncMock(side_effect=OSError("closed"))
    )
    client_writer = SimpleNamespace(
        close=Mock(), wait_closed=AsyncMock(side_effect=OSError("closed"))
    )
    monkeypatch.setattr(
        network_bridge.asyncio,
        "open_unix_connection",
        AsyncMock(return_value=(remote_reader, remote_writer)),
    )
    pipe = AsyncMock()
    monkeypatch.setattr(network_bridge, "_pipe", pipe)

    await network_bridge._handle_client(object(), client_writer, "/tmp/proxy.sock")

    assert pipe.await_count == 2
    remote_writer.close.assert_called_once_with()
    client_writer.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_run_requires_a_command_before_starting_services():
    with pytest.raises(ValueError, match="sandbox command is required"):
        await network_bridge._run("/tmp/proxy.sock", [])


@pytest.mark.asyncio
async def test_run_sets_proxy_environment_and_returns_child_exit_code(monkeypatch):
    server = SimpleNamespace(
        sockets=[SimpleNamespace(getsockname=lambda: ("127.0.0.1", 43210))],
        close=Mock(),
        wait_closed=AsyncMock(),
    )
    process = SimpleNamespace(returncode=0, wait=AsyncMock(return_value=7))
    start_server = AsyncMock(return_value=server)
    create_process = AsyncMock(return_value=process)
    monkeypatch.setattr(network_bridge, "_bring_loopback_up", Mock())
    monkeypatch.setattr(network_bridge, "_drop_capabilities", Mock())
    monkeypatch.setattr(network_bridge.asyncio, "start_server", start_server)
    monkeypatch.setattr(
        network_bridge.asyncio, "create_subprocess_exec", create_process
    )

    result = await network_bridge._run("/tmp/proxy.sock", ["installer", "install"])

    assert result == 7
    env = create_process.await_args.kwargs["env"]
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
        assert env[key] == "http://127.0.0.1:43210"
    assert env["NO_PROXY"] == env["no_proxy"] == env["npm_config_noproxy"] == ""
    server.close.assert_called_once_with()
    server.wait_closed.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_run_closes_server_when_child_creation_fails(monkeypatch):
    server = SimpleNamespace(
        sockets=[SimpleNamespace(getsockname=lambda: ("127.0.0.1", 43210))],
        close=Mock(),
        wait_closed=AsyncMock(),
    )
    monkeypatch.setattr(network_bridge, "_bring_loopback_up", Mock())
    monkeypatch.setattr(network_bridge, "_drop_capabilities", Mock())
    monkeypatch.setattr(
        network_bridge.asyncio, "start_server", AsyncMock(return_value=server)
    )
    monkeypatch.setattr(
        network_bridge.asyncio,
        "create_subprocess_exec",
        AsyncMock(side_effect=OSError("spawn failed")),
    )

    with pytest.raises(OSError, match="spawn failed"):
        await network_bridge._run("/tmp/proxy.sock", ["installer"])

    server.close.assert_called_once_with()
    server.wait_closed.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_run_kills_child_when_graceful_shutdown_times_out(monkeypatch):
    server = SimpleNamespace(
        sockets=[SimpleNamespace(getsockname=lambda: ("127.0.0.1", 43210))],
        close=Mock(),
        wait_closed=AsyncMock(),
    )
    process = SimpleNamespace(
        returncode=None,
        wait=AsyncMock(side_effect=[9, asyncio.TimeoutError(), 0]),
        send_signal=Mock(),
        kill=Mock(),
    )
    monkeypatch.setattr(network_bridge, "_bring_loopback_up", Mock())
    monkeypatch.setattr(network_bridge, "_drop_capabilities", Mock())
    monkeypatch.setattr(
        network_bridge.asyncio, "start_server", AsyncMock(return_value=server)
    )
    monkeypatch.setattr(
        network_bridge.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    )

    result = await network_bridge._run("/tmp/proxy.sock", ["installer"])

    assert result == 9
    process.send_signal.assert_called_once_with(network_bridge.signal.SIGTERM)
    process.kill.assert_called_once_with()
    assert process.wait.await_count == 3
    server.close.assert_called_once_with()


def _run_main_with_args(monkeypatch, argv):
    seen = []

    async def fake_bridge(socket_path, command):
        seen.append((socket_path, command))
        return 7

    def run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(network_bridge, "_run", fake_bridge)
    monkeypatch.setattr(network_bridge.asyncio, "run", run)
    monkeypatch.setattr(sys, "argv", ["network-bridge", *argv])

    with pytest.raises(SystemExit) as exc:
        network_bridge.main()

    return exc.value.code, seen


@pytest.mark.parametrize(
    ("argv", "expected_command"),
    [
        (["--proxy-socket", "/tmp/proxy.sock", "--", "python", "-V"], ["python", "-V"]),
        (["--proxy-socket", "/tmp/proxy.sock", "python", "-V"], ["python", "-V"]),
    ],
)
def test_main_preserves_command_arguments(monkeypatch, argv, expected_command):
    exit_code, seen = _run_main_with_args(monkeypatch, argv)

    assert exit_code == 7
    assert seen == [("/tmp/proxy.sock", expected_command)]


def test_script_entrypoint_invokes_main(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["network-bridge", "--proxy-socket", "/tmp/proxy.sock", "--", "true"],
    )

    def run(coro):
        coro.close()
        return 0

    monkeypatch.setattr(network_bridge.asyncio, "run", run)
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(network_bridge.__file__, run_name="__main__")

    assert exc.value.code == 0
