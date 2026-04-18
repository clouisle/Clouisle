"""Python sandbox environment cache."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .cache import acquire_cache_lock, build_cache_key, normalize_package_source_url


class PythonEnvironmentManager:
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root / "python-envs"
        self.cache_root.mkdir(parents=True, exist_ok=True)

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
            sys.version.split()[0],
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
                    [sys.executable, "-m", "venv", str(env_dir)],
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

    def build_env_vars(self, env_dir: Path) -> dict[str, str]:
        return {
            "VIRTUAL_ENV": str(env_dir),
            "PYTHONNOUSERSITE": "1",
            "PATH": f"{env_dir / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
        }
