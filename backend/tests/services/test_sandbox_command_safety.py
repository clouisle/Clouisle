import pytest

from app.services.sandbox.command_safety import (
    ShellCommandSafetyError,
    validate_shell_command,
)


@pytest.mark.parametrize(
    ("command", "allowed_commands"),
    [
        ("", None),
        ("pwd", {"pwd"}),
        ("/usr/bin/ls reports/*.json", {"l*"}),
        ("rm -rf reports/tmp", None),
        ("python script.py", None),
        ("node app.js", None),
        ("python -m pip install pydantic==2.12.0 --target build", None),
        ("npm add zod@4.0.0 --cache=.cache", None),
    ],
)
def test_allows_commands_confined_to_safe_behavior(command, allowed_commands):
    validate_shell_command(command, allowed_commands=allowed_commands)


def test_honors_custom_workspace_boundary():
    validate_shell_command("ls /job/output", workspace_root="/job")

    with pytest.raises(ShellCommandSafetyError, match="Path escapes workspace"):
        validate_shell_command("ls /workspace/output", workspace_root="/job")


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("ls && pwd", "Unsupported shell syntax"),
        ("'unterminated", "Unsupported shell syntax"),
        ("dd if=input of=output", "Dangerous command blocked: dd"),
        ("eval harmless", "Dangerous command blocked: eval"),
        ("find . -delete", "Dangerous command blocked: find"),
        ("rm -rf /workspace", "Dangerous command blocked: rm"),
        ("bash script.sh", "Unsafe command invocation blocked: bash"),
        ("python -m http.server", "Unsafe command invocation blocked: python"),
        ("node --print 1", "Unsafe command invocation blocked: node"),
        ("npx prettier .", "Unsafe command invocation blocked: npx"),
        ("pip list", "Unsafe pip invocation blocked: pip"),
        ("python -m pip install --editable .", "Unsafe pip install option blocked"),
        (
            "pip install https://example.test/pkg.whl",
            "Unsafe pip install source blocked",
        ),
        ("pip install pkg --target /tmp", "Path escapes workspace: /tmp"),
        ("pip install pkg --root", "Path escapes workspace: --root"),
        ("npm run build", "Unsafe npm invocation blocked: npm"),
        ("npm install --global pkg", "Unsafe npm install option blocked"),
        ("npm add github:user/repo", "Unsafe npm install source blocked"),
        ("npm i pkg --prefix=/tmp", "Path escapes workspace: /tmp"),
        ("ls ../outside", "Path escapes workspace: ../outside"),
    ],
)
def test_rejects_commands_that_cross_execution_boundaries(command, message):
    with pytest.raises(ShellCommandSafetyError, match=message):
        validate_shell_command(command)


def test_rejects_commands_outside_the_whitelist():
    with pytest.raises(ShellCommandSafetyError, match="Command not in whitelist: grep"):
        validate_shell_command("grep value report.txt", allowed_commands={"ls", "find"})
