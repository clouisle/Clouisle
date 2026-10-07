"""Unix-socket egress proxy enforcing the sandbox DNS allowlist."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import shutil
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from app.core.sandbox_network_policy import (
    SandboxNetworkPolicyError,
    normalize_sandbox_network_allowlist,
    normalize_sandbox_network_host,
)

logger = logging.getLogger(__name__)
_MAX_PROXY_HEADER_BYTES = 16 * 1024


class SandboxEgressProxy:
    """A per-job HTTPS CONNECT proxy reachable only through a Unix socket."""

    def __init__(self, *, job_id: str, allowed_hosts: list[str]) -> None:
        self.job_id = job_id
        self.allowed_hosts = frozenset(
            normalize_sandbox_network_allowlist(allowed_hosts)
        )
        self._directory: str | None = None
        self._socket_path: Path | None = None
        self._server: asyncio.AbstractServer | None = None
        self._blocked: dict[tuple[str, int, str], None] = {}

    @property
    def socket_path(self) -> Path:
        if self._socket_path is None:
            raise RuntimeError("Sandbox egress proxy has not started")
        return self._socket_path

    @property
    def blocked_diagnostics(self) -> list[str]:
        return [
            f"[sandbox-network] blocked host={host} port={port} reason={reason}"
            for host, port, reason in self._blocked
        ]

    async def start(self) -> None:
        if self._server is not None:
            return
        self._directory = tempfile.mkdtemp(prefix="sbx-egress-")
        os.chmod(self._directory, 0o700)
        self._socket_path = Path(self._directory) / "proxy.sock"
        self._server = await asyncio.start_unix_server(
            self._handle_connection,
            path=str(self._socket_path),
            limit=_MAX_PROXY_HEADER_BYTES,
        )
        os.chmod(self._socket_path, 0o600)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._directory is not None:
            shutil.rmtree(self._directory, ignore_errors=True)
            self._directory = None
            self._socket_path = None

    async def __aenter__(self) -> "SandboxEgressProxy":
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def _handle_connection(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            header = await asyncio.wait_for(
                client_reader.readuntil(b"\r\n\r\n"), timeout=10
            )
            if len(header) > _MAX_PROXY_HEADER_BYTES:
                await self._deny(client_writer, "unknown", 0, "header_too_large")
                return
            first_line = header.split(b"\r\n", 1)[0].decode("ascii", "replace")
            parts = first_line.split()
            if len(parts) != 3:
                await self._deny(client_writer, "unknown", 0, "invalid_request")
                return

            method, target, _version = parts
            if method.upper() != "CONNECT":
                host = urlsplit(target).hostname or "unknown"
                await self._deny(client_writer, host, 80, "https_required")
                return

            host, port = self._parse_authority(target)
            if port != 443:
                await self._deny(client_writer, host, port, "port_not_allowed")
                return
            try:
                normalized_host = normalize_sandbox_network_host(host)
            except SandboxNetworkPolicyError:
                await self._deny(client_writer, host, port, "invalid_host")
                return
            if normalized_host not in self.allowed_hosts:
                await self._deny(
                    client_writer, normalized_host, port, "not_allowlisted"
                )
                return

            try:
                upstream_reader, upstream_writer = await self._connect_public(
                    normalized_host, port
                )
            except (OSError, asyncio.TimeoutError, ValueError) as exc:
                logger.warning(
                    "Sandbox egress connection failed",
                    extra={
                        "sandbox_job_id": self.job_id,
                        "sandbox_network_host": normalized_host,
                        "sandbox_network_port": port,
                        "sandbox_network_error": type(exc).__name__,
                    },
                )
                await self._respond(
                    client_writer,
                    502,
                    f"Sandbox egress connection failed for host {normalized_host}",
                )
                return

            client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_writer.drain()
            await self._relay(
                client_reader,
                client_writer,
                upstream_reader,
                upstream_writer,
            )
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            await self._deny(client_writer, "unknown", 0, "invalid_request")
        except (ConnectionError, OSError):
            pass
        finally:
            if upstream_writer is not None:
                upstream_writer.close()
                try:
                    await upstream_writer.wait_closed()
                except OSError:
                    pass
            client_writer.close()
            try:
                await client_writer.wait_closed()
            except OSError:
                pass

    @staticmethod
    def _parse_authority(authority: str) -> tuple[str, int]:
        parsed = urlsplit(f"//{authority}")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Invalid proxy destination port") from exc
        if not parsed.hostname or port is None or parsed.path or parsed.query:
            raise ValueError("Invalid proxy destination")
        return parsed.hostname, port

    async def _connect_public(
        self, host: str, port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        loop = asyncio.get_running_loop()
        async with asyncio.timeout(10):
            addresses = await loop.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            )
            seen: set[tuple[int, tuple[object, ...]]] = set()
            for family, socktype, proto, _canonname, sockaddr in addresses:
                address = sockaddr[0].split("%", 1)[0]
                ip = ipaddress.ip_address(address)
                if not ip.is_global:
                    continue
                key = (family, tuple(sockaddr))
                if key in seen:
                    continue
                seen.add(key)
                connection = socket.socket(family, socktype, proto)
                connection.setblocking(False)
                try:
                    await loop.sock_connect(connection, sockaddr)
                    return await asyncio.open_connection(sock=connection)
                except OSError:
                    connection.close()
        raise ValueError("No public address for allowlisted host")

    async def _deny(
        self,
        writer: asyncio.StreamWriter,
        host: str,
        port: int,
        reason: str,
    ) -> None:
        safe_host = host.replace("\r", "?").replace("\n", "?")[:253]
        self._blocked[(safe_host, port, reason)] = None
        logger.warning(
            "Sandbox network destination blocked",
            extra={
                "sandbox_job_id": self.job_id,
                "sandbox_blocked_host": safe_host,
                "sandbox_blocked_port": port,
                "sandbox_block_reason": reason,
            },
        )
        await self._respond(
            writer,
            403,
            f"Sandbox network blocked host={safe_host} port={port} reason={reason}",
        )

    @staticmethod
    async def _respond(
        writer: asyncio.StreamWriter,
        status: int,
        message: str,
    ) -> None:
        body = message.encode("utf-8", "replace")
        writer.write(
            f"HTTP/1.1 {status} {'Forbidden' if status == 403 else 'Bad Gateway'}\r\n"
            "Connection: close\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n\r\n".encode()
            + body
        )
        await writer.drain()

    @staticmethod
    async def _relay(
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        async def copy_stream(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            while chunk := await reader.read(64 * 1024):
                writer.write(chunk)
                await writer.drain()
            try:
                writer.write_eof()
                await writer.drain()
            except (AttributeError, OSError, RuntimeError):
                pass

        await asyncio.gather(
            copy_stream(client_reader, upstream_writer),
            copy_stream(upstream_reader, client_writer),
        )
