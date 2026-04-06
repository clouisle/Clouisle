from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "license-policy.yml"


@dataclass
class ExceptionRule:
    ecosystem: str | None = None
    package: str | None = None
    version: str | None = None
    license: str | None = None
    justification: str | None = None
    owner: str | None = None
    expires_on: date | None = None


@dataclass
class Policy:
    action_on_unknown: str
    fail_on_missing_license: bool
    allowed_licenses: set[str]
    conditionally_allowed_licenses: set[str]
    denied_licenses: set[str]
    exceptions: list[ExceptionRule]


def strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    result: list[str] = []

    for char in line:
        if char == '"' and not in_single:
            in_double = not in_double
        elif char == "'" and not in_double:
            in_single = not in_single
        elif char == "#" and not in_single and not in_double:
            break
        result.append(char)

    return "".join(result).rstrip()


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value.startswith(('"', "'")) and value.endswith(('"', "'")):
        return value[1:-1]
    if value in {"true", "false"}:
        return value == "true"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value)
    return value


def parse_policy_file(text: str) -> dict[str, Any]:
    lines = [strip_comment(line) for line in text.splitlines()]
    lines = [line for line in lines if line.strip()]

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(-1, root)]

    for index, raw_line in enumerate(lines):
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()

        parent = stack[-1][1]

        if line.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"Invalid list item placement: {raw_line}")
            item_text = line[2:].strip()
            if ":" in item_text:
                key, value = item_text.split(":", 1)
                item: dict[str, Any] = {key.strip(): parse_scalar(value)}
                parent.append(item)
                stack.append((indent, item))
            else:
                parent.append(parse_scalar(item_text))
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if isinstance(parent, list):
            raise ValueError(f"Unexpected mapping under list: {raw_line}")

        if not value:
            next_non_empty = None
            for next_line in lines[index + 1 :]:
                next_indent = len(next_line) - len(next_line.lstrip(" "))
                if next_indent <= indent:
                    break
                next_non_empty = next_line.strip()
                break
            container: dict[str, Any] | list[Any] = (
                [] if next_non_empty and next_non_empty.startswith("- ") else {}
            )
            parent[key] = container
            stack.append((indent, container))
            continue

        parent[key] = parse_scalar(value)

    return root


def load_policy() -> Policy:
    data = parse_policy_file(POLICY_PATH.read_text(encoding="utf-8"))
    defaults = data.get("defaults", {})

    exceptions = []
    for item in data.get("exceptions", []):
        exceptions.append(
            ExceptionRule(
                ecosystem=item.get("ecosystem"),
                package=item.get("package"),
                version=item.get("version"),
                license=item.get("license"),
                justification=item.get("justification"),
                owner=item.get("owner"),
                expires_on=item.get("expires_on"),
            )
        )

    return Policy(
        action_on_unknown=defaults.get("action_on_unknown", "deny"),
        fail_on_missing_license=bool(defaults.get("fail_on_missing_license", True)),
        allowed_licenses=set(data.get("allowed_licenses", [])),
        conditionally_allowed_licenses=set(
            data.get("conditionally_allowed_licenses", [])
        ),
        denied_licenses=set(data.get("denied_licenses", [])),
        exceptions=exceptions,
    )


def normalize_token(token: str) -> str:
    token = token.strip()
    token = re.sub(r"^\((.*)\)$", r"\1", token)
    token = re.sub(r"\s+", " ", token)
    token = token.split("\n", 1)[0].strip()
    if (
        " AND " not in token
        and " OR " not in token
        and ";" not in token
        and "," not in token
    ):
        token = re.sub(r"\s*\([^)]*\)$", "", token).strip()
    mapping = {
        "Apache 2.0": "Apache-2.0",
        "Apache*": "Apache-2.0",
        "Apache Software License": "Apache-2.0",
        "Apache License 2.0": "Apache-2.0",
        "MIT License": "MIT",
        "MIT*": "MIT",
        "BSD License": "BSD-3-Clause",
        "BSD": "BSD-3-Clause",
        "3-Clause BSD License": "BSD-3-Clause",
        "BSD-3-Clause License": "BSD-3-Clause",
        "BSD-2-Clause License": "BSD-2-Clause",
        "The Unlicense": "Unlicense",
        "ISC License": "ISC",
        "Python Software Foundation License": "PSF-2.0",
        "Mozilla Public License 2.0": "MPL-2.0",
        "PSF": "PSF-2.0",
        "ZLIB": "Zlib",
        "UNLICENSED": "UNLICENSED",
    }
    return mapping.get(token, token)


