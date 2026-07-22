#!/usr/bin/env bash
# Instala/actualiza bloqueo geo en Nginx (origen). Ejecutar EN EL VPS como root.
#   APP_DIR=/var/www/medellin-project bash scripts/deploy/setup_geo_block_nginx.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/medellin-project}"
# shellcheck source=geo_block_shared.sh
source "$APP_DIR/scripts/deploy/geo_block_shared.sh"

say() { printf '\n== %s ==\n' "$*"; }

say "Copiar mapas geo → $NGINX_GEO_INCLUDE"
cp -f "$APP_DIR/scripts/deploy/nginx/geo_block_countries.conf" "$NGINX_GEO_INCLUDE"

SITE_SRC="$APP_DIR/scripts/deploy/nginx/vivemedellin.conf"
SITE_DST="/etc/nginx/sites-available/vivemedellin"

if [[ -f "$SITE_SRC" ]]; then
  say "Instalar site $SITE_DST (incluye geo-block en www)"
  cp -f "$SITE_SRC" "$SITE_DST"
  ln -sf "$SITE_DST" /etc/nginx/sites-enabled/vivemedellin
else
  say "Aviso: falta $SITE_SRC — solo se instaló $NGINX_GEO_INCLUDE"
  say "Añade manualmente en http/sites:"
  echo "  include $NGINX_GEO_INCLUDE;"
  echo '  if ($geo_block_request) { return 403; }  # dentro de server www'
fi

nginx -t
systemctl reload nginx

say "Listo. Verifica con:"
echo "  bash $APP_DIR/scripts/deploy/verify_geo_block.sh"
