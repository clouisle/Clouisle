import pytest

from app.services.sandbox.command_safety import (
    ShellCommandSafetyError,
    validate_shell_command,
)


@pytest.mark.parametrize(
    "command",
    [
        "",
        "pwd",
        "ls .",
        "find src -name '*.py'",
        "rm -f output.txt",
        "python script.py",
        "pip install requests==2.32.3",
        "python3 -m pip install --target vendor requests==2.32.3",
        "npm add lodash",
        "npm install --cache .npm-cache lodash",
    ],
)
def test_safe_commands_are_allowed(command: str) -> None:
    validate_shell_command(command)


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("ls && rm -rf /", "Unsupported shell syntax"),
        ("ls 'unterminated", "Unsupported shell syntax"),
        ("rm -rf /", "Dangerous command blocked: rm"),
        ("rm -rf .", "Dangerous command blocked: rm"),
        ("find . -delete", "Dangerous command blocked: find"),
        ("bash script.sh", "Unsafe command invocation blocked: bash"),
        ("python -c 'print(1)'", "Unsafe command invocation blocked: python"),
        ("node --eval '1 + 1'", "Unsafe command invocation blocked: node"),
        ("npm run build", "Unsafe npm invocation blocked: npm"),
        ("npx prettier .", "Unsafe command invocation blocked: npx"),
        ("pip list", "Unsafe pip invocation blocked: pip"),
        ("pip install -e .", "Unsafe pip install option blocked"),
        (
            "pip install https://example.com/pkg.whl",
            "Unsafe pip install source blocked",
        ),
        ("pip install --target /tmp/vendor pkg", "Path escapes workspace: /tmp/vendor"),
        ("npm install --global lodash", "Unsafe npm install option blocked"),
        ("npm install github:owner/repo", "Unsafe npm install source blocked"),
        ("npm install --cache=/tmp/npm lodash", "Path escapes workspace: /tmp/npm"),
        ("ls /etc", "Path escapes workspace: /etc"),
    ],
)
def test_unsafe_commands_are_denied(command: str, message: str) -> None:
    with pytest.raises(ShellCommandSafetyError, match=message):
        validate_shell_command(command)


def test_whitelist_supports_patterns_without_bypassing_safety_checks() -> None:
    validate_shell_command("/usr/bin/python3 script.py", allowed_commands={"python*"})

    with pytest.raises(ShellCommandSafetyError, match="Command not in whitelist: ls"):
        validate_shell_command("ls .", allowed_commands={"python*"})

    with pytest.raises(ShellCommandSafetyError, match="Dangerous command blocked: rm"):
        validate_shell_command("rm -rf /", allowed_commands={"*"})


def test_custom_workspace_root_confines_path_arguments() -> None:
    validate_shell_command("ls /tmp/job/output", workspace_root="/tmp/job")

    with pytest.raises(
        ShellCommandSafetyError, match="Path escapes workspace: /tmp/other"
    ):
        validate_shell_command("ls /tmp/other", workspace_root="/tmp/job")
