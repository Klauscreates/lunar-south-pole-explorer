#!/usr/bin/env bash
set -euo pipefail

workspace_dir="$(cd "$(dirname "$0")/.." && pwd)"
python_bin="$workspace_dir/.venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  echo "Missing $python_bin; run 'uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e .[dev]'" >&2
  exit 2
fi

cd "$workspace_dir"
"$python_bin" -m unittest discover -s tests -v
"$python_bin" -m compileall -q science run_simulation.py

cd "$workspace_dir/apps/web"
npm run lint
npm run build
