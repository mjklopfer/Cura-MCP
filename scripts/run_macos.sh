#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE="${CURA_MCP_NODE:-}"
if [[ -z "$NODE" ]]; then
  for candidate in /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node; do
    if [[ -x "$candidate" ]]; then NODE="$candidate"; break; fi
  done
fi
if [[ -z "$NODE" ]]; then NODE="$(command -v node || true)"; fi
[[ -n "$NODE" && -x "$NODE" ]] || { echo "Node.js 20+ is required." >&2; exit 1; }
"$NODE" -e 'if(Number(process.versions.node.split(".")[0])<20)process.exit(1)' || { echo "Node.js 20+ is required." >&2; exit 1; }
if [[ -z "${CURA_MCP_PYTHON:-}" ]]; then
  CURA_MCP_PYTHON="$(command -v python3 || true)"
  for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if [[ -z "$CURA_MCP_PYTHON" && -x "$candidate" ]]; then CURA_MCP_PYTHON="$candidate"; fi
  done
fi
[[ -n "$CURA_MCP_PYTHON" && -x "$CURA_MCP_PYTHON" ]] || { echo "Python 3 is required." >&2; exit 1; }
"$CURA_MCP_PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || { echo "Python 3.10+ is required." >&2; exit 1; }
export CURA_MCP_PYTHON
export CURA_PRINTER_BASE_URL="${CURA_PRINTER_BASE_URL:?Set CURA_PRINTER_BASE_URL to your printer HTTP origin}"
export CURA_MCP_BRIDGE_CONNECTION_PATH="${CURA_MCP_BRIDGE_CONNECTION_PATH:-$HOME/Library/Application Support/cura/${CURA_MCP_CURA_VERSION:-5.14}/cura-mcp-bridge.json}"
export CURA_MCP_PRINT_FILE_ROOT="${CURA_MCP_PRINT_FILE_ROOT:-$HOME/Library/Application Support/CuraMcpBridge/print_files}"
mkdir -p "$CURA_MCP_PRINT_FILE_ROOT"
exec "$NODE" "$SCRIPT_DIR/src/server.mjs"
