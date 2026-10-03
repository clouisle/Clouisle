"""Real-filesystem regressions for local recoverable sandbox workspaces."""

from __future__ import annotations

import asyncio
import io
import json
import multiprocessing
import os
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest

from app.services.sandbox import checkpoint
from app.services.sandbox import workspace as workspace_module
from app.services.sandbox.workspace import SandboxWorkspaceManager


@pytest.fixture
def manager(tmp_path: Path) -> SandboxWorkspaceManager:
    return SandboxWorkspaceManager(
        root=str(tmp_path / "jobs"), checkpoint_root=str(tmp_path / "checkpoints")
    )


def _tree(root: Path) -> dict:
    result = {".": ("directory", stat.S_IMODE(root.lstat().st_mode))}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            mode = stat.S_IMODE(path.lstat().st_mode)
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                result[relative] = ("symlink", mode, os.readlink(path))
            elif path.is_dir():
                result[relative] = ("directory", mode)
            elif path.is_file():
                result[relative] = ("file", mode, path.read_bytes())
            else:
                result[relative] = ("unsupported", mode)
    return result


def _entry(name: str, kind=tarfile.REGTYPE, *, link: str = "", mode: int = 0o600):
    member = tarfile.TarInfo(name)
    member.type = kind
    member.linkname = link
    member.mode = mode
    return member


def _archive(
    manager: SandboxWorkspaceManager,
    entries=(),
    *,
    session_id: str = "session",
    owner: str = "session",
    version=checkpoint.CHECKPOINT_VERSION,
    include_root: bool = True,
) -> Path:
    manager.checkpoint_root.mkdir(parents=True, exist_ok=True)
    path = manager.checkpoints.checkpoint_path(session_id)
    with tarfile.open(path, "w", format=tarfile.PAX_FORMAT) as archive:
        data = json.dumps({"version": version, "session_id": owner}).encode()
        manifest = _entry(checkpoint.MANIFEST_NAME)
        manifest.size = len(data)
        archive.addfile(manifest, io.BytesIO(data))
        if include_root:
            archive.addfile(_entry("workspace", tarfile.DIRTYPE, mode=0o700))
        for member, data in entries:
            if data is not None:
                member.size = len(data)
            archive.addfile(member, io.BytesIO(data) if data is not None else None)
    return path


@pytest.mark.asyncio
async def test_save_evict_restore_preserves_full_tree_and_modes(manager):
    async with manager.session_lock("session"):
        live = manager.restore_session("session")
        (live.input_dir / "binary.dat").write_bytes(bytes(range(256)) * 1000)
        (live.input_dir / "binary.dat").chmod(0o640)
        (live.output_dir / "executable").write_bytes(b"#!/bin/sh\necho checkpoint\n")
        (live.output_dir / "executable").chmod(0o751)
        (live.output_dir / "empty" / "nested").mkdir(parents=True)
        (live.output_dir / "empty").chmod(0o550)
        (live.output_dir / "copy").symlink_to("../input/binary.dat")
        # Unicode and long path names exercise bounded PAX handling, not just USTAR.
        (live.output_dir / ("结果" * 30 + ".txt")).write_text(
            "完整保存", encoding="utf-8"
        )
        live.root.chmod(0o750)
        expected = _tree(live.root)

        assert manager.save_checkpoint("session") is True
        saved = manager.checkpoints.checkpoint_path("session")
        assert saved.is_file()
        assert live.root not in saved.parents
        assert manager.evict_session("session") is True
        assert not live.root.exists()
        assert saved.exists()

        restored = manager.restore_session("session", allow_empty=False)
        assert _tree(restored.root) == expected
        # Internal runtime cleanup does not remove its recoverable snapshot.
        manager.cleanup_session("session")
        assert saved.exists()
        assert _tree(manager.restore_session("session").root) == expected


