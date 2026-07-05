#!/usr/bin/env bash
# Convenience wrapper for the end-to-end smoke test. Activates the venv if present.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  . .venv/bin/activate
fi
echo "== unit tests =="
python -m pytest -q
echo
echo "== end-to-end smoke (stdio + http) =="
python scripts/smoke.py
