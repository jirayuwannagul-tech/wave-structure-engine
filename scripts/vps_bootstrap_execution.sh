#!/usr/bin/env bash
# Read-only checklist for VPS execution (no secrets printed).
# Run from repo root: ./scripts/vps_bootstrap_execution.sh
# With .env loaded: set -a && source .env && set +a && ./scripts/vps_bootstrap_execution.sh

set -euo pipefail

ok() { echo "[ok] $*"; }
warn() { echo "[!!] $*" >&2; }

echo "=== VPS execution checklist ==="

if [[ -f .env ]]; then ok ".env present"; else warn "no .env in cwd ($(pwd))"; fi

check_env() {
  local n="$1"
  local v="${!n:-}"
  if [[ -n "${v:-}" ]]; then ok "$n is set"; else warn "$n is empty"; fi
}

for k in BINANCE_EXECUTION_ENABLED BINANCE_LIVE_ORDER_ENABLED KILL_SWITCH BINANCE_FUTURES_API_KEY BINANCE_FUTURES_API_SECRET; do
  check_env "$k"
done

if [[ "${BINANCE_LIVE_ORDER_ENABLED:-0}" =~ ^(1|true|yes|on)$ ]]; then
  ok "BINANCE_LIVE_ORDER_ENABLED allows order placement"
else
  warn "BINANCE_LIVE_ORDER_ENABLED not true — SL/TP will NOT be sent to Binance"
fi

if [[ -d .venv ]]; then ok ".venv exists"; else warn "no .venv — create: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; fi

if [[ -f scripts/ensure_position_protections.py ]]; then ok "ensure_position_protections.py"; else warn "missing scripts/ensure_position_protections.py"; fi
if [[ -f scripts/sync_sheet_signals.py ]]; then ok "sync_sheet_signals.py"; else warn "missing scripts/sync_sheet_signals.py"; fi

echo ""
echo "Suggested commands (after fixing env):"
echo "  sudo systemctl restart elliott-wave-orchestrator"
echo "  set -a && source .env && set +a && .venv/bin/python scripts/ensure_position_protections.py"
echo "  set -a && source .env && set +a && .venv/bin/python scripts/sync_sheet_signals.py"
echo "=== end ==="
