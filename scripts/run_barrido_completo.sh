#!/bin/bash
cd /var/www/medellin-project
source med/bin/activate
export PYTHONUNBUFFERED=1
LOG=data/scan_pipeline_completo.log
SCAN="python manage.py scan_place_ids_gratis --fast --retries 5 --rate-limit-sleep 120"

run() {
  echo "" | tee -a "$LOG"
  echo "======== $(date -Iseconds) $* ========" | tee -a "$LOG"
  $SCAN "$@" >> "$LOG" 2>&1 || echo "WARN: fase fallo: $*" | tee -a "$LOG"
}

run --preset all --pasada bias
run --preset all --pasada bias --rescan-vacios --radio 450
run --preset all --pasada restriction
run --preset all --pasada generico
echo "======== $(date -Iseconds) PIPELINE COMPLETO ========" | tee -a "$LOG"
