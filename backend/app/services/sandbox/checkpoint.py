"""Bounded local full-tree checkpoints with narrowly allowed runtime aliases.

Root-level Node cache links are omitted. Standard `.venv/bin/python*` links to
configured base interpreters remain durable; all other external links are rejected.
User files, directories, and safe in-workspace symlinks are preserved.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from collections import deque
from pathlib import Path
from uuid import uuid4

CHECKPOINT_VERSION = 1
MANIFEST_NAME = ".clouisle-checkpoint.json"
TREE_NAME = "workspace"
MAX_ENTRIES = 100_000
MAX_PATH_BYTES = 4096
MAX_PATH_DEPTH = 128
MAX_PAX_BYTES = 16 * 1024
COPY_BUFFER_BYTES = 64 * 1024
_SESSION_ID = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}\Z")
logger = logging.getLogger(__name__)

_RUNTIME_PYTHON_PATHS_CACHE: dict[tuple[str, ...], frozenset[Path]] = {}


def _resolve_runtime_python_paths(executables: tuple[str, ...]) -> set[Path]:
    cached = _RUNTIME_PYTHON_PATHS_CACHE.get(executables)
    if cached is not None:
        return set(cached)

    resolved_paths: set[Path] = set()
    for executable in executables:
        try:
            configured = Path(executable).resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if not configured.is_file():
            continue
        resolved_paths.add(configured)
        try:
            result = subprocess.run(
                [
                    executable,
                    "-c",
                    "import sys; print(sys._base_executable or sys.executable)",
                ],
                capture_output=True,
                check=False,
                env={"PATH": os.defpath},
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                runtime = Path(result.stdout.strip().splitlines()[-1]).resolve(
                    strict=True
                )
                if runtime.is_file():
                    resolved_paths.add(runtime)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
            continue

    _RUNTIME_PYTHON_PATHS_CACHE[executables] = frozenset(resolved_paths)
    return resolved_paths


def validate_session_id(session_id: str) -> None:
    if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id):
        raise ValueError("Invalid sandbox session ID")


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def remove_workspace_tree(root: Path) -> None:
    """Remove even read-only owned directories, without traversing symlinks."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Sandbox workspace root must be a directory")

    def writable(directory: Path) -> None:
        os.chmod(directory, stat.S_IMODE(directory.stat().st_mode) | 0o700)
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    writable(Path(entry.path))

    writable(root)
    shutil.rmtree(root)


def remove_session_temporary_trees(session_id: str, sessions_root: Path) -> None:
    """Permanent deletion also removes interrupted restore/swap staging trees."""
    validate_session_id(session_id)
    pattern = re.compile(
        rf"\.{re.escape(session_id)}\.(?:[a-z0-9_]{{8}}\.restore|[0-9a-f]{{32}}\.previous)\Z"
    )
    if not sessions_root.exists():
        return
    if sessions_root.is_symlink():
        raise ValueError("Sandbox sessions root must not be a symlink")
    removed = False
    for path in sessions_root.iterdir():
        if pattern.fullmatch(path.name):
            if path.is_symlink():
                path.unlink()
            else:
                remove_workspace_tree(path)
            removed = True
    if removed:
        fsync_directory(sessions_root)


