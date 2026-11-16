#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export NEXUS3_ROOT="$ROOT"
cd "$ROOT"
exec python3 nexus3.py doctor
