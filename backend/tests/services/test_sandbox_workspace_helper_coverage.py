from pathlib import Path

import pytest

from app.services.sandbox.workspace import SandboxWorkspaceManager


def test_prepares_resolves_sizes_and_cleans_workspace(tmp_path: Path):
    manager = SandboxWorkspaceManager(root=str(tmp_path / "workspaces"))
    workspace = manager.prepare("job-1")

    assert {path.name for path in workspace.root.iterdir()} == {
        "input",
        "output",
        "tmp",
        "logs",
    }
    assert manager.cache_root == tmp_path / "cache"
    assert manager.resolve_workspace_path(workspace, "/workspace") == workspace.root
    assert manager.resolve_workspace_path(
        workspace, "/workspace/output/result.txt"
    ) == (workspace.output_dir / "result.txt")

    result = workspace.output_dir / "result.txt"
    result.write_bytes(b"ok")
    assert manager.workspace_size_bytes(workspace) == 2

    manager.cleanup("job-1")
    manager.cleanup("missing-job")
    assert not workspace.root.exists()


def test_session_cleanup_and_workspace_path_escape_are_handled(tmp_path: Path):
    manager = SandboxWorkspaceManager(root=str(tmp_path / "workspaces"))
    workspace = manager.prepare_session("session-1")

    with pytest.raises(ValueError, match="escapes workspace"):
        manager.resolve_workspace_path(workspace, "/workspace/../../outside.txt")

    manager.cleanup_session("session-1")
    manager.cleanup_session("missing-session")
    assert not workspace.root.exists()


def test_rejects_symlink_escape_and_excludes_it_from_workspace_size(tmp_path: Path):
    manager = SandboxWorkspaceManager(root=str(tmp_path / "workspaces"))
    workspace = manager.prepare("job-1")
    target = tmp_path / "outside.txt"
    target.write_bytes(b"outside")
    link = workspace.output_dir / "outside.txt"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="escapes workspace"):
        manager.resolve_workspace_path(workspace, "/workspace/output/outside.txt")

    assert manager.workspace_size_bytes(workspace) == 0