@pytest.mark.asyncio
async def test_second_checkpoint_replaces_first_including_deleted_files(manager):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        (live.root / "old.txt").write_bytes(b"first snapshot")
        manager.save_checkpoint("session")
        first = manager.checkpoints.checkpoint_path("session").read_bytes()
        (live.root / "old.txt").unlink()
        (live.root / "new.txt").write_bytes(b"second snapshot")
        (live.root / "new.txt").chmod(0o604)
        expected = _tree(live.root)
        manager.save_checkpoint("session")
        assert manager.checkpoints.checkpoint_path("session").read_bytes() != first
        manager.cleanup_session("session")
        assert _tree(manager.restore_session("session").root) == expected
        assert not (live.root / "old.txt").exists()
        assert list(manager.checkpoint_root.iterdir()) == [
            manager.checkpoints.checkpoint_path("session")
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "symlink",
        "fifo",
        "disk",
        "entries",
        "archive",
        "data_fsync",
        "directory_fsync",
        "rename",
    ],
)
async def test_failed_eviction_keeps_live_tree_and_previous_snapshot(
    manager, tmp_path, monkeypatch, failure
):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        value = live.root / "value.txt"
        value.write_bytes(b"committed")
        manager.save_checkpoint("session")
        saved = manager.checkpoints.checkpoint_path("session")
        old_snapshot = saved.read_bytes()
        value.write_bytes(b"uncommitted changes")

        def fail(*args, **kwargs):
            raise OSError("injected storage failure")

        if failure == "symlink":
            outside = tmp_path / "outside.txt"
            outside.write_bytes(b"must not be read")
            (live.root / "outside-link").symlink_to(outside)
        elif failure == "fifo":
            os.mkfifo(live.root / "pipe")
        elif failure == "disk":
            monkeypatch.setattr(workspace_module.settings, "SANDBOX_MAX_DISK_MB", 0)
        elif failure == "entries":
            monkeypatch.setattr(checkpoint, "MAX_ENTRIES", 5)
        elif failure == "archive":
            original_addfile = tarfile.TarFile.addfile

            def addfile(archive, member, fileobj=None):
                if member.name == "workspace/value.txt":
                    fail()
                return original_addfile(archive, member, fileobj)

            monkeypatch.setattr(tarfile.TarFile, "addfile", addfile)
        elif failure == "data_fsync":
            monkeypatch.setattr(checkpoint.os, "fsync", fail)
        elif failure == "directory_fsync":
            monkeypatch.setattr(checkpoint, "fsync_directory", fail)
        elif failure == "rename":
            monkeypatch.setattr(checkpoint.os, "replace", fail)
        expected = _tree(live.root)

        with pytest.raises((ValueError, OSError), match="checkpoint|storage|Workspace"):
            manager.evict_session("session")
        assert _tree(live.root) == expected
        assert saved.read_bytes() == old_snapshot
        assert list(manager.checkpoint_root.iterdir()) == [saved]


@pytest.mark.asyncio
async def test_missing_workspace_does_not_create_checkpoint_or_initialize_used_session(
    manager,
):
    async with manager.session_lock("session"):
        assert manager.save_checkpoint("session") is False
        assert manager.evict_session("session") is False
        assert not manager.get_session_root("session").exists()
        assert not manager.checkpoint_root.exists()
        with pytest.raises(FileNotFoundError):
            manager.restore_session("session", allow_empty=False)
        assert not manager.get_session_root("session").exists()
        fresh = manager.restore_session("session")
        assert {path.name for path in fresh.root.iterdir()} == {
            "input",
            "output",
            "tmp",
            "logs",
        }


@pytest.mark.asyncio
async def test_restore_reuses_live_directory_without_mutating_it(manager):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        manager.save_checkpoint("session")
        (live.root / "fresh.txt").write_bytes(b"same round")
        live.logs_dir.rmdir()
        expected = _tree(live.root)
        assert manager.restore_session("session").root == live.root
        assert _tree(live.root) == expected
        assert not live.logs_dir.exists()


