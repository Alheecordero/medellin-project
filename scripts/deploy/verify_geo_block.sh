#!/usr/bin/env bash
# Comprueba bloqueo geo en origen (Nginx + header CF-IPCountry simulado).
set -euo pipefail

HOST="${GEO_TEST_HOST:-www.vivemedellin.co}"
BASE="${GEO_TEST_URL:-http://127.0.0.1/}"

pass=0
fail=0

check_code() {
  local name="$1" expected="$2"
  shift 2
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' "$@" || echo 000)
  if [[ "$code" == "$expected" ]]; then
    echo "OK  $name → HTTP $code"
    pass=$((pass + 1))
  else
    echo "FAIL $name → HTTP $code (esperado $expected)" >&2
    fail=$((fail + 1))
  fi
}

check_one_of() {
  local name="$1"
  shift
  local -a expected=()
  while [[ $# -gt 1 ]]; do
    expected+=("$1")
    shift
  done
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' "$@" || echo 000)
  local ok=0
  for e in "${expected[@]}"; do
    if [[ "$code" == "$e" ]]; then
      ok=1
      break
    fi
  done
  if [[ "$ok" == 1 ]]; then
    echo "OK  $name → HTTP $code"
    pass=$((pass + 1))
  else
    echo "FAIL $name → HTTP $code (esperado: ${expected[*]})" >&2
    fail=$((fail + 1))
  fi
}

echo "Host: $HOST  URL: $BASE"
echo ""

check_code "CN sin bot → 403" "403" \
  -H "Host: $HOST" -H "CF-IPCountry: CN" "$BASE"

check_one_of "ES → 200 o 301" "200" "301" \
  -H "Host: $HOST" -H "CF-IPCountry: ES" "$BASE"

check_one_of "CN + Googlebot → 200 o 301" "200" "301" \
  -H "Host: $HOST" -H "CF-IPCountry: CN" \
  -A "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" \
  "$BASE"

echo ""
echo "Resultado: $pass OK, $fail FAIL"
[[ "$fail" -eq 0 ]]