def _check_parts(name: str) -> tuple[str, ...]:
    parts = tuple(name.split("/"))
    if (
        not name
        or "\0" in name
        or len(name.encode("utf-8", "surrogateescape")) > MAX_PATH_BYTES
        or len(parts) > MAX_PATH_DEPTH
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise ValueError(f"Unsafe checkpoint path: {name!r}")
    return parts


_RUNTIME_PYTHON_LINK = re.compile(r"python(?:[0-9]+(?:\.[0-9]+)*)?\Z")


def _is_runtime_python_link(
    source: tuple[str, ...], target: str, allowed_targets: set[Path]
) -> bool:
    if (
        len(source) != 3
        or source[:2] != (".venv", "bin")
        or not _RUNTIME_PYTHON_LINK.fullmatch(source[-1])
        or not target.startswith("/")
        or "\0" in target
        or len(target.encode("utf-8", "surrogateescape")) > MAX_PATH_BYTES
    ):
        return False
    try:
        return Path(target).resolve(strict=True) in allowed_targets
    except (OSError, RuntimeError, ValueError):
        return False


def _check_symlinks(
    links: dict[tuple[str, ...], str],
    *,
    external_aliases: set[tuple[str, ...]] | None = None,
    runtime_links: set[tuple[str, ...]] | None = None,
    runtime_python_paths: set[Path] | None = None,
) -> None:
    # Resolve against the archived tree, never against the host filesystem.
    # Only configured Python executables referenced by standard venv aliases
    # may terminate outside the workspace.
    runtime_links = runtime_links or set()
    runtime_python_paths = runtime_python_paths or set()
    for source, target in links.items():
        if source in runtime_links:
            if not _is_runtime_python_link(source, target, runtime_python_paths):
                raise ValueError(f"Unsafe runtime interpreter link: {'/'.join(source)}")
            continue
        if (
            not target
            or target.startswith("/")
            or "\0" in target
            or len(target.encode("utf-8", "surrogateescape")) > MAX_PATH_BYTES
        ):
            raise ValueError(f"Unsafe checkpoint symlink: {'/'.join(source)}")
        pending = deque(target.split("/"))
        resolved = list(source[:-1])
        hops = 0
        while pending:
            component = pending.popleft()
            if component in ("", "."):
                continue
            if component == "..":
                if not resolved:
                    raise ValueError("Checkpoint symlink escapes workspace")
                resolved.pop()
                continue
            resolved.append(component)
            if external_aliases and tuple(resolved) in external_aliases:
                raise ValueError(
                    "Checkpoint symlink escapes workspace through runtime cache"
                )
            if tuple(resolved) in runtime_links:
                if (
                    source[:2] != (".venv", "bin")
                    or not _RUNTIME_PYTHON_LINK.fullmatch(source[-1])
                    or pending
                ):
                    raise ValueError(
                        "Checkpoint symlink escapes through runtime interpreter"
                    )
                continue
            nested = links.get(tuple(resolved))
            if nested is not None:
                if nested.startswith("/") or "\0" in nested:
                    raise ValueError("Checkpoint symlink escapes workspace")
                hops += 1
                if hops > 40:
                    raise ValueError("Checkpoint symlink cycle or excessive depth")
                resolved.pop()
                pending.extendleft(reversed(nested.split("/")))
            if len(resolved) > MAX_PATH_DEPTH:
                raise ValueError("Checkpoint symlink target is too deep")


class _BoundedTarInfo(tarfile.TarInfo):
    """Reject expensive extension headers before tarfile can allocate their data."""

    def _proc_member(self, archive):
        count = getattr(archive, "_checkpoint_header_count", 0) + 1
        archive._checkpoint_header_count = count
        if count > 2 * MAX_ENTRIES + 4:
            raise ValueError("Checkpoint contains too many headers")
        if self.type == tarfile.XHDTYPE:
            if (
                self.size < 0
                or self.size > MAX_PAX_BYTES
                or getattr(archive, "_checkpoint_in_pax", False)
            ):
                raise ValueError("Invalid checkpoint extended header")
            archive._checkpoint_in_pax = True
            try:
                member = super()._proc_member(archive)
            finally:
                archive._checkpoint_in_pax = False
            if set(member.pax_headers) - {"path", "linkpath", "hdrcharset"}:
                raise ValueError("Unsupported checkpoint extended metadata")
            return member
        if self.type not in (
            tarfile.REGTYPE,
            tarfile.AREGTYPE,
            tarfile.DIRTYPE,
            tarfile.SYMTYPE,
        ):
            raise ValueError("Unsupported checkpoint entry type")
        return super()._proc_member(archive)

    def _proc_gnusparse_00(self, *args):
        raise ValueError("Sparse checkpoint entries are unsupported")

    def _proc_gnusparse_01(self, *args):
        raise ValueError("Sparse checkpoint entries are unsupported")

    def _proc_gnusparse_10(self, *args):
        raise ValueError("Sparse checkpoint entries are unsupported")


class WorkspaceCheckpointStore:
    def __init__(
        self,
        root: Path,
        *,
        runtime_cache_root: Path | None = None,
        runtime_python_paths: tuple[str, ...] = (),
    ):
        self.root = root
        self.runtime_cache_root = runtime_cache_root
        self.runtime_python_paths = _resolve_runtime_python_paths(runtime_python_paths)

    def checkpoint_path(self, session_id: str) -> Path:
        validate_session_id(session_id)
        return self.root / f"{session_id}.tar"

    def save(self, session_id: str, workspace: Path, *, max_bytes: int) -> bool:
        """Commit a streamed snapshot; retain both live data and the old snapshot on error."""
        checkpoint = self.checkpoint_path(session_id)
        try:
            root_fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return False
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.root.is_symlink():
                raise ValueError("Checkpoint root must not be a symlink")
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{session_id}.", dir=self.root
            )
            temporary = Path(temporary_name)
            backup = self.root / f".{session_id}.{uuid4().hex}.previous"
            replaced = False
            has_backup = False
            try:
                with os.fdopen(fd, "wb") as stream:
                    with tarfile.open(
                        fileobj=stream, mode="w|", format=tarfile.PAX_FORMAT
                    ) as archive:
                        manifest = json.dumps(
                            {"version": CHECKPOINT_VERSION, "session_id": session_id},
                            separators=(",", ":"),
                        ).encode("utf-8")
                        metadata = tarfile.TarInfo(MANIFEST_NAME)
                        metadata.size = len(manifest)
                        metadata.mode = 0o600
                        archive.addfile(metadata, io.BytesIO(manifest))
                        archive.members.clear()
                        self._save_tree(
                            archive, root_fd, workspace, max_bytes=max_bytes
                        )
                    stream.flush()
                    os.fsync(stream.fileno())
                if checkpoint.exists() or checkpoint.is_symlink():
                    if not stat.S_ISREG(checkpoint.lstat().st_mode):
                        raise ValueError("Checkpoint must be a regular file")
                    os.link(checkpoint, backup, follow_symlinks=False)
                    has_backup = True
                os.replace(temporary, checkpoint)
                replaced = True
                fsync_directory(self.root)
                if has_backup:
                    backup.unlink()
                    has_backup = False
            except BaseException:
                if replaced:
                    if has_backup:
                        os.replace(backup, checkpoint)
                        has_backup = False
                    else:
                        checkpoint.unlink()
                    with contextlib.suppress(OSError):
                        fsync_directory(self.root)
                raise
            finally:
                temporary.unlink(missing_ok=True)
                if has_backup:
                    backup.unlink(missing_ok=True)
        finally:
            os.close(root_fd)
        return True

    def _save_tree(
        self, archive: tarfile.TarFile, root_fd: int, workspace: Path, *, max_bytes: int
    ) -> None:
        count = 0
        total = 0
        links: dict[tuple[str, ...], str] = {}
        external_aliases: set[tuple[str, ...]] = set()
        runtime_links: set[tuple[str, ...]] = set()

        def header(parts: tuple[str, ...], info: os.stat_result) -> tarfile.TarInfo:
            nonlocal count
            count += 1
            if count > MAX_ENTRIES:
                raise ValueError("Workspace contains too many checkpoint entries")
            name = "/".join((TREE_NAME, *parts))
            _check_parts(name)
            member = tarfile.TarInfo(name)
            member.mode = stat.S_IMODE(info.st_mode)
            member.mtime = int(info.st_mtime)
            return member

        def directory(fd: int, parts: tuple[str, ...]) -> None:
            nonlocal total
            member = header(parts, os.fstat(fd))
            member.type = tarfile.DIRTYPE
            archive.addfile(member)
            archive.members.clear()
            with os.scandir(fd) as entries:
                for entry in entries:
                    child_parts = (*parts, entry.name)
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        child_fd = os.open(
                            entry.name,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd,
                        )
                        try:
                            directory(child_fd, child_parts)
                        finally:
                            os.close(child_fd)
                    elif stat.S_ISREG(info.st_mode):
                        child_fd = os.open(
                            entry.name,
                            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                            dir_fd=fd,
                        )
                        with os.fdopen(child_fd, "rb") as stream:
                            opened = os.fstat(stream.fileno())
                            if not stat.S_ISREG(opened.st_mode):
                                raise ValueError(
                                    "Workspace file changed type during checkpoint"
                                )
                            total += opened.st_size
                            if total > max_bytes:
                                raise ValueError(
                                    "Workspace exceeds sandbox checkpoint disk limit"
                                )
                            member = header(child_parts, opened)
                            member.size = opened.st_size
                            archive.addfile(member, stream)
                            archive.members.clear()
                            after = os.fstat(stream.fileno())
                            if (
                                opened.st_size,
                                opened.st_mtime_ns,
                                opened.st_ctime_ns,
                            ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                                raise ValueError(
                                    "Workspace file changed during checkpoint"
                                )
                    elif stat.S_ISLNK(info.st_mode):
                        linkname = os.readlink(entry.name, dir_fd=fd)
                        if (
                            len(linkname.encode("utf-8", "surrogateescape"))
                            > MAX_PATH_BYTES
                        ):
                            raise ValueError("Checkpoint symlink target is too long")
                        if _is_runtime_python_link(
                            child_parts, linkname, self.runtime_python_paths
                        ):
                            runtime_links.add(child_parts)
                        if (
                            child_parts == ("node_modules",)
                            and self.runtime_cache_root is not None
                        ):
                            cache = self.runtime_cache_root.resolve()
                            target = Path(linkname)
                            resolved = (
                                target if target.is_absolute() else workspace / target
                            ).resolve()
                            if resolved == cache or cache in resolved.parents:
                                external_aliases.add(child_parts)
                                continue
                        member = header(child_parts, info)
                        member.type = tarfile.SYMTYPE
                        member.linkname = linkname
                        links[child_parts] = member.linkname
                        archive.addfile(member)
                        archive.members.clear()
                    else:
                        raise ValueError(
                            "Workspace contains an unsupported checkpoint node"
                        )

        directory(root_fd, ())
        _check_symlinks(
            links,
            external_aliases=external_aliases,
            runtime_links=runtime_links,
            runtime_python_paths=self.runtime_python_paths,
        )

    def restore(
        self, session_id: str, destination: Path, *, max_bytes: int, force: bool = False
    ) -> bool:
        """Validate privately before publishing, optionally replacing dirty live data."""
        checkpoint = self.checkpoint_path(session_id)
        if self.root.is_symlink():
            raise ValueError("Checkpoint root must not be a symlink")
        try:
            fd = os.open(checkpoint, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return False
        temporary: Path | None = None
        backup: Path | None = None
        published = False
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Checkpoint must be a regular file")
            if (
                info.st_size
                > max_bytes + (MAX_ENTRIES + 2) * (MAX_PAX_BYTES + 1536) + 10240
            ):
                raise ValueError("Checkpoint archive exceeds disk and metadata limits")
            if destination.exists() or destination.is_symlink():
                if not force:
                    raise FileExistsError(destination)
                if destination.is_symlink() or not destination.is_dir():
                    raise ValueError("Sandbox session root must be a directory")
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            temporary = Path(
                tempfile.mkdtemp(
                    prefix=f".{session_id}.", suffix=".restore", dir=destination.parent
                )
            )
            with os.fdopen(fd, "rb") as stream:
                fd = -1
                self._restore_tree(stream, temporary, session_id, max_bytes=max_bytes)
            if destination.exists():
                previous = destination.parent / f".{session_id}.{uuid4().hex}.previous"
                os.rename(destination, previous)
                backup = previous
            os.rename(temporary, destination)
            published = True
            fsync_directory(destination.parent)
        except BaseException:
            if published:
                remove_workspace_tree(destination)
            if backup is not None:
                os.rename(backup, destination)
                backup = None
            if published:
                with contextlib.suppress(OSError):
                    fsync_directory(destination.parent)
            raise
        finally:
            if fd >= 0:
                os.close(fd)
            if temporary is not None and temporary.exists():
                remove_workspace_tree(temporary)
        if backup is not None:
            try:
                remove_workspace_tree(backup)
            except (OSError, ValueError):
                # Publication is already durable. A cleanup error must not report
                # a failed restore after discarding the original live directory.
                # Permanent session deletion also reaps these staging trees.
                logger.warning(
                    "Unable to remove displaced sandbox workspace %s",
                    backup,
                    exc_info=True,
                )
        return True

    def _restore_tree(
        self, stream, root: Path, session_id: str, *, max_bytes: int
    ) -> None:
        seen: dict[tuple[str, ...], str] = {}
        directories: list[tuple[Path, int]] = []
        links: dict[tuple[str, ...], str] = {}
        runtime_links: set[tuple[str, ...]] = set()
        total = 0
        count = 0
        manifest_seen = False
        with tarfile.open(
            fileobj=stream, mode="r|", tarinfo=_BoundedTarInfo
        ) as archive:
            for member in archive:
                # Stream mode otherwise still accumulates every TarInfo in members.
                archive.members.clear()
                if not manifest_seen:
                    if (
                        member.name != MANIFEST_NAME
                        or not member.isreg()
                        or not 0 < member.size <= 1024
                    ):
                        raise ValueError("Missing or invalid checkpoint manifest")
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        raise ValueError("Missing checkpoint manifest data")
                    with extracted:
                        metadata = json.loads(extracted.read(1025))
                    if (
                        not isinstance(metadata, dict)
                        or type(metadata.get("version")) is not int
                        or metadata
                        != {"version": CHECKPOINT_VERSION, "session_id": session_id}
                    ):
                        raise ValueError(
                            "Checkpoint version or session ownership mismatch"
                        )
                    manifest_seen = True
                    continue
                parts = _check_parts(member.name)
                if parts[0] != TREE_NAME:
                    raise ValueError("Checkpoint entry is outside workspace")
                relative = parts[1:]
                count += 1
                if count > MAX_ENTRIES:
                    raise ValueError("Checkpoint contains too many entries")
                if relative in seen or (
                    relative and seen.get(relative[:-1]) != "directory"
                ):
                    raise ValueError("Duplicate checkpoint entry or unsafe parent")
                if member.mode < 0 or member.mode > 0o7777 or member.size < 0:
                    raise ValueError("Invalid checkpoint entry metadata")
                target = root.joinpath(*relative)
                if member.isdir():
                    if member.size:
                        raise ValueError(
                            "Checkpoint directory contains unexpected data"
                        )
                    if relative:
                        target.mkdir(mode=0o700)
                    directories.append((target, member.mode))
                    seen[relative] = "directory"
                elif member.isreg() and relative:
                    total += member.size
                    if total > max_bytes:
                        raise ValueError("Checkpoint exceeds sandbox disk limit")
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        raise ValueError("Missing checkpoint file data")
                    with extracted, target.open("xb") as output:
                        remaining = member.size
                        while remaining:
                            block = extracted.read(min(COPY_BUFFER_BYTES, remaining))
                            if not block:
                                raise ValueError("Truncated checkpoint file")
                            output.write(block)
                            remaining -= len(block)
                        output.flush()
                        os.fchmod(output.fileno(), member.mode)
                        os.fsync(output.fileno())
                    seen[relative] = "file"
                elif member.issym() and relative:
                    if member.size:
                        raise ValueError("Checkpoint symlink contains unexpected data")
                    links[relative] = member.linkname
                    if _is_runtime_python_link(
                        relative, member.linkname, self.runtime_python_paths
                    ):
                        runtime_links.add(relative)
                    seen[relative] = "symlink"
                else:
                    raise ValueError("Unsupported checkpoint entry")
            end_offset = archive.offset
        if not manifest_seen or seen.get(()) != "directory":
            raise ValueError("Checkpoint does not contain a complete workspace")
        stream.seek(end_offset)
        padding_bytes = 0
        while block := stream.read(COPY_BUFFER_BYTES):
            padding_bytes += len(block)
            if padding_bytes > tarfile.RECORDSIZE + tarfile.BLOCKSIZE:
                raise ValueError("Checkpoint has excessive archive padding")
            if any(block):
                raise ValueError("Checkpoint has unexpected trailing data")
        if padding_bytes < 1024 or padding_bytes % tarfile.BLOCKSIZE:
            raise ValueError("Checkpoint is missing its complete archive footer")
        _check_symlinks(
            links,
            runtime_links=runtime_links,
            runtime_python_paths=self.runtime_python_paths,
        )
        for parts, target in links.items():
            root.joinpath(*parts).symlink_to(target)
        # Children remain accessible until every file/link is in place. Apply
        # read-only directory modes last, holding the descriptor while syncing.
        for directory, mode in reversed(directories):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fchmod(fd, mode)
                os.fsync(fd)
            finally:
                os.close(fd)

    def delete(self, session_id: str) -> None:
        checkpoint = self.checkpoint_path(session_id)
        if self.root.is_symlink():
            raise ValueError("Checkpoint root must not be a symlink")
        if not self.root.exists():
            return
        pattern = re.compile(
            rf"\.{re.escape(session_id)}\.(?:[a-z0-9_]{{8}}|[0-9a-f]{{32}}\.previous)\Z"
        )
        removed = False
        for path in self.root.iterdir():
            if path == checkpoint or pattern.fullmatch(path.name):
                path.unlink()
                removed = True
        if removed:
            fsync_directory(self.root)
