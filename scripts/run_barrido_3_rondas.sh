#!/bin/bash
# 3 rondas de sub-grilla con offsets distintos + scan bias en huecos.
# Ronda 1 (cardinal 250m) ya se ejecutó en el pipeline smart v2 — por defecto arranca en 2.
set -e
cd /var/www/medellin-project
source med/bin/activate
export PYTHONUNBUFFERED=1

DESDE="${1:-2}"   # ./run_barrido_3_rondas.sh 1  → incluir ronda 1
HASTA="${2:-3}"
LOG=data/scan_pipeline_3rondas.log
SCAN="python manage.py scan_place_ids_gratis --smart --retries 5 --rate-limit-sleep 120"

log() {
  echo "" | tee -a "$LOG"
  echo "======== $(date -Iseconds) $* ========" | tee -a "$LOG"
}

log "INICIO BARRIDO 3 RONDAS (desde ronda $DESDE hasta $HASTA)"

for RONDA in $(seq "$DESDE" "$HASTA"); do
  log "generar_subgrilla_saturacion --ronda $RONDA --alcance base"
  python manage.py generar_subgrilla_saturacion --ronda "$RONDA" --alcance base >> "$LOG" 2>&1

  log "scan bias ronda $RONDA --solo-huecos"
  $SCAN --preset all --pasada bias --solo-huecos >> "$LOG" 2>&1
done

log "rescan vacios radio 450"
$SCAN --preset all --pasada bias --rescan-vacios --radio 450 >> "$LOG" 2>&1

log "BARRIDO 3 RONDAS COMPLETO"
