from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = PROJECT_ROOT / "deploy" / "install.sh"
REQUIRED_SECRET_KEYS = (
    "SECRET_KEY",
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "QDRANT_API_KEY",
    "SANDBOX_ARTIFACT_UPLOAD_API_KEY",
    "INTERNAL_API_TOKEN",
)
BACKEND_WORKLOADS = ("api", "worker", "sandbox-worker", "beat")


def _run_manifest_generator(output_path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "CLOUISLE_DEPLOYMENT": "k8s",
        "CLOUISLE_K8S_MANIFEST": str(output_path),
        "CLOUISLE_SOURCE_DIR": str(PROJECT_ROOT),
        "CLOUISLE_YES": "1",
    }
    return subprocess.run(
        ["bash", str(INSTALL_SCRIPT)],
        cwd=output_path.parent.parent,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _generated_documents(output_path: Path) -> list[dict]:
    return list(yaml.safe_load_all(output_path.read_text(encoding="utf-8")))


def test_k8s_installer_generates_a_secret_manifest_and_preserves_output(tmp_path: Path):
    output_path = tmp_path / "generated" / "clouisle-k8s.yaml"

    result = _run_manifest_generator(output_path)

    assert result.returncode == 0, result.stderr
    assert output_path.stat().st_mode & 0o777 == 0o600
    assert f"kubectl apply -f {output_path}" in result.stdout

    documents = _generated_documents(output_path)
    secret = next(document for document in documents if document["kind"] == "Secret")
    decoded = {
        key: base64.b64decode(secret["data"][key]).decode("ascii")
        for key in REQUIRED_SECRET_KEYS
    }
    assert set(decoded) == set(REQUIRED_SECRET_KEYS)
    assert len(set(decoded.values())) == len(REQUIRED_SECRET_KEYS)
    assert all(len(value) == 64 for value in decoded.values())

    template_documents = _generated_documents(
        PROJECT_ROOT / "deploy" / "k8s" / "clouisle.yaml"
    )
    template_secret = next(
        document for document in template_documents if document["kind"] == "Secret"
    )
    assert (
        template_secret["data"]["SECRET_KEY"]
        == "Y2hhbmdldGhpcy10by1hLXNlY3VyZS1yYW5kb20tc2VjcmV0LWtleQ=="
    )
    assert template_secret["data"]["INTERNAL_API_TOKEN"] == ""
    assert template_secret["data"]["SANDBOX_ARTIFACT_UPLOAD_API_KEY"] == ""

    deployments = {
        document["metadata"]["name"]: document
        for document in documents
        if document["kind"] == "Deployment"
    }
    for name in BACKEND_WORKLOADS:
        pod_spec = deployments[name]["spec"]["template"]["spec"]
        wait_container = next(
            container
            for container in pod_spec["initContainers"]
            if container["name"] == "wait-for-postgres"
        )
        assert wait_container["image"].startswith(
            "registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:"
        )
        assert "pg_isready" in wait_container["command"][-1]
        assert {item["name"] for item in wait_container["env"]} == {
            "POSTGRES_SERVER",
            "POSTGRES_PORT",
            "POSTGRES_USER",
            "POSTGRES_DB",
        }

    existing = _run_manifest_generator(output_path)
    assert existing.returncode != 0
    assert "Refusing to overwrite existing Kubernetes manifest" in existing.stderr
