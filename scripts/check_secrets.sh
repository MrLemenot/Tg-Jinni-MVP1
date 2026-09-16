#!/usr/bin/env bash
set -euo pipefail

# Local pre-push style check. Requires gitleaks installed and available on PATH.
if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks is not installed. Install it or rely on the GitHub Actions secret scan."
  exit 2
fi

gitleaks git --redact --verbose .
