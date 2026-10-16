#!/usr/bin/env bash
# Lanza N shards de scrape Maps en el VPS (tmux o nohup).
set -euo pipefail
ROOT="${ROOT:-/root/medellin-project}"
PY="${PY:-/root/UK/venv/bin/python}"
SHARDS="${SHARDS:-6}"
PAUSE="${PAUSE:-2.0}"
BATCH="${BATCH:-40}"
WAIT_MS="${WAIT_MS:-6500}"
LOG_DIR="$ROOT/data/maps_shards"

cd "$ROOT"
mkdir -p "$LOG_DIR"
export PYTHONPATH="$ROOT"
# Forzar túnel
if [[ -f /tmp/vive_db_tunnel.url ]]; then
  export DATABASE_URL="$(cat /tmp/vive_db_tunnel.url)"
elif [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

# Matar shards previos del worker (no tocar UK MenuRadar)
pkill -f "run_maps_shard_worker.py" 2>/dev/null || true
sleep 1

for i in $(seq 0 $((SHARDS - 1))); do
  out="$LOG_DIR/shard_${i}.out"
  echo "Launch shard $i/$SHARDS → $out"
  nohup "$PY" "$ROOT/scripts/run_maps_shard_worker.py" \
    --shard-index "$i" \
    --shard-count "$SHARDS" \
    --batch "$BATCH" \
    --pause "$PAUSE" \
    --wait-ms "$WAIT_MS" \
    --log-dir "$LOG_DIR" \
    >>"$out" 2>&1 &
  echo $! >"$LOG_DIR/shard_${i}.pid"
  sleep 2
done

echo "PIDs:"
cat "$LOG_DIR"/shard_*.pid
ps aux | grep run_maps_shard_worker | grep -v grep || true
echo "OK — seguir con: tail -f $LOG_DIR/shard_0.log"
