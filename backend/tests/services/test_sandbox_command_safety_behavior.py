import pytest

from app.services.sandbox.command_safety import (
    ShellCommandSafetyError,
    validate_shell_command,
)


def test_allows_safe_workspace_commands_and_pinned_packages():
    validate_shell_command("ls reports", allowed_commands={"ls"})
    validate_shell_command("python -m pip install pydantic==2.12.0")
    validate_shell_command("npm install zod@4.0.0")


@pytest.mark.parametrize(
    "command",
    [
        "ls && pwd",
        "find . -delete",
        "bash script.sh",
        "python -c 'print(1)'",
        "node --eval 'process.exit()'",
        "npx prettier .",
        "pip install git+https://example.test/package.git",
        "npm install --global package",
        "rm -rf /workspace",
    ],
)
def test_blocks_unsafe_shell_semantics(command):
    with pytest.raises(ShellCommandSafetyError):
        validate_shell_command(command)


def test_enforces_command_whitelist_and_workspace_boundaries():
    with pytest.raises(ShellCommandSafetyError, match="not in whitelist"):
        validate_shell_command("grep value report.txt", allowed_commands={"ls"})

    with pytest.raises(ShellCommandSafetyError, match="Path escapes workspace"):
        validate_shell_command("ls /etc")

    validate_shell_command("ls /workspace/reports")