@pytest.mark.asyncio
async def test_forced_restore_rolls_back_uncommitted_live_data(manager):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        value = live.root / "value.txt"
        value.write_bytes(b"stable boundary")
        value.chmod(0o640)
        manager.save_checkpoint("session")
        expected = _tree(live.root)
        value.write_bytes(b"interrupted round")
        value.chmod(0o777)
        (live.root / "uncommitted.txt").write_bytes(
            b"discard this only after validation"
        )
        restored = manager.restore_session("session", force=True)
        assert _tree(restored.root) == expected
        assert list(manager.sessions_root.iterdir()) == [live.root]


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_forced_restore_missing_or_corrupt_checkpoint_retains_dirty_live_data(
    manager, missing
):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        (live.root / "sole-data.txt").write_bytes(b"do not silently discard")
        if not missing:
            manager.checkpoint_root.mkdir()
            manager.checkpoints.checkpoint_path("session").write_bytes(
                b"not a tar archive"
            )
        expected = _tree(live.root)
        with pytest.raises((FileNotFoundError, ValueError, tarfile.TarError)):
            manager.restore_session("session", force=True)
        assert _tree(live.root) == expected
        assert list(manager.sessions_root.iterdir()) == [live.root]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["publish", "fsync"])
async def test_forced_restore_publication_failure_rolls_back_dirty_directory(
    manager, monkeypatch, failure
):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        (live.root / "value.txt").write_bytes(b"stable")
        manager.save_checkpoint("session")
        old_checkpoint = manager.checkpoints.checkpoint_path("session").read_bytes()
        (live.root / "value.txt").write_bytes(b"dirty")
        expected = _tree(live.root)
        if failure == "publish":
            rename = os.rename

            def fail_publish(source, target):
                if Path(source).name.endswith(".restore"):
                    raise OSError("injected publish failure")
                return rename(source, target)

            monkeypatch.setattr(checkpoint.os, "rename", fail_publish)
        else:

            def fail_fsync(path):
                raise OSError("injected directory fsync failure")

            monkeypatch.setattr(checkpoint, "fsync_directory", fail_fsync)
        with pytest.raises(OSError, match="injected"):
            manager.restore_session("session", force=True)
        assert _tree(live.root) == expected
        assert (
            manager.checkpoints.checkpoint_path("session").read_bytes()
            == old_checkpoint
        )
        assert list(manager.sessions_root.iterdir()) == [live.root]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_path",
    [
        "/escaped.txt",
        "workspace/../../escaped.txt",
        "workspace/../escaped.txt",
        "workspace//bad",
        "workspace/./bad",
        "elsewhere/bad",
    ],
)
async def test_malicious_archive_paths_cannot_escape_or_publish_empty_workspace(
    manager, tmp_path, bad_path
):
    saved = _archive(manager, [(_entry(bad_path), b"hostile")])
    original = saved.read_bytes()
    async with manager.session_lock("session"):
        with pytest.raises(ValueError):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()
        assert not (tmp_path / "escaped.txt").exists()
        assert not (manager.sessions_root / "escaped.txt").exists()
        assert saved.read_bytes() == original
        assert list(manager.sessions_root.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        tarfile.LNKTYPE,
        tarfile.FIFOTYPE,
        tarfile.CHRTYPE,
        tarfile.BLKTYPE,
        tarfile.GNUTYPE_SPARSE,
    ],
)
async def test_restore_rejects_unsupported_archive_nodes(manager, kind):
    _archive(
        manager, [(_entry("workspace/unsafe", kind, link="workspace/target"), None)]
    )
    async with manager.session_lock("session"):
        with pytest.raises(ValueError, match="Unsupported"):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()
        assert list(manager.sessions_root.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["../../escaped", "/tmp/escaped"])
async def test_restore_rejects_escaping_symlink_targets(manager, target):
    _archive(manager, [(_entry("workspace/link", tarfile.SYMTYPE, link=target), None)])
    async with manager.session_lock("session"):
        with pytest.raises(ValueError, match="symlink"):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()


