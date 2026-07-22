#!/usr/bin/env bash
# Constantes compartidas: nginx + Cloudflare WAF (misma lista que MenuRadar/SPAIN).

GEO_BLOCK_COUNTRIES=(
  CN RU KP IR BY SY CU VE PK BD NG EG ID VN PH MM
  KZ UZ TM TJ KG AF IQ YE LY SD SO ET ZW
)

# Países NO bloqueados (turismo/AdSense): CO ES US MX + UE + CA AU UK, etc.
# Solo listado informativo; la regla es deny-list arriba.

WAF_RULE_DESCRIPTION='ViveMedellín: block non-target countries'
WAF_EXPRESSION='(not cf.client.bot.verified_bot and ip.geoip.country in {"CN" "RU" "KP" "IR" "BY" "SY" "CU" "VE" "PK" "BD" "NG" "EG" "ID" "VN" "PH" "MM" "KZ" "UZ" "TM" "TJ" "KG" "AF" "IQ" "YE" "LY" "SD" "SO" "ET" "ZW"})'

DEFAULT_ZONE_NAME='vivemedellin.co'
NGINX_GEO_INCLUDE='/etc/nginx/vivemedellin-geo-block.conf'
