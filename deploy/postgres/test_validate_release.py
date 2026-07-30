#!/usr/bin/env python3
"""Focused tests for PostgreSQL release metadata validation."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("validate-release.py")
SPEC = importlib.util.spec_from_file_location("validate_release", MODULE_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)

AMD64 = "sha256:" + "a" * 64
ARM64 = "sha256:" + "b" * 64


def descriptor(architecture: str, digest: str, os_name: str = "linux") -> dict:
    return {
        "digest": digest,
        "platform": {"architecture": architecture, "os": os_name},
    }


class ManifestValidationTests(unittest.TestCase):
    def test_valid_manifest(self) -> None:
        VALIDATOR.validate_manifest(
            {"manifests": [descriptor("amd64", AMD64), descriptor("arm64", ARM64)]},
            AMD64,
            ARM64,
        )

    def assert_invalid(self, payload: object) -> None:
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_manifest(payload, AMD64, ARM64)

    def test_malformed_manifest(self) -> None:
        self.assert_invalid({"manifests": "not-an-array"})

    def test_missing_platform(self) -> None:
        self.assert_invalid({"manifests": [descriptor("amd64", AMD64)]})

    def test_extra_platform(self) -> None:
        self.assert_invalid(
            {
                "manifests": [
                    descriptor("amd64", AMD64),
                    descriptor("arm64", ARM64),
                    descriptor("s390x", "sha256:" + "c" * 64),
                ]
            }
        )

    def test_duplicate_platform(self) -> None:
        self.assert_invalid(
            {
                "manifests": [
                    descriptor("amd64", AMD64),
                    descriptor("amd64", AMD64),
                ]
            }
        )

    def test_digest_mismatch(self) -> None:
        self.assert_invalid(
            {
                "manifests": [
                    descriptor("amd64", "sha256:" + "d" * 64),
                    descriptor("arm64", ARM64),
                ]
            }
        )


class ImageValidationTests(unittest.TestCase):
    def valid_image(self) -> list[dict]:
        return [
            {
                "Os": "linux",
                "Architecture": "amd64",
                "Config": {"Labels": dict(VALIDATOR.EXPECTED_LABELS)},
            }
        ]

    def test_valid_image(self) -> None:
        VALIDATOR.validate_image_inspect(self.valid_image(), "amd64")

    def test_wrong_architecture(self) -> None:
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_image_inspect(self.valid_image(), "arm64")

    def test_missing_label(self) -> None:
        image = self.valid_image()
        del image[0]["Config"]["Labels"]["io.clouisle.pg-search.platform"]
        with self.assertRaises(VALIDATOR.ValidationError):
            VALIDATOR.validate_image_inspect(image, "amd64")


if __name__ == "__main__":
    unittest.main()