@pytest.mark.asyncio
async def test_restore_rejects_user_symlink_to_runtime_interpreter(manager):
    runtime = next(iter(manager.checkpoints.runtime_python_paths))
    _archive(
        manager,
        [
            (_entry("workspace/.venv", tarfile.DIRTYPE), None),
            (_entry("workspace/.venv/bin", tarfile.DIRTYPE), None),
            (
                _entry(
                    "workspace/.venv/bin/python3", tarfile.SYMTYPE, link=str(runtime)
                ),
                None,
            ),
            (
                _entry("workspace/escape", tarfile.SYMTYPE, link=".venv/bin/python3"),
                None,
            ),
        ],
    )
    async with manager.session_lock("session"):
        with pytest.raises(ValueError, match="runtime interpreter"):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()


@pytest.mark.asyncio
async def test_restore_rejects_file_below_symlink_and_chained_escape(manager):
    async with manager.session_lock("session"):
        _archive(
            manager,
            [
                (_entry("workspace/link", tarfile.SYMTYPE, link="output"), None),
                (_entry("workspace/link/child"), b"unsafe"),
            ],
        )
        with pytest.raises(ValueError, match="parent"):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()
        _archive(
            manager,
            [
                (_entry("workspace/dir", tarfile.DIRTYPE), None),
                (_entry("workspace/dir/link", tarfile.SYMTYPE, link=".."), None),
                (
                    _entry(
                        "workspace/escape",
                        tarfile.SYMTYPE,
                        link="dir/link/../../outside",
                    ),
                    None,
                ),
            ],
        )
        with pytest.raises(ValueError, match="escapes"):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owner,version", [("another-session", 1), ("session", 999), ("session", True)]
)
async def test_restore_validates_version_and_session_ownership(manager, owner, version):
    _archive(manager, owner=owner, version=version)
    async with manager.session_lock("session"):
        with pytest.raises(ValueError, match="version or session"):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    [
        "not_tar",
        "truncated_file",
        "missing_footer",
        "trailing_data",
        "missing_root",
        "duplicate",
    ],
)
async def test_corrupt_archive_never_publishes_a_partial_or_empty_live_directory(
    manager, corruption
):
    entries = [(_entry("workspace/value"), b"payload" * 200)]
    if corruption == "duplicate":
        entries.append((_entry("workspace/value"), b"other"))
    saved = _archive(manager, entries, include_root=corruption != "missing_root")
    if corruption == "not_tar":
        saved.write_bytes(b"not a tar")
    elif corruption == "truncated_file":
        saved.write_bytes(saved.read_bytes()[:2300])
    elif corruption == "missing_footer":
        # Manifest (header+block), root header, file header+three data blocks.
        saved.write_bytes(saved.read_bytes()[:3584])
    elif corruption == "trailing_data":
        with saved.open("ab") as stream:
            stream.write(b"unexpected")
    async with manager.session_lock("session"):
        with pytest.raises((ValueError, tarfile.TarError)):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()
        assert list(manager.sessions_root.iterdir()) == []


@pytest.mark.asyncio
async def test_restore_bounds_file_bytes_entry_count_and_pax_metadata(
    manager, monkeypatch
):
    async with manager.session_lock("session"):
        _archive(manager, [(_entry("workspace/too-large"), b"x" * (1024 * 1024 + 1))])
        monkeypatch.setattr(workspace_module.settings, "SANDBOX_MAX_DISK_MB", 1)
        with pytest.raises(ValueError, match="disk limit"):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()

        _archive(manager, [(_entry(f"workspace/{index}"), b"") for index in range(8)])
        monkeypatch.setattr(checkpoint, "MAX_ENTRIES", 5)
        with pytest.raises(ValueError, match="too many"):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()
        monkeypatch.setattr(checkpoint, "MAX_ENTRIES", 100_000)

        pax = _entry("extended", tarfile.XHDTYPE)
        _archive(manager, [(pax, b"x" * (checkpoint.MAX_PAX_BYTES + 1))])
        with pytest.raises(ValueError, match="extended header"):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()

        sparse = _entry("workspace/sparse")
        sparse.pax_headers = {"GNU.sparse.map": "0,1", "GNU.sparse.realsize": "1"}
        _archive(manager, [(sparse, b"x")])
        with pytest.raises(ValueError, match="Sparse|extended metadata"):
            manager.restore_session("session")
        assert not manager.get_session_root("session").exists()


