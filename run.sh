#!/usr/bin/env bash
# Start SystemInspector (local only, free stack).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "SystemInspector → http://127.0.0.1:8787"
echo "Only reachable on this machine. Ctrl+C to stop."
exec python -m uvicorn backend.main:app --host 127.0.0.1 --port 8787
