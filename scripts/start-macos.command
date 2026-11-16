#!/bin/bash
# Launcher macOS — Nexus Portable 3.0
# Caminhos relativos ao proprio script; nenhuma dependencia de diretorio atual.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export NEXUS3_ROOT="$ROOT"
cd "$ROOT"

if [ ! -f "$ROOT/nexus3.py" ]; then
  echo "[NEXUS 3] nexus3.py nao encontrado em $ROOT (instalacao incompleta)." >&2
  exit 2
fi

# Retorna 0 somente se o interpretador for Python 3.10+ ( requisito do nucleo ).
is_py310() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

if command -v python3 >/dev/null 2>&1 && is_py310 python3; then
  exec python3 nexus3.py start "$@"
fi
if [ -x "$ROOT/runtime/python/bin/python3" ] && is_py310 "$ROOT/runtime/python/bin/python3"; then
  exec "$ROOT/runtime/python/bin/python3" nexus3.py start "$@"
fi

echo "[NEXUS 3] Python 3.10+ nao encontrado. Instale o Python ou coloque um runtime portatil em runtime/python/bin." >&2
exit 1
