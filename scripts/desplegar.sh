#!/usr/bin/env bash
# Despliega origin/main en el servidor sin dejar el sitio caído a medias.
#
# Orden: push → código nuevo → check → migraciones → estáticos si cambiaron → prueba de las
# páginas clave con el código nuevo ANTES de reiniciar → caché → reinicio → verificación.
# Si check, migrate o la prueba fallan, vuelve al commit anterior y no reinicia: gunicorn
# sigue sirviendo el código viejo. (Una migración que ya se aplicó no se deshace sola: el
# script lo avisa.)
#
# No corre comandos de datos: esos van aparte, primero con --dry-run.
#
#   scripts/desplegar.sh            # despliega
#   scripts/desplegar.sh --plan     # solo dice qué cambiaría (commits, migraciones), no toca nada
set -euo pipefail

SERVER=${SERVER:-root@65.109.54.17}
SERVICE=${SERVICE:-gunicorn-vivemedellin}
HOST=${HOST:-vivemedellin.net}
# Páginas que tienen que dar 200 antes y después del reinicio.
URLS=${URLS:-"/ /guias/ /guias/centros-comerciales/ /que-hacer/ /que-hacer/tours-y-excursiones/ /lugares/ /sitemap.xml /en/"}

PLAN=false
[[ "${1:-}" == "--plan" ]] && PLAN=true

if [[ "$PLAN" == false ]]; then
  git push -q origin main
fi

ssh "$SERVER" PLAN="$PLAN" SERVICE="$SERVICE" HOST="$HOST" URLS="'$URLS'" bash -s <<'REMOTO'
set -euo pipefail
cd /var/www/medellin-project
PY=med/bin/python
ERR=/var/log/medellin/django.err

git fetch -q origin
PREV=$(git rev-parse HEAD)
NEW=$(git rev-parse origin/main)
if [[ "$PREV" == "$NEW" ]]; then
  echo "nada que desplegar: ya está en $(git log -1 --oneline)"
  exit 0
fi
echo "== de $(git log -1 --format='%h %s' "$PREV")"
echo "== a  $(git log -1 --format='%h %s' "$NEW")"
git log --oneline "$PREV..$NEW"
CAMBIADOS=$(git diff --name-only "$PREV" "$NEW")

if [[ "$PLAN" == true ]]; then
  echo "== archivos:"; echo "$CAMBIADOS" | sed 's/^/   /'
  echo "== migraciones nuevas:"; echo "$CAMBIADOS" | grep '/migrations/0' | sed 's/^/   /' || echo "   ninguna"
  echo "(--plan: no se tocó nada)"
  exit 0
fi

volver() {
  echo "!! $1: vuelvo a $(git log -1 --format='%h' "$PREV") sin reiniciar"
  git reset -q --hard "$PREV"
  [[ "${MIGRADO:-false}" == true ]] && echo "!! OJO: las migraciones nuevas ya se aplicaron; el código viejo tiene que tolerarlas"
  exit 1
}

MIGRADO=false
git reset -q --hard "$NEW"
$PY manage.py check >/dev/null 2>&1 || volver "manage.py check falló"

if $PY manage.py migrate --plan 2>/dev/null | grep -q '^  explorer\|^  [a-z_]*\.0'; then
  echo "== migraciones pendientes:"; $PY manage.py migrate --plan 2>/dev/null | grep -v '^Planned'
  $PY manage.py migrate --noinput 2>&1 | grep -v "objects imported" | tail -5 || volver "migrate falló"
  MIGRADO=true
fi

if echo "$CAMBIADOS" | grep -q '/static/'; then
  $PY manage.py collectstatic --noinput 2>&1 | tail -1 || volver "collectstatic falló"
fi

# Prueba con el código nuevo en un proceso aparte, antes de reiniciar.
$PY manage.py shell -c "
import sys
from django.test import Client
c = Client(HTTP_HOST='$HOST')
malas = [(u, r.status_code) for u in '$URLS'.split() for r in [c.get(u, secure=True)] if r.status_code != 200]
print('== prueba previa:', malas or 'todo 200')
sys.exit(1 if malas else 0)
" 2>&1 | grep -v "objects imported" || volver "la prueba previa falló"

LINEAS_ERR=$(wc -l < "$ERR" 2>/dev/null || echo 0)
$PY manage.py shell -c "from django.core.cache import cache; cache.clear()" >/dev/null 2>&1
systemctl restart "$SERVICE"
sleep 4
systemctl is-active --quiet "$SERVICE" || { echo "!! $SERVICE no arrancó"; journalctl -u "$SERVICE" -n 20 --no-pager; exit 1; }

FALLOS=0
for u in $URLS; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --resolve "$HOST:443:127.0.0.1" "https://$HOST$u" -k)
  [[ "$code" == 200 ]] || { echo "!! $u → $code"; FALLOS=1; }
done
NUEVOS=$(( $(wc -l < "$ERR" 2>/dev/null || echo 0) - LINEAS_ERR ))
echo "== desplegado $(git log -1 --oneline) | errores nuevos en django.err: $NUEVOS"
[[ "$FALLOS" == 0 && "$NUEVOS" -le 0 ]] || { echo "!! revisar: tail -50 $ERR"; exit 1; }
echo "== todo 200"
REMOTO
