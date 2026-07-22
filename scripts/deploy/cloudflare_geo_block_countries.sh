#!/usr/bin/env bash
# Crea/actualiza regla WAF en Cloudflare: bloqueo por país (bajo RPM / no objetivo).
# Requiere token con Zone → Firewall Services → Edit + Zone → Read.
#
# Uso (desde raíz del repo, con .env cargado):
#   source .env   # CLOUDFLARE_API_TOKEN, opcional CLOUDFLARE_ZONE_ID
#   ./scripts/deploy/cloudflare_geo_block_countries.sh --dry-run
#   ./scripts/deploy/cloudflare_geo_block_countries.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
[[ -f "$ROOT/.env" ]] && set -a && source "$ROOT/.env" && set +a
# shellcheck source=geo_block_shared.sh
source "$(dirname "${BASH_SOURCE[0]}")/geo_block_shared.sh"

TOKEN="${CLOUDFLARE_API_TOKEN:-}"
ZONE="${CLOUDFLARE_ZONE_ID:-}"
ZONE_NAME="${CLOUDFLARE_ZONE_NAME:-$DEFAULT_ZONE_NAME}"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

if [[ -z "$TOKEN" ]]; then
  echo "Falta CLOUDFLARE_API_TOKEN en .env" >&2
  echo "Permisos: Zone Firewall Services Edit + Zone Read ($ZONE_NAME)" >&2
  exit 1
fi

if [[ -z "$ZONE" ]]; then
  ZONE=$(curl -sS -H "Authorization: Bearer $TOKEN" \
    "https://api.cloudflare.com/client/v4/zones?name=${ZONE_NAME}" \
    | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['result'][0]['id'] if r.get('success') and r.get('result') else '')")
fi
[[ -n "$ZONE" ]] || { echo "No se pudo resolver zone id ${ZONE_NAME}" >&2; exit 1; }

echo "Zone: $ZONE ($ZONE_NAME)"
echo "Expression: $WAF_EXPRESSION"

ENTRY=$(curl -sS -H "Authorization: Bearer $TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE/rulesets/phases/http_request_firewall_custom/entrypoint")

python3 - <<'PY' "$ENTRY"
import json, sys
d = json.loads(sys.argv[1])
if not d.get("success"):
    print("ERROR entrypoint:", d.get("errors"), file=sys.stderr)
    sys.exit(2)
r = d["result"]
print("ruleset_id", r["id"])
print("existing_rules", len(r.get("rules") or []))
for rule in r.get("rules") or []:
    if rule.get("description") == "ViveMedellín: block non-target countries":
        print("found_existing", rule.get("id"))
PY

RULESET_ID=$(echo "$ENTRY" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['id'])")
EXISTING=$(echo "$ENTRY" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)['result'].get('rules') or []))")

PAYLOAD=$(EXISTING="$EXISTING" WAF_RULE_DESCRIPTION="$WAF_RULE_DESCRIPTION" WAF_EXPRESSION="$WAF_EXPRESSION" python3 - <<'PY'
import json, os
rules = json.loads(os.environ["EXISTING"])
desc = os.environ["WAF_RULE_DESCRIPTION"]
expr = os.environ["WAF_EXPRESSION"]
new_rule = {
    "action": "block",
    "expression": expr,
    "description": desc,
    "enabled": True,
}
filtered = [r for r in rules if r.get("description") != desc]
filtered.insert(0, new_rule)
print(json.dumps({"rules": filtered}))
PY
)

if [[ "$DRY_RUN" == 1 ]]; then
  echo "DRY-RUN payload:"
  echo "$PAYLOAD" | python3 -m json.tool | head -40
  exit 0
fi

RESP=$(curl -sS -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE/rulesets/$RULESET_ID" \
  --data "$PAYLOAD")

python3 - <<'PY' "$RESP"
import json, sys
d = json.loads(sys.argv[1])
if d.get("success"):
    print("OK: regla WAF aplicada en Cloudflare edge")
else:
    print("FAIL:", json.dumps(d.get("errors"), indent=2), file=sys.stderr)
    sys.exit(1)
PY
