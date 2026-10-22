#!/usr/bin/env bash
# Discovery de Place IDs desde esta Mac, contra la base de producción por túnel SSH.
# No copia secretos al repo: lee el .env local (gitignored).
#
# Uso:
#   ./scripts/local_discovery.sh scan_place_ids_gratis --status
#   ./scripts/local_discovery.sh scan_place_ids_gratis --pasada bias --preset all --turbo --pause 2
#   ./scripts/local_discovery.sh scan_place_ids_gratis --pasada restriction --preset all --high-yield-only --skip-after-ids 50 --pause 2
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_PREFIX="${DISCOVERY_ENV_PREFIX:-$HOME/.local/micromamba/envs/vivemedellin}"
PY="$ENV_PREFIX/bin/python"
SERVER="${DISCOVERY_SERVER:-root@65.109.54.17}"
LOCAL_PORT="${DISCOVERY_LOCAL_PORT:-5433}"
REMOTE_PORT="${DISCOVERY_REMOTE_PORT:-5432}"

if [[ ! -x "$PY" ]]; then
  echo "No está el entorno con GDAL: $PY" >&2
  echo "Crealo con: micromamba create -y -n vivemedellin -c conda-forge python=3.12 gdal geos proj" >&2
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Falta $ROOT/.env (gitignored). Tiene que apuntar DATABASE_URL a 127.0.0.1:${LOCAL_PORT}." >&2
  exit 1
fi

export GDAL_LIBRARY_PATH="$ENV_PREFIX/lib/libgdal.dylib"
export GEOS_LIBRARY_PATH="$ENV_PREFIX/lib/libgeos_c.dylib"
export PROJ_DATA="$ENV_PREFIX/share/proj"
export PROJ_LIB="$PROJ_DATA"
export DYLD_FALLBACK_LIBRARY_PATH="$ENV_PREFIX/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"

if ! nc -z 127.0.0.1 "$LOCAL_PORT" >/dev/null 2>&1; then
  echo "Abriendo túnel SSH ${LOCAL_PORT} → ${SERVER}:${REMOTE_PORT}"
  ssh -f -N -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=4 -o TCPKeepAlive=yes \
    -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" "$SERVER"
fi

cd "$ROOT"
exec "$PY" manage.py "$@"