@pytest.mark.asyncio
async def test_delete_removes_live_and_checkpoint_but_never_lock_inode(manager):
    async with manager.session_lock("session") as locked_fd:
        lock = manager.locks_root / "session.lock"
        inode = os.fstat(locked_fd).st_ino
        live = manager.prepare_session("session")
        (live.root / "value").write_bytes(b"saved")
        manager.save_checkpoint("session")
        manager.delete_session("session")
        assert not live.root.exists()
        assert not manager.checkpoints.checkpoint_path("session").exists()
        assert lock.stat().st_ino == inode
        manager.delete_session("session")
    async with manager.session_lock("session") as locked_fd:
        assert os.fstat(locked_fd).st_ino == inode


@pytest.mark.parametrize(
    "session_id",
    ["", ".", "..", "../other", "/absolute", "a/b", "a\\b", "a\0b", "a" * 129],
)
def test_session_path_components_are_validated_before_any_write(manager, session_id):
    with pytest.raises(ValueError, match="session ID"):
        manager.prepare_session(session_id)
    with pytest.raises(ValueError, match="session ID"):
        manager.save_checkpoint(session_id)
    with pytest.raises(ValueError, match="session ID"):
        manager.delete_session(session_id)
    assert not manager.sessions_root.exists()
    assert not manager.checkpoint_root.exists()


@pytest.mark.asyncio
async def test_runtime_parent_and_checkpoint_symlinks_are_not_followed(
    manager, tmp_path
):
    outside = tmp_path / "outside"
    outside.mkdir()
    manager.root.mkdir()
    manager.sessions_root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        manager.save_checkpoint("session")
    with pytest.raises(ValueError, match="symlink"):
        manager.restore_session("session")
    assert list(outside.iterdir()) == []
    manager.sessions_root.unlink()
    manager.checkpoint_root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        manager.restore_session("session")
    assert list(outside.iterdir()) == []


def _lock_in_process(root: str, ready, acquired, release):
    async def run():
        manager = SandboxWorkspaceManager(root=root)
        ready.set()
        async with manager.session_lock("session"):
            acquired.set()
            if not await asyncio.to_thread(release.wait, 15):
                raise TimeoutError("Parent did not release test child")

    asyncio.run(run())


@pytest.mark.asyncio
async def test_two_processes_serialize_on_one_stable_native_lock(manager):
    context = multiprocessing.get_context("spawn")
    ready, acquired, release = context.Event(), context.Event(), context.Event()
    child = context.Process(
        target=_lock_in_process, args=(str(manager.root), ready, acquired, release)
    )
    try:
        async with manager.session_lock("session") as locked_fd:
            inode = os.fstat(locked_fd).st_ino
            child.start()
            assert await asyncio.to_thread(ready.wait, 15)
            # The child is alive, but its nonblocking acquisition cannot enter.
            assert not await asyncio.to_thread(acquired.wait, 0.2)
        assert await asyncio.to_thread(acquired.wait, 15)
        assert (manager.locks_root / "session.lock").stat().st_ino == inode
        release.set()
        await asyncio.to_thread(child.join, 15)
        assert child.exitcode == 0
        async with manager.session_lock("session") as locked_fd:
            assert os.fstat(locked_fd).st_ino == inode
    finally:
        release.set()
        if child.pid is not None and child.is_alive():
            child.terminate()
            await asyncio.to_thread(child.join, 15)


@pytest.mark.asyncio
async def test_waiting_lock_cancellation_closes_its_fd_without_releasing_owner(
    manager, monkeypatch
):
    async with manager.session_lock("session") as owner_fd:
        opened = []
        original_open = os.open

        def recording_open(*args, **kwargs):
            fd = original_open(*args, **kwargs)
            opened.append(fd)
            return fd

        monkeypatch.setattr(workspace_module.os, "open", recording_open)

        async def wait_for_lock():
            async with manager.session_lock("session"):
                pytest.fail("Cancelled waiter acquired a held lock")

        waiter = asyncio.create_task(wait_for_lock())
        await asyncio.sleep(0.1)
        assert len(opened) == 1
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        with pytest.raises(OSError):
            os.fstat(opened[0])
        assert os.fstat(owner_fd)
        assert (manager.locks_root / "session.lock").exists()
    async with asyncio.timeout(1):
        async with manager.session_lock("session"):
            pass


