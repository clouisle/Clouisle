#!/usr/bin/env python3
"""Validate PostgreSQL release images and two-platform OCI indexes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

EXPECTED_LABELS = {
    "org.opencontainers.image.source": "https://github.com/paradedb/paradedb",
    "org.opencontainers.image.version": "0.24.3",
    "io.clouisle.pg-search.revision": "5fa2690053c905d06e8b55d43f3df7aa40ee43a2",
    "io.clouisle.pg-search.platform": "alpine-musl",
}
EXPECTED_ARCHITECTURES = ("amd64", "arm64")


class ValidationError(ValueError):
    pass


def load_json(path: str) -> Any:
    try:
        if path == "-":
            return json.load(sys.stdin)
        with Path(path).open(encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON input: {exc}") from exc


def validate_image_inspect(payload: Any, expected_architecture: str) -> None:
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValidationError("docker image inspect must contain exactly one image")

    image = payload[0]
    if image.get("Os") != "linux" or image.get("Architecture") != expected_architecture:
        raise ValidationError(
            f"image platform must be linux/{expected_architecture}, got "
            f"{image.get('Os')}/{image.get('Architecture')}"
        )

    config = image.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict):
        raise ValidationError("image labels are missing")
    for name, expected in EXPECTED_LABELS.items():
        actual = labels.get(name)
        if actual != expected:
            raise ValidationError(f"label {name} must be {expected!r}, got {actual!r}")


def validate_manifest(
    payload: Any, amd64_digest: str, arm64_digest: str
) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("manifests"), list):
        raise ValidationError("OCI index must contain a manifests array")

    expected = {"amd64": amd64_digest, "arm64": arm64_digest}
    observed: dict[str, str] = {}
    for descriptor in payload["manifests"]:
        if not isinstance(descriptor, dict):
            raise ValidationError("manifest descriptor must be an object")
        platform = descriptor.get("platform")
        if not isinstance(platform, dict):
            raise ValidationError("manifest descriptor platform is missing")
        os_name = platform.get("os")
        architecture = platform.get("architecture")
        if os_name != "linux" or architecture not in expected:
            raise ValidationError(f"unexpected manifest platform {os_name}/{architecture}")
        if architecture in observed:
            raise ValidationError(f"duplicate manifest platform linux/{architecture}")
        digest = descriptor.get("digest")
        if (
            not isinstance(digest, str)
            or len(digest) != 71
            or not digest.startswith("sha256:")
        ):
            raise ValidationError(f"invalid digest for linux/{architecture}")
        try:
            int(digest.removeprefix("sha256:"), 16)
        except ValueError as exc:
            raise ValidationError(
                f"invalid digest for linux/{architecture}"
            ) from exc
        observed[architecture] = digest

    missing = set(EXPECTED_ARCHITECTURES) - observed.keys()
    if missing:
        raise ValidationError(f"missing manifest platforms: {', '.join(sorted(missing))}")
    if len(payload["manifests"]) != len(EXPECTED_ARCHITECTURES):
        raise ValidationError("manifest must contain exactly two descriptors")
    for architecture, expected_digest in expected.items():
        if observed[architecture] != expected_digest:
            raise ValidationError(
                f"linux/{architecture} digest must be {expected_digest}, "
                f"got {observed[architecture]}"
            )


def inspect_image(image: str) -> Any:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not inspect image {image}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    image_parser = subparsers.add_parser("image")
    image_parser.add_argument("image")
    image_parser.add_argument("architecture", choices=EXPECTED_ARCHITECTURES)

    manifest_parser = subparsers.add_parser("manifest")
    manifest_parser.add_argument("json_path")
    manifest_parser.add_argument("amd64_digest")
    manifest_parser.add_argument("arm64_digest")

    args = parser.parse_args()
    try:
        if args.command == "image":
            validate_image_inspect(inspect_image(args.image), args.architecture)
        else:
            validate_manifest(
                load_json(args.json_path), args.amd64_digest, args.arm64_digest
            )
    except ValidationError as exc:
        print(f"release validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
