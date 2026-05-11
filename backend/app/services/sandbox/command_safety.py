"""Shell command semantic safety checks."""

from __future__ import annotations

import fnmatch
import os
import shlex
from collections.abc import Collection

PROTECTED_PATHS = frozenset(
    {
        "/",
        "/workspace",
    }
)

DEFAULT_SAFE_SHELL_COMMANDS = frozenset(
    {
        "pwd",
        "ls",
        "find",
        "grep",
        "rg",
        "wc",
        "sort",
        "uniq",
        "cut",
        "tr",
        "date",
    }
)

SHELL_INTERPRETERS = frozenset({"bash", "sh"})
PYTHON_INTERPRETERS = frozenset({"python", "python3"})
NODE_INTERPRETERS = frozenset({"node", "nodejs", "javascript"})
PIP_COMMANDS = frozenset({"pip", "pip3"})
NPM_INSTALL_COMMANDS = frozenset({"install", "add", "i"})


class ShellCommandSafetyError(ValueError):
    """Raised when a shell command has unsafe semantics."""


class ShellCommandSafetyAnalyzer:
    """Analyze shell commands for unsafe semantics."""

    def __init__(self, workspace_root: str = "/workspace") -> None:
        self.workspace_root = workspace_root

    def validate(
        self, command: str, *, allowed_commands: Collection[str] | None = None
    ) -> None:
        words = self._split_command(command)
        if not words:
            return

        command_name = os.path.basename(words[0])
        if self._is_dangerous_command(command_name, words):
            raise ShellCommandSafetyError(f"Dangerous command blocked: {command_name}")
        pip_words = self._pip_invocation_words(command_name, words)
        if pip_words is not None:
            self._validate_pip_install(command_name, pip_words)
        elif command_name == "npm":
            self._validate_npm_install(words)
        elif self._is_disallowed_invocation(command_name, words):
            raise ShellCommandSafetyError(
                f"Unsafe command invocation blocked: {command_name}"
            )
        if allowed_commands is not None and not self._is_allowed_command(
            command_name, allowed_commands
        ):
            raise ShellCommandSafetyError(f"Command not in whitelist: {command_name}")
        self._validate_path_arguments(command_name, words)

    def _split_command(self, command: str) -> list[str]:
        if any(
            token in command for token in ("&&", "||", ";", "|", "<", ">", "`", "$")
        ):
            raise ShellCommandSafetyError("Unsupported shell syntax")
        try:
            return shlex.split(command, posix=True)
        except ValueError as e:
            raise ShellCommandSafetyError("Unsupported shell syntax") from e

    def _is_dangerous_command(self, command_name: str, words: list[str]) -> bool:
        if command_name in {"rm", "del", "rd", "rmdir", "unlink"}:
            return self._has_dangerous_delete_semantics(words)

        if command_name == "dd":
            return True

        if command_name in {":", "eval", "source", "."}:
            return True

        if command_name == "find" and any(
            word in {"-exec", "-execdir", "-delete"} for word in words[1:]
        ):
            return True

        return False

    def _pip_invocation_words(
        self, command_name: str, words: list[str]
    ) -> list[str] | None:
        if command_name in PIP_COMMANDS:
            return words

        if command_name in PYTHON_INTERPRETERS and words[1:3] == ["-m", "pip"]:
            return ["pip", *words[3:]]

        return None

    def _validate_pip_install(self, command_name: str, words: list[str]) -> None:
        if len(words) < 3 or words[1] != "install":
            raise ShellCommandSafetyError(
                f"Unsafe pip invocation blocked: {command_name}"
            )

        for index, word in enumerate(words[2:], start=2):
            if word in {"-e", "--editable"}:
                raise ShellCommandSafetyError("Unsafe pip install option blocked")
            if word.startswith(("git+", "hg+", "svn+", "bzr+")) or "://" in word:
                raise ShellCommandSafetyError("Unsafe pip install source blocked")
            if word in {"--target", "--prefix", "--root", "--src"}:
                target = words[index + 1] if index + 1 < len(words) else ""
                if not target or self._path_escapes_workspace(target):
                    raise ShellCommandSafetyError(
                        f"Path escapes workspace: {target or word}"
                    )
            if word.startswith(("--target=", "--prefix=", "--root=", "--src=")):
                target = word.split("=", 1)[1]
                if not target or self._path_escapes_workspace(target):
                    raise ShellCommandSafetyError(
                        f"Path escapes workspace: {target or word}"
                    )

    def _validate_npm_install(self, words: list[str]) -> None:
        if len(words) < 3 or words[1] not in NPM_INSTALL_COMMANDS:
            raise ShellCommandSafetyError("Unsafe npm invocation blocked: npm")

        for index, word in enumerate(words[2:], start=2):
            if word in {"-g", "--global"}:
                raise ShellCommandSafetyError("Unsafe npm install option blocked")
            if (
                word.startswith(("git+", "github:", "gitlab:", "bitbucket:"))
                or "://" in word
            ):
                raise ShellCommandSafetyError("Unsafe npm install source blocked")
            if word in {"--prefix", "--cache"}:
                target = words[index + 1] if index + 1 < len(words) else ""
                if not target or self._path_escapes_workspace(target):
                    raise ShellCommandSafetyError(
                        f"Path escapes workspace: {target or word}"
                    )
            if word.startswith(("--prefix=", "--cache=")):
                target = word.split("=", 1)[1]
                if not target or self._path_escapes_workspace(target):
                    raise ShellCommandSafetyError(
                        f"Path escapes workspace: {target or word}"
                    )

    def _is_disallowed_invocation(self, command_name: str, words: list[str]) -> bool:
        if command_name in SHELL_INTERPRETERS:
            return True

        if command_name in PYTHON_INTERPRETERS:
            return any(word in {"-c", "-m", "-"} for word in words[1:])

        if command_name in NODE_INTERPRETERS:
            return any(word in {"-e", "--eval", "-p", "--print"} for word in words[1:])

        if command_name == "npm":
            return any(word in {"exec", "x", "run", "start"} for word in words[1:])

        if command_name == "npx":
            return True

        return False

    def _is_allowed_command(
        self, command_name: str, allowed_commands: Collection[str]
    ) -> bool:
        return any(
            fnmatch.fnmatch(command_name, pattern) for pattern in allowed_commands
        )

    def _validate_path_arguments(self, command_name: str, words: list[str]) -> None:
        if command_name in {"pwd", "date", "sort", "uniq", "cut", "tr", "wc", "which"}:
            return

        if command_name == "cd" and len(words) == 1:
            return

        for word in words[1:]:
            if not word or word.startswith("-") or "=" in word:
                continue
            if any(marker in word for marker in {"*", "?", "[", "]", "{", "}", "$"}):
                continue
            if "://" in word:
                continue
            if word.startswith("|") or word in {"&&", "||", ";"}:
                continue
            if self._path_escapes_workspace(word):
                raise ShellCommandSafetyError(f"Path escapes workspace: {word}")

    def _has_dangerous_delete_semantics(self, words: list[str]) -> bool:
        flags = {"-r", "-rf", "-fr", "-f", "--no-preserve-root", "-R", "-force"}
        has_dangerous_flag = any(word in flags for word in words[1:])
        if not has_dangerous_flag:
            return False

        for word in words[1:]:
            if word == "-exec":
                return True
            if word.startswith("-"):
                continue
            if self._is_protected_path(word):
                return True
        return False

    def _path_escapes_workspace(self, path: str) -> bool:
        if not os.path.isabs(path):
            path = os.path.join(self.workspace_root, path)
        normalized = os.path.normpath(path)
        workspace_root = os.path.normpath(self.workspace_root)
        return normalized != workspace_root and not normalized.startswith(
            f"{workspace_root}/"
        )

    def _is_protected_path(self, path: str) -> bool:
        if not os.path.isabs(path):
            path = os.path.join(self.workspace_root, path)
        normalized = os.path.normpath(path)
        return normalized in PROTECTED_PATHS or normalized.startswith("/..")


def validate_shell_command(
    command: str,
    workspace_root: str = "/workspace",
    *,
    allowed_commands: Collection[str] | None = None,
) -> None:
    ShellCommandSafetyAnalyzer(workspace_root=workspace_root).validate(
        command,
        allowed_commands=allowed_commands,
    )