@pytest.mark.asyncio
async def test_lock_body_exception_releases_fd_and_keeps_lock_file(manager):
    locked_fd = None
    with pytest.raises(RuntimeError, match="body failure"):
        async with manager.session_lock("session") as locked_fd:
            raise RuntimeError("body failure")
    with pytest.raises(OSError):
        os.fstat(locked_fd)
    async with asyncio.timeout(1):
        async with manager.session_lock("session"):
            assert (manager.locks_root / "session.lock").is_file()


@pytest.mark.asyncio
async def test_cached_node_modules_alias_is_transient_and_never_archives_cache_bytes(
    manager, monkeypatch
):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        cached = manager.cache_root / "node-env" / "node_modules"
        cached.mkdir(parents=True)
        cache_marker = b"CACHED_DEPENDENCY_NOT_WORKSPACE_DATA"
        (cached / "dependency.bin").write_bytes(cache_marker * 40_000)
        (cached / "unsafe-dependency-link").symlink_to(
            "/outside/cache-is-not-traversed"
        )
        (live.root / "node_modules").symlink_to(cached, target_is_directory=True)
        (live.root / "user-script.js").write_bytes(b"console.log('durable user code')")
        monkeypatch.setattr(workspace_module.settings, "SANDBOX_MAX_DISK_MB", 1)
        assert manager.save_checkpoint("session") is True
        saved = manager.checkpoints.checkpoint_path("session")
        with tarfile.open(saved, "r") as archive:
            names = archive.getnames()
        assert not any(name.startswith("workspace/node_modules") for name in names)
        assert cache_marker not in saved.read_bytes()
        assert manager.evict_session("session") is True
        restored = manager.restore_session("session", allow_empty=False)
        assert (
            restored.root / "user-script.js"
        ).read_bytes() == b"console.log('durable user code')"
        assert not (restored.root / "node_modules").exists()
        assert not (restored.root / "node_modules").is_symlink()
        assert (cached / "dependency.bin").read_bytes() == cache_marker * 40_000


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["outside", "nested", "indirect"])
async def test_node_modules_exception_does_not_allow_other_external_links(
    manager, tmp_path, kind
):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        (live.root / "user-file").write_bytes(b"retain on failed checkpoint")
        if kind == "outside":
            outside = tmp_path / "not-the-dependency-cache"
            outside.mkdir()
            (live.root / "node_modules").symlink_to(outside, target_is_directory=True)
        else:
            cached = manager.cache_root / "node-env" / "node_modules"
            cached.mkdir(parents=True)
            if kind == "nested":
                (live.output_dir / "node_modules").symlink_to(
                    cached, target_is_directory=True
                )
            else:
                (live.root / "node_modules").symlink_to(
                    cached, target_is_directory=True
                )
                (live.root / "user-link").symlink_to("node_modules/private-file")
        expected = _tree(live.root)
        with pytest.raises(ValueError, match="symlink"):
            manager.evict_session("session")
        assert _tree(live.root) == expected
        assert not manager.checkpoints.checkpoint_path("session").exists()


@pytest.mark.asyncio
async def test_actual_user_node_modules_directory_is_durable(manager):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        modules = live.root / "node_modules"
        modules.mkdir()
        (modules / "own-package.js").write_bytes(b"user-managed package")
        expected = _tree(live.root)
        manager.evict_session("session")
        assert _tree(manager.restore_session("session").root) == expected


