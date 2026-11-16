#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export NEXUS3_ROOT="$ROOT"
cd "$ROOT"
if command -v python3 >/dev/null 2>&1; then
  exec python3 nexus3.py start "$@"
fi
if [ -x "$ROOT/runtime/python/bin/python3" ]; then
  exec "$ROOT/runtime/python/bin/python3" nexus3.py start "$@"
fi
echo "[NEXUS 3] Python 3.10+ nao encontrado. Instale o Python ou coloque um runtime portatil em runtime/python/bin."
exit 1
