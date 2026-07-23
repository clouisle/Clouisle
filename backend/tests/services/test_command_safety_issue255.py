import pytest

from app.services.sandbox.command_safety import (
    ShellCommandSafetyError,
    validate_shell_command,
)


@pytest.mark.parametrize(
    "command",
    [
        "",
        "ls src",
        "rm -f temporary.txt",
        "pip install pytest",
        "python3 -m pip install pytest --target vendor",
        "npm add lodash --cache .cache",
        "cd",
        "grep pattern https://example.com",
        "find *.py",
    ],
)
def test_safe_commands_are_accepted(command):
    validate_shell_command(command)


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("ls && pwd", "Unsupported shell syntax"),
        ("ls 'unterminated", "Unsupported shell syntax"),
        ("rm -rf /", "Dangerous command blocked: rm"),
        ("rmdir -R /workspace", "Dangerous command blocked: rmdir"),
        ("dd if=input of=output", "Dangerous command blocked: dd"),
        ("find . -delete", "Dangerous command blocked: find"),
        ("bash script.sh", "Unsafe command invocation blocked: bash"),
        ("python -c print(1)", "Unsafe command invocation blocked: python"),
        ("node --print 1", "Unsafe command invocation blocked: node"),
        ("npx eslint", "Unsafe command invocation blocked: npx"),
        ("pip list", "Unsafe pip invocation blocked: pip"),
        ("pip install -e package", "Unsafe pip install option blocked"),
        (
            "pip install git+https://example.com/pkg",
            "Unsafe pip install source blocked",
        ),
        ("pip install pkg --target /tmp", "Path escapes workspace: /tmp"),
        ("pip install pkg --root=", "Path escapes workspace: --root="),
        ("npm run build", "Unsafe npm invocation blocked: npm"),
        ("npm install -g pkg", "Unsafe npm install option blocked"),
        ("npm install github:user/repo", "Unsafe npm install source blocked"),
        ("npm install pkg --prefix /tmp", "Path escapes workspace: /tmp"),
        ("ls /etc", "Path escapes workspace: /etc"),
    ],
)
def test_unsafe_commands_are_rejected(command, message):
    with pytest.raises(ShellCommandSafetyError, match=message):
        validate_shell_command(command)


def test_whitelist_supports_patterns_and_rejects_other_commands():
    validate_shell_command("python3 script.py", allowed_commands={"python*"})

    with pytest.raises(ShellCommandSafetyError, match="Command not in whitelist: ls"):
        validate_shell_command("ls", allowed_commands={"python*"})


def test_custom_workspace_controls_path_boundaries():
    validate_shell_command("ls /sandbox/files", workspace_root="/sandbox")

    with pytest.raises(ShellCommandSafetyError, match="Path escapes workspace"):
        validate_shell_command("ls ../outside", workspace_root="/sandbox")
