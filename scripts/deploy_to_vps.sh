#!/usr/bin/env bash
# Deploy latest main to VPS (matches systemd WorkingDirectory).
# Prereq: SSH key auth to VPS (no password in script).
#
#   export VPS_HOST=your.ip.or.host
#   export VPS_USER=root                    # optional, default root
#   export DEPLOY_PATH=/root/wave-structure-engine
#   export SYSTEMD_SERVICE=elliott-wave-orchestrator
#   ./scripts/deploy_to_vps.sh
#
# Or load from .env (same keys as .env.example VPS_*):
#   set -a && [ -f .env ] && source .env && set +a && ./scripts/deploy_to_vps.sh

set -euo pipefail

VPS_HOST="${VPS_HOST:-${VPS_IP:-}}"
VPS_USER="${VPS_USER:-root}"
DEPLOY_PATH="${DEPLOY_PATH:-/root/wave-structure-engine}"
SYSTEMD_SERVICE="${SYSTEMD_SERVICE:-elliott-wave-orchestrator}"

if [[ -z "$VPS_HOST" ]]; then
  echo "ERROR: Set VPS_HOST (or VPS_IP) to your server address." >&2
  exit 1
fi

echo ">>> Deploy to ${VPS_USER}@${VPS_HOST}:${DEPLOY_PATH}"

ssh -o BatchMode=yes -o ConnectTimeout=20 "${VPS_USER}@${VPS_HOST}" bash <<EOF
set -e
cd "${DEPLOY_PATH}"
git fetch origin main
git reset --hard origin/main
if [[ -d .venv ]]; then
  .venv/bin/pip install -q -r requirements.txt
else
  echo "WARN: no .venv at ${DEPLOY_PATH}; create with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
fi
if systemctl cat "${SYSTEMD_SERVICE}.service" &>/dev/null; then
  sudo systemctl restart "${SYSTEMD_SERVICE}" || true
  sudo systemctl --no-pager status "${SYSTEMD_SERVICE}" || true
fi
# Optional: place SL/TP on already-open positions (no market close). Set ENSURE_PROTECTIONS=1 when calling this script.
if [[ "${ENSURE_PROTECTIONS:-0}" == "1" ]] && [[ -d .venv ]]; then
  echo ">>> ENSURE_PROTECTIONS=1: running scripts/ensure_position_protections.py"
  set -a
  [[ -f .env ]] && source .env
  set +a
  .venv/bin/python scripts/ensure_position_protections.py || true
fi
echo ">>> Done. HEAD: \$(git log -1 --oneline)"
EOF

echo ">>> Local: push already on origin/main; VPS is now at same commit."
