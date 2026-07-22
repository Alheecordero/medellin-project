#!/usr/bin/env bash
# Aplica bloqueo geo: Nginx en VPS + WAF Cloudflare (desde máquina local).
#
# Uso:
#   ./scripts/deploy/apply_geo_block.sh --dry-run
#   ./scripts/deploy/apply_geo_block.sh
#   SERVER=root@65.109.54.17 ./scripts/deploy/apply_geo_block.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER="${SERVER:-root@65.109.54.17}"
APP_DIR="${APP_DIR:-/var/www/medellin-project}"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

echo "== Cloudflare WAF =="
if [[ "$DRY_RUN" == 1 ]]; then
  bash "$ROOT/scripts/deploy/cloudflare_geo_block_countries.sh" --dry-run
else
  bash "$ROOT/scripts/deploy/cloudflare_geo_block_countries.sh"
fi

echo ""
echo "== Nginx origen ($SERVER) =="
if [[ "$DRY_RUN" == 1 ]]; then
  echo "DRY-RUN: ssh $SERVER APP_DIR=$APP_DIR bash $APP_DIR/scripts/deploy/setup_geo_block_nginx.sh"
  echo "DRY-RUN: ssh $SERVER bash $APP_DIR/scripts/deploy/verify_geo_block.sh"
  exit 0
fi

ssh -o StrictHostKeyChecking=no "$SERVER" "bash -lc '
  set -e
  cd \"$APP_DIR\"
  git pull origin main 2>/dev/null || true
  APP_DIR=\"$APP_DIR\" bash scripts/deploy/setup_geo_block_nginx.sh
  bash scripts/deploy/verify_geo_block.sh
'"

echo ""
echo "OK: geo-block nginx + Cloudflare aplicado"
