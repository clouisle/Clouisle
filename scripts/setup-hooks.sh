#!/usr/bin/env bash
# Run once after cloning to enable pre-commit hooks.
set -euo pipefail
git config core.hooksPath .githooks
echo "✓ Git hooks configured (core.hooksPath = .githooks)"