def split_expression(license_value: str) -> tuple[str, list[str]]:
    cleaned = re.sub(r"\s+", " ", license_value.strip())
    if not cleaned:
        return "single", []

    inner = cleaned.strip("()").replace(";", " OR ").replace(",", " OR ")
    if " OR " in inner:
        return "or", [
            normalize_token(part) for part in inner.split(" OR ") if part.strip()
        ]
    if " AND " in inner:
        return "and", [
            normalize_token(part) for part in inner.split(" AND ") if part.strip()
        ]
    if "/" in inner and "http" not in inner:
        return "or", [
            normalize_token(part) for part in inner.split("/") if part.strip()
        ]
    return "single", [normalize_token(inner)]


def is_exception_match(
    rule: ExceptionRule, package: str, version: str, license_value: str
) -> bool:
    if rule.ecosystem and rule.ecosystem != "python":
        return False
    if rule.package and rule.package != package:
        return False
    if rule.version and rule.version != version:
        return False
    if rule.license and rule.license != normalize_token(license_value):
        return False
    if rule.expires_on and rule.expires_on < date.today():
        return False
    return True


def find_exception(
    policy: Policy, package: str, version: str, license_value: str
) -> ExceptionRule | None:
    normalized = normalize_token(license_value)
    for rule in policy.exceptions:
        if is_exception_match(rule, package, version, normalized):
            return rule
    return None


def evaluate_license(policy: Policy, license_value: str) -> tuple[bool, str]:
    normalized = normalize_token(license_value)
    if not normalized or normalized.upper() == "UNKNOWN":
        if policy.fail_on_missing_license or policy.action_on_unknown == "deny":
            return False, "unknown license"
        return True, "unknown license allowed by policy"

    mode, parts = split_expression(normalized)
    if not parts:
        return False, "missing license"

    def classify(token: str) -> str:
        if token in policy.denied_licenses:
            return "denied"
        if (
            token in policy.allowed_licenses
            or token in policy.conditionally_allowed_licenses
        ):
            return "allowed"
        return "unknown"

    statuses = [classify(part) for part in parts]

    if mode == "or":
        if "allowed" in statuses:
            return True, f"allowed via OR expression: {', '.join(parts)}"
        if "denied" in statuses:
            return False, f"denied OR expression: {', '.join(parts)}"
        return False, f"unknown OR expression: {', '.join(parts)}"

    if mode == "and":
        if all(status == "allowed" for status in statuses):
            return True, f"allowed AND expression: {', '.join(parts)}"
        denied = [part for part, status in zip(parts, statuses) if status == "denied"]
        if denied:
            return False, f"denied AND expression component: {', '.join(denied)}"
        unknown = [part for part, status in zip(parts, statuses) if status == "unknown"]
        return False, f"unknown AND expression component: {', '.join(unknown)}"

    token = parts[0]
    if token in policy.denied_licenses:
        return False, f"denied license: {token}"
    if token in policy.allowed_licenses:
        return True, f"allowed license: {token}"
    if token in policy.conditionally_allowed_licenses:
        return True, f"conditionally allowed license: {token}"
    return False, f"unknown license: {token}"


def run_pip_licenses() -> list[dict[str, Any]]:
    result = subprocess.run(
        ["pip-licenses", "--format=json", "--with-urls"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def main() -> int:
    policy = load_policy()
    packages = run_pip_licenses()
    failures: list[str] = []

    for package in packages:
        name = package.get("Name", "")
        version = package.get("Version", "")
        license_value = str(package.get("License", "")).strip()
        license_value = license_value.split("\n", 1)[0].strip()

        exception = find_exception(policy, name, version, license_value)
        if exception is not None:
            continue

        allowed, reason = evaluate_license(policy, license_value)
        if not allowed:
            failures.append(
                f"- {name}=={version}: {license_value or 'UNKNOWN'} ({reason})"
            )

    if failures:
        print("License compliance check failed for backend dependencies:")
        print("\n".join(failures))
        return 1

    print(f"Backend license compliance check passed for {len(packages)} dependencies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
