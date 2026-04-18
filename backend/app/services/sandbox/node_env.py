"""Node sandbox environment cache."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .cache import acquire_cache_lock, build_cache_key, normalize_package_source_url


class NodeEnvironmentManager:
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root / "node-envs"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._node_version_cache: str | None = None
        self._node_exec_path_cache: str | None = None

    def build_env_key(
        self,
        node_version: str,
        packages: list[str],
        runtime_profile: str,
        registry_url: str | None = None,
    ) -> str:
        normalized_registry_url = normalize_package_source_url(registry_url)
        return build_cache_key(
            "node",
            node_version,
            packages,
            runtime_profile,
            normalized_registry_url,
        )

    def ensure_environment(
        self,
        *,
        packages: list[str],
        runtime_profile: str,
        registry_url: str | None = None,
    ) -> tuple[Path | None, bool]:
        if not packages:
            return None, False

        normalized_registry_url = normalize_package_source_url(registry_url)
        node_version = self._node_version()
        env_key = self.build_env_key(
            node_version,
            packages,
            runtime_profile,
            normalized_registry_url,
        )
        env_root = self.cache_root / env_key
        ready_flag = env_root / "READY"
        node_modules_bin = env_root / "node_modules" / ".bin"
        if ready_flag.exists() and node_modules_bin.exists():
            return env_root, True

        with acquire_cache_lock("node-env", env_key):
            if ready_flag.exists() and node_modules_bin.exists():
                return env_root, True

            building_root = self.cache_root / f".building-{env_key}"
            if building_root.exists():
                shutil.rmtree(building_root, ignore_errors=True)
            building_root.mkdir(parents=True, exist_ok=True)
            package_json = {
                "name": "clouisle-sandbox-job",
                "private": True,
                "dependencies": {
                    package.rsplit("@", 1)[0] if "@" in package[1:] else package: package.rsplit("@", 1)[1] if "@" in package[1:] else "latest"
                    for package in packages
                },
            }
            (building_root / "package.json").write_text(
                json.dumps(package_json),
                encoding="utf-8",
            )
            try:
                npm_cmd = ["npm", "install", "--ignore-scripts"]
                if normalized_registry_url:
                    npm_cmd.extend(["--registry", normalized_registry_url])
                subprocess.run(npm_cmd, cwd=building_root, check=True)

                if env_root.exists():
                    shutil.rmtree(env_root, ignore_errors=True)
                building_root.rename(env_root)
                ready_flag.write_text("ready", encoding="utf-8")
                return env_root, False
            except Exception:
                shutil.rmtree(building_root, ignore_errors=True)
                raise

    def node_binary(self) -> str:
        return self._node_exec_path()

    def build_env_vars(self, env_root: Path) -> dict[str, str]:
        node_modules = env_root / "node_modules"
        node_binary = self.node_binary()
        node_bin_dir = str(Path(node_binary).parent)
        return {
            "NODE_PATH": str(node_modules),
            "SANDBOX_NODE_BINARY": node_binary,
            "PATH": f"{node_modules / '.bin'}{os.pathsep}{node_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        }

    def _node_version(self) -> str:
        if self._node_version_cache is None:
            self._node_version_cache = subprocess.check_output(
                ["node", "--version"], text=True
            ).strip()
        return self._node_version_cache

    def _node_exec_path(self) -> str:
        if self._node_exec_path_cache is None:
            self._node_exec_path_cache = subprocess.check_output(
                ["node", "-p", "process.execPath"], text=True
            ).strip()
        return self._node_exec_path_cache
