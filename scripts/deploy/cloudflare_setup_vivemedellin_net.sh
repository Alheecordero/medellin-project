#!/usr/bin/env bash
# Configura DNS en Cloudflare para vivemedellin.net → VPS Medellín
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
[[ -f "$ROOT/.env" ]] && set -a && source "$ROOT/.env" && set +a

TOKEN="$(printf '%s' "${CLOUDFLARE_API_TOKEN:-}" | tr -d "'\"" | xargs)"
ORIGIN="${ORIGIN_IP:-65.109.54.17}"
ZONE_NAME="${CLOUDFLARE_ZONE_NAME:-vivemedellin.net}"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

if [[ -z "$TOKEN" ]]; then
  echo "Falta CLOUDFLARE_API_TOKEN" >&2
  exit 1
fi

api() {
  curl -sS -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$@"
}

ZONE_ID="$(api "https://api.cloudflare.com/client/v4/zones?name=${ZONE_NAME}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); 
assert d.get('success'), d.get('errors'); 
r=d.get('result') or []; 
assert r, 'Zona no encontrada'; 
print(r[0]['id'])")"

echo "Zone: $ZONE_NAME ($ZONE_ID)"

upsert_a() {
  local name="$1"
  local proxied="$2"
  local existing
  existing="$(api "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?type=A&name=${name}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('result') or []; print(r[0]['id'] if r else '')")"
  local payload
  payload="$(python3 - <<PY
import json
print(json.dumps({
  "type": "A",
  "name": "$name",
  "content": "$ORIGIN",
  "proxied": $proxied,
  "ttl": 1,
}))
PY
)"
  if [[ "$DRY" == 1 ]]; then
    echo "DRY upsert A $name -> $ORIGIN proxied=$proxied"
    return
  fi
  if [[ -n "$existing" ]]; then
    api -X PUT "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records/${existing}" --data "$payload" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('success'), d.get('errors'); print('OK update', '$name')"
  else
    api -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records" --data "$payload" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('success'), d.get('errors'); print('OK create', '$name')"
  fi
}

upsert_cname() {
  local name="$1"
  local target="$2"
  local proxied="$3"
  local existing
  existing="$(api "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?type=CNAME&name=${name}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); r=d.get('result') or []; print(r[0]['id'] if r else '')")"
  local payload
  payload="$(python3 - <<PY
import json
print(json.dumps({
  "type": "CNAME",
  "name": "$name",
  "content": "$target",
  "proxied": $proxied,
  "ttl": 1,
}))
PY
)"
  if [[ "$DRY" == 1 ]]; then
    echo "DRY upsert CNAME $name -> $target"
    return
  fi
  if [[ -n "$existing" ]]; then
    api -X PUT "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records/${existing}" --data "$payload" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('success'), d.get('errors'); print('OK update', '$name')"
  else
    api -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records" --data "$payload" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('success'), d.get('errors'); print('OK create', '$name')"
  fi
}

upsert_a "$ZONE_NAME" true
upsert_a "www.$ZONE_NAME" true
upsert_cname "img.$ZONE_NAME" "vivemedellin-media.r2.dev" true

# ads.txt via Transform Rule alternative: use DNS TXT is wrong. Origin serves /ads.txt.
# SSL mode: full (strict) if origin has cert - nginx is HTTP only, CF flexible or full

if [[ "$DRY" == 0 ]]; then
  api -X PATCH "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings/ssl" \
    --data '{"value":"full"}' \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print('SSL', d.get('success'), d.get('result',{}).get('value'))"
  api -X PATCH "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings/always_use_https" \
    --data '{"value":"on"}' \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print('HTTPS', d.get('success'))"
fi

echo "Done. Verifica: dig A $ZONE_NAME && curl -sS https://$ZONE_NAME/ads.txt"
