#!/usr/bin/env bash
# Migración rápida GCS → Cloudflare R2 con rclone (recomendado).
#
# rclone suele ser 5–15× más rápido que copiar objeto a objeto en Python
# porque paraleliza transferencias, reanuda fallos y evita cargar todo en RAM.
#
# Instalación (Ubuntu/Debian):
#   curl https://rclone.org/install.sh | sudo bash
#
# Configuración (una vez):
#   rclone config
#   → remote "gcs"  type google cloud storage, service_account_file
#   → remote "r2"   type s3, provider Cloudflare, endpoint sin /bucket
#
# O copia scripts/rclone.conf.example y edita credenciales:
#   export RCLONE_CONFIG="$PWD/scripts/rclone.conf"
#
# Uso:
#   ./scripts/migrar_gcs_a_r2_rclone.sh              # sync completo
#   ./scripts/migrar_gcs_a_r2_rclone.sh --dry-run
#   ./scripts/migrar_gcs_a_r2_rclone.sh --prefix tourism/
#   TRANSFERS=64 CHECKERS=128 ./scripts/migrar_gcs_a_r2_rclone.sh

set -euo pipefail

GCS_REMOTE="${GCS_REMOTE:-gcs:vivemedellin-bucket}"
R2_REMOTE="${R2_REMOTE:-r2:vivemedellin-media}"
TRANSFERS="${TRANSFERS:-48}"
CHECKERS="${CHECKERS:-96}"
LOG="${LOG:-data/rclone_gcs_r2.log}"
DRY_RUN=""
PREFIX=""

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN="--dry-run" ;;
    --prefix=*) PREFIX="${arg#*=}" ;;
    --prefix) shift; PREFIX="${1:-}" ;;
    -h|--help)
      sed -n '2,22p' "$0"
      exit 0
      ;;
  esac
done

mkdir -p "$(dirname "$LOG")"

SRC="$GCS_REMOTE"
DST="$R2_REMOTE"
if [[ -n "$PREFIX" ]]; then
  SRC="${GCS_REMOTE%/}/${PREFIX}"
  DST="${R2_REMOTE%/}/${PREFIX}"
fi

echo "════════════════════════════════════════════════════════"
echo " GCS → R2 (rclone)"
echo " Origen:  $SRC"
echo " Destino: $DST"
echo " transfers=$TRANSFERS  checkers=$CHECKERS"
echo " Log:     $LOG"
[[ -n "$DRY_RUN" ]] && echo " ⚠️  DRY RUN"
echo "════════════════════════════════════════════════════════"

rclone sync "$SRC" "$DST" \
  $DRY_RUN \
  --transfers "$TRANSFERS" \
  --checkers "$CHECKERS" \
  --fast-list \
  --s3-no-check-bucket \
  --retries 5 \
  --low-level-retries 10 \
  --stats 30s \
  --stats-one-line \
  --progress \
  --log-file "$LOG" \
  --log-level INFO

echo ""
echo "✓ Sync terminado. Revisa: $LOG"
echo "  Siguiente paso: python manage.py migrar_urls_gcs_a_r2 --verify-sample 50"
