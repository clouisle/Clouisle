"""Python sandbox environment cache."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.core.config import settings

from .cache import acquire_cache_lock, build_cache_key, normalize_package_source_url


class PythonEnvironmentManager:
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root / "python-envs"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._python_version_cache: str | None = None

    def build_env_key(
        self,
        python_version: str,
        packages: list[str],
        runtime_profile: str,
        package_index_url: str | None = None,
    ) -> str:
        normalized_package_index_url = normalize_package_source_url(package_index_url)
        return build_cache_key(
            "python",
            python_version,
            packages,
            runtime_profile,
            normalized_package_index_url,
        )

    def ensure_environment(
        self,
        *,
        packages: list[str],
        runtime_profile: str,
        package_index_url: str | None = None,
    ) -> tuple[Path | None, bool]:
        if not packages:
            return None, False

        normalized_package_index_url = normalize_package_source_url(package_index_url)
        env_key = self.build_env_key(
            self.python_version(),
            packages,
            runtime_profile,
            normalized_package_index_url,
        )
        env_root = self.cache_root / env_key
        env_dir = env_root / "venv"
        ready_flag = env_root / "READY"
        if ready_flag.exists() and env_dir.exists():
            return env_dir, True

        with acquire_cache_lock("python-env", env_key):
            if ready_flag.exists() and env_dir.exists():
                return env_dir, True

            if env_root.exists():
                shutil.rmtree(env_root, ignore_errors=True)
            env_root.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    [self.python_binary(), "-m", "venv", str(env_dir)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                pip_cmd = [str(env_dir / "bin" / "pip"), "install"]
                if normalized_package_index_url:
                    pip_cmd.extend(["--index-url", normalized_package_index_url])
                pip_cmd.extend(packages)
                subprocess.run(pip_cmd, check=True)
                ready_flag.write_text("ready", encoding="utf-8")
                return env_dir, False
            except Exception:
                shutil.rmtree(env_root, ignore_errors=True)
                raise

    def ensure_workspace_environment(self, workspace_root: Path) -> Path:
        env_dir = workspace_root / ".venv"
        python_binary = env_dir / "bin" / "python"
        pip_binary = env_dir / "bin" / "pip"
        if python_binary.exists() and pip_binary.exists():
            return env_dir

        if env_dir.exists() and not python_binary.exists():
            shutil.rmtree(env_dir, ignore_errors=True)

        if not python_binary.exists():
            subprocess.run(
                [self.python_binary(), "-m", "venv", str(env_dir)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        if not pip_binary.exists():
            subprocess.run(
                [str(python_binary), "-m", "ensurepip", "--upgrade"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return env_dir

    def build_env_vars(self, env_dir: Path) -> dict[str, str]:
        return {
            "VIRTUAL_ENV": str(env_dir),
            "PYTHONNOUSERSITE": "1",
            "PATH": f"{env_dir / 'bin'}{os.pathsep}{self.runtime_path()}",
        }

    def build_workspace_env_vars(
        self, workspace_root: Path, tmp_dir: Path
    ) -> dict[str, str]:
        env_dir = self.ensure_workspace_environment(workspace_root)
        pip_cache_dir = tmp_dir / "pip-cache"
        pip_cache_dir.mkdir(parents=True, exist_ok=True)
        env = self.build_env_vars(env_dir)
        env["PIP_CACHE_DIR"] = str(pip_cache_dir)
        return env

    def python_binary(self) -> str:
        for candidate in settings.SANDBOX_DEFAULT_PYTHON_BINARIES:
            if Path(candidate).exists():
                return candidate
        return "python3"

    def python_version(self) -> str:
        if self._python_version_cache is None:
            self._python_version_cache = (
                subprocess.check_output(
                    [self.python_binary(), "--version"],
                    text=True,
                )
                .strip()
                .split()[-1]
            )
        return self._python_version_cache

    def runtime_path(self) -> str:
        python_dir = str(Path(self.python_binary()).parent)
        current_path = os.environ.get("PATH", "")
        parts = [
            part
            for part in current_path.split(os.pathsep)
            if part
            and "/backend/.venv/" not in part
            and not part.endswith("/backend/.venv/bin")
        ]
        filtered = os.pathsep.join(parts)
        return f"{python_dir}{os.pathsep}{filtered}" if filtered else python_dir
