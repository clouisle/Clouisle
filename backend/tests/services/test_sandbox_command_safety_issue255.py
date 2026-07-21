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
        ("/usr/bin/ls /workspace/data", {"l*"}),
        ("cd", None),
        ("grep '*.py' /workspace", None),
        ("python script.py", None),
        ("node script.js", None),
        ("pip install requests==2.32.0 --target /workspace/vendor", None),
        ("python3 -m pip install pytest==8.4.1 --prefix=/workspace/vendor", None),
        ("npm add lodash@4.17.21 --cache /workspace/cache", None),
        ("npm i react@19 --prefix=/workspace/vendor", None),
        ("rm file.txt", None),
        ("rm -rf /workspace/tmp", None),
        ("ls https://example.test/file", None),
    ],
)
def test_safe_commands_are_accepted(command, allowed_commands):
    validate_shell_command(command, allowed_commands=allowed_commands)


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("echo ok && pwd", "Unsupported shell syntax"),
        ("echo 'unterminated", "Unsupported shell syntax"),
        ("rm -rf /", "Dangerous command blocked: rm"),
        ("rmdir -r /workspace", "Dangerous command blocked: rmdir"),
        ("dd if=/dev/zero", "Dangerous command blocked: dd"),
        ("eval harmless", "Dangerous command blocked: eval"),
        ("find . -delete", "Dangerous command blocked: find"),
        ("bash script.sh", "Unsafe command invocation blocked: bash"),
        ("python -c pass", "Unsafe command invocation blocked: python"),
        ("node --eval pass", "Unsafe command invocation blocked: node"),
        ("npm run build", "Unsafe npm invocation blocked: npm"),
        ("npm start", "Unsafe npm invocation blocked: npm"),
        ("npx prettier", "Unsafe command invocation blocked: npx"),
        ("echo hello", "Command not in whitelist: echo"),
        ("ls /etc", "Path escapes workspace: /etc"),
        ("pip list", "Unsafe pip invocation blocked: pip"),
        ("pip install -e package", "Unsafe pip install option blocked"),
        (
            "pip install https://example.test/pkg.whl",
            "Unsafe pip install source blocked",
        ),
        ("pip install package --root /", "Path escapes workspace: /"),
        ("pip install package --src=", "Path escapes workspace: --src="),
        ("npm list package", "Unsafe npm invocation blocked: npm"),
        ("npm install -g package", "Unsafe npm install option blocked"),
        ("npm install github:owner/repo", "Unsafe npm install source blocked"),
        ("npm install package --cache /tmp", "Path escapes workspace: /tmp"),
        ("npm install package --prefix=", "Path escapes workspace: --prefix="),
    ],
)
def test_unsafe_commands_are_rejected(command, message):
    allowed_commands = {"ls"} if command == "echo hello" else None
    with pytest.raises(ShellCommandSafetyError, match=message):
        validate_shell_command(command, allowed_commands=allowed_commands)
