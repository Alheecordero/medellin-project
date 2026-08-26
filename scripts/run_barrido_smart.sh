#!/bin/bash
# Pipeline rápido post-saturación: sub-grilla + bias en huecos (sin repetir fases cerradas).
set -e
cd /var/www/medellin-project
source med/bin/activate
export PYTHONUNBUFFERED=1
LOG=data/scan_pipeline_smart.log
SCAN="python manage.py scan_place_ids_gratis --smart --retries 5 --rate-limit-sleep 120"

log() {
  echo "" | tee -a "$LOG"
  echo "======== $(date -Iseconds) $* ========" | tee -a "$LOG"
}

run() {
  log "$*"
  $SCAN "$@" >> "$LOG" 2>&1
}

log "INICIO BARRIDO SMART v2"

# Fases 2A/2B: solo si quedan pendientes (evita 2×2.405 iteraciones inútiles).
PEND_RESTR=$(python manage.py shell -c "
from explorer.utils.text_scan_progress import initialgrid_qs
print(initialgrid_qs().filter(is_text_scan_processed=True).exclude(text_scan_passes__contains=['restriction']).count())
" 2>/dev/null | tail -1)
PEND_GEN=$(python manage.py shell -c "
from explorer.utils.text_scan_progress import initialgrid_qs
print(initialgrid_qs().filter(is_text_scan_processed=True).exclude(text_scan_passes__contains=['generico']).count())
" 2>/dev/null | tail -1)

if [ "${PEND_RESTR:-0}" -gt 0 ]; then
  run --preset all --pasada restriction
else
  log "SKIP restriction (0 pendientes)"
fi

if [ "${PEND_GEN:-0}" -gt 0 ]; then
  run --preset all --pasada generico
else
  log "SKIP generico (0 pendientes)"
fi

# Sub-grilla: 4 puntos nuevos por cada celda con >=50 IDs (supera tope 60/query).
log "generar_subgrilla_saturacion"
python manage.py generar_subgrilla_saturacion >> "$LOG" 2>&1

# Bias solo en sub-puntos vacíos; radio 350 m evita solapar con el padre (600 m).
run --preset all --pasada bias --solo-huecos

# Segunda pasada en celdas que siguen vacías.
run --preset all --pasada bias --rescan-vacios --radio 450

log "BARRIDO SMART v2 COMPLETO"