@pytest.mark.asyncio
async def test_forced_restore_malicious_archive_keeps_dirty_live_data(manager):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        (live.root / "dirty-value").write_bytes(
            b"retain until checkpoint fully validates"
        )
        expected = _tree(live.root)
        _archive(manager, [(_entry("workspace/../../escaped"), b"malicious")])
        with pytest.raises(ValueError, match="Unsafe"):
            manager.restore_session("session", force=True)
        assert _tree(live.root) == expected
        assert list(manager.sessions_root.iterdir()) == [live.root]


@pytest.mark.asyncio
async def test_permanent_delete_reaps_interrupted_staging_without_prefix_collisions(
    manager,
):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        (live.root / "value").write_bytes(b"saved user data")
        manager.save_checkpoint("session")
        for name in (".session.abcdefgh", ".session." + "a" * 32 + ".previous"):
            (manager.checkpoint_root / name).write_bytes(b"interrupted snapshot data")
        for name in (".session.abcdefgh.restore", ".session." + "a" * 32 + ".previous"):
            staging = manager.sessions_root / name
            staging.mkdir()
            (staging / "value").write_bytes(b"interrupted restore data")
        other_checkpoint = manager.checkpoint_root / ".session.other.abcdefgh"
        other_checkpoint.write_bytes(b"different session must survive")
        other_staging = manager.sessions_root / ".session.other.abcdefgh.restore"
        other_staging.mkdir()
        (other_staging / "value").write_bytes(b"different session must survive")
        manager.delete_session("session")
        assert list(manager.checkpoint_root.iterdir()) == [other_checkpoint]
        assert list(manager.sessions_root.iterdir()) == [other_staging]
        assert other_checkpoint.read_bytes() == b"different session must survive"
        assert (
            other_staging / "value"
        ).read_bytes() == b"different session must survive"
        assert (manager.locks_root / "session.lock").exists()


@pytest.mark.asyncio
async def test_committed_forced_restore_defers_failed_old_tree_cleanup_to_permanent_delete(
    manager, monkeypatch
):
    async with manager.session_lock("session"):
        live = manager.prepare_session("session")
        value = live.root / "value"
        value.write_bytes(b"committed")
        manager.save_checkpoint("session")
        expected = _tree(live.root)
        value.write_bytes(b"dirty previous tree")
        remove_tree = checkpoint.remove_workspace_tree

        def fail_old_tree(path):
            if path.name.endswith(".previous"):
                raise OSError("injected displaced-directory removal failure")
            return remove_tree(path)

        with monkeypatch.context() as patch:
            patch.setattr(checkpoint, "remove_workspace_tree", fail_old_tree)
            restored = manager.restore_session("session", force=True)
            assert _tree(restored.root) == expected
        leftovers = [
            path for path in manager.sessions_root.iterdir() if path != live.root
        ]
        assert len(leftovers) == 1
        assert (leftovers[0] / "value").read_bytes() == b"dirty previous tree"
        manager.delete_session("session")
        assert list(manager.sessions_root.iterdir()) == []
        assert list(manager.checkpoint_root.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_python_workspace_environment_and_installed_package_survive_restore(
    manager, legacy
):
    from app.services.sandbox.python_env import PythonEnvironmentManager

    environments = PythonEnvironmentManager(manager.cache_root)
    async with manager.session_lock("python-environment"):
        workspace = manager.prepare_session("python-environment")
        if legacy:
            subprocess.run(
                [
                    environments.python_binary(),
                    "-m",
                    "venv",
                    str(workspace.root / ".venv"),
                ],
                check=True,
                capture_output=True,
            )
        environment = environments.ensure_workspace_environment(workspace.root)
        interpreter = environment / "bin" / "python"
        packages = subprocess.check_output(
            [
                str(interpreter),
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ],
            text=True,
        ).strip()
        (Path(packages) / "checkpoint_dependency.py").write_text("value = 'retained'\n")
        assert manager.evict_session("python-environment")
        restored = manager.restore_session("python-environment", allow_empty=False)
        output = subprocess.check_output(
            [
                str(restored.root / ".venv/bin/python"),
                "-c",
                "import checkpoint_dependency; print(checkpoint_dependency.value)",
            ],
            text=True,
        )
        assert output == "retained\n"
