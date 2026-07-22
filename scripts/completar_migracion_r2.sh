#!/usr/bin/env bash
# Completar migración GCS → R2 al 100% sin perder datos.
#
# Orden seguro (NO saltar pasos):
#   1. Copiar archivos (rclone sync)
#   2. Verificar integridad (rclone check)
#   3. URLs en BD (migrar_urls_gcs_a_r2)
#   4. Auditoría HTTP (verificar_migracion_r2)
#   5. Activar R2 en producción (.env + restart)
#   6. Período de gracia 7–14 días
#   7. Solo entonces: desactivar bucket GCS
#
# Uso en hserver3:
#   cd /var/www/medellin-project && source med/bin/activate
#   export RCLONE_CONFIG=/root/.config/rclone/rclone.conf
#   ./scripts/completar_migracion_r2.sh              # todo
#   ./scripts/completar_migracion_r2.sh --solo-sync  # solo copia
#   ./scripts/completar_migracion_r2.sh --solo-verify

set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/medellin-project}"
VENV="${VENV:-med}"
RCLONE_CONFIG="${RCLONE_CONFIG:-/root/.config/rclone/rclone.conf}"
LOG_DIR="$APP_DIR/data"
SYNC_LOG="$LOG_DIR/rclone_gcs_r2.log"
CHECK_LOG="$LOG_DIR/rclone_check.log"
VERIFY_LOG="$LOG_DIR/verificar_migracion_r2.log"
TRANSFERS="${TRANSFERS:-48}"
CHECKERS="${CHECKERS:-96}"

DO_SYNC=false
DO_CHECK=false
DO_URLS=false
DO_VERIFY=false
DO_ALL=false

for arg in "$@"; do
  case "$arg" in
    --solo-sync)  DO_SYNC=true ;;
    --solo-check) DO_CHECK=true ;;
    --solo-urls)  DO_URLS=true ;;
    --solo-verify) DO_VERIFY=true ;;
    --all|"")     DO_ALL=true ;;
    -h|--help)
      sed -n '2,22p' "$0"
      exit 0
      ;;
  esac
done

if $DO_ALL; then
  DO_SYNC=true DO_CHECK=true DO_URLS=true DO_VERIFY=true
fi

mkdir -p "$LOG_DIR"
cd "$APP_DIR"
source "$VENV/bin/activate"

step() {
  echo ""
  echo "════════════════════════════════════════════════════════"
  echo " $1"
  echo "════════════════════════════════════════════════════════"
}

# ── PASO 1: Copiar archivos ──
if $DO_SYNC; then
  step "PASO 1/4 — rclone sync (GCS → R2)"
  if pgrep -f "rclone sync gcs:vivemedellin-bucket" >/dev/null 2>&1; then
    echo "⚠️  Ya hay un rclone sync corriendo. Espera a que termine o mata el PID:"
    pgrep -af "rclone sync gcs:vivemedellin-bucket"
    exit 1
  fi
  export RCLONE_CONFIG
  rclone sync "gcs:vivemedellin-bucket" "r2:vivemedellin-media" \
    --transfers "$TRANSFERS" \
    --checkers "$CHECKERS" \
    --fast-list \
    --s3-no-check-bucket \
    --retries 5 \
    --low-level-retries 10 \
    --stats 30s \
    --stats-one-line \
    --log-file "$SYNC_LOG" \
    --log-level INFO
  echo "✓ Sync completado → $SYNC_LOG"
fi

# ── PASO 2: Verificar integridad bucket ──
if $DO_CHECK; then
  step "PASO 2/4 — rclone check (integridad)"
  export RCLONE_CONFIG
  rclone check "gcs:vivemedellin-bucket" "r2:vivemedellin-media" \
    --one-way \
    --error-on-no-match \
    --checkers "$CHECKERS" \
    --log-file "$CHECK_LOG" \
    --log-level INFO
  echo "✓ Check OK — buckets coinciden → $CHECK_LOG"
fi

# ── PASO 3: URLs en BD ──
if $DO_URLS; then
  step "PASO 3/4 — migrar URLs en BD"
  python manage.py migrar_urls_gcs_a_r2
fi

# ── PASO 4: Auditoría HTTP ──
if $DO_VERIFY; then
  step "PASO 4/4 — verificar_migracion_r2"
  python manage.py verificar_migracion_r2 --sample 100 --strict 2>&1 | tee "$VERIFY_LOG"
fi

step "SIGUIENTE (manual, cuando verificación pase al 100%)"
cat <<'EOF'

  A) Añadir al .env de producción (NO quitar GCS creds aún):
     R2_ENDPOINT_URL=...
     R2_BUCKET=vivemedellin-media
     R2_ACCESS_KEY_ID=...
     R2_SECRET_ACCESS_KEY=...
     R2_PUBLIC_BASE_URL=https://img.vivemedellin.co

  B) Reiniciar: sudo systemctl restart gunicorn-vivemedellin

  C) Probar sitio 24–48 h (home, detalle lugar, guías)

  D) Período de gracia 7–14 días con GCS bucket intacto (solo lectura)

  E) Última verificación:
     python manage.py verificar_migracion_r2 --sample 200 --rclone-check --strict

  F) SOLO ENTONCES desactivar/eliminar bucket GCS en Google Cloud Console

  ⚠️  NUNCA borrar GCS antes de:
     - rclone check sin errores
     - verificar_migracion_r2 ≥ 99.5% HTTP OK
     - período de gracia completado

EOF
