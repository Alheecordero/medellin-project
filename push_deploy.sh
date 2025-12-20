#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting deployment process...${NC}"

# Configuración
BRANCH=${BRANCH:-main}
SERVER=${SERVER:-root@5.161.85.163}
APP_DIR=${APP_DIR:-/var/www/medellin-project}
VENV_DIR=${VENV_DIR:-med}
SERVICE=${SERVICE:-gunicorn}
GIT_REPO=${GIT_REPO:-https://github.com/Alheecordero/medellin-project.git}

# Flags de despliegue (por defecto: modo rápido, no toca env/credenciales)
# --full habilita pip+migrate+static
DO_PIP=false
DO_MIGRATE=false
DO_STATIC=false
DO_RESTART=true
DO_COMPILE=false

for arg in "$@"; do
  case "$arg" in
    --full) DO_PIP=true; DO_MIGRATE=true; DO_STATIC=true ;;
    --pip) DO_PIP=true ;;
    --no-pip) DO_PIP=false ;;
    --migrate) DO_MIGRATE=true ;;
    --no-migrate) DO_MIGRATE=false ;;
    --static) DO_STATIC=true ;;
    --no-static) DO_STATIC=false ;;
    --restart) DO_RESTART=true ;;
    --no-restart) DO_RESTART=false ;;
    --compile) DO_COMPILE=true ;;
  esac
done

# Push a GitHub
echo -e "${GREEN}Verificando cambios locales...${NC}"
git add -A
if ! git diff --cached --quiet; then
    echo -e "${GREEN}Auto-commit de cambios locales...${NC}"
    git commit -m "auto: deploy $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
fi

echo -e "${GREEN}Pushing changes to GitHub...${NC}"
if ! git push origin "$BRANCH"; then
	echo -e "${RED}Failed to push changes to GitHub${NC}"
	exit 1
fi

# Actualizar y reiniciar en servidor
echo -e "${GREEN}Updating and restarting on server...${NC}"
ssh -o StrictHostKeyChecking=no "$SERVER" "bash -lc 'set -e; \
  cd \"$APP_DIR\"; \
  if [ ! -d .git ]; then echo -e \"${RED}ERROR: Git repo not found in $APP_DIR${NC}\"; exit 1; fi; \
  if [ ! -f .env ]; then echo -e \"${RED}ERROR: .env not found in $APP_DIR (required)${NC}\"; exit 1; fi; \
  # Guardrail: evitar que DEBUG quede activo (o duplicado) en producción, lo cual expone páginas técnicas en la web \
  DBG_COUNT=$(grep -c \"^DEBUG=\" .env || true); \
  if [ \"${DBG_COUNT:-0}\" -ne 1 ]; then \
    echo -e \"${RED}ERROR: .env must contain exactly ONE DEBUG=... line (found ${DBG_COUNT:-0}).${NC}\"; \
    echo -e \"${RED}Fix: keep a single line like DEBUG=False in /var/www/medellin-project/.env${NC}\"; \
    exit 1; \
  fi; \
  if grep -Eiq \"^DEBUG=(true|1|yes|on)$\" .env; then \
    echo -e \"${RED}ERROR: DEBUG is ON in production (.env). Set DEBUG=False before deploying.${NC}\"; \
    exit 1; \
  fi; \
  PREV_COMMIT=$(git rev-parse --short HEAD || echo none); \
  git fetch origin \"$BRANCH\" || true; \
  git checkout -B \"$BRANCH\"; \
  git reset --hard \"origin/$BRANCH\"; \
  # Do NOT remove untracked files to preserve .env and keys \
  if [ ! -d \"$VENV_DIR\" ]; then python3 -m venv \"$VENV_DIR\"; fi; \
  source \"$VENV_DIR\"/bin/activate; \
  # Respetar credenciales/entorno del servidor: NO tocar .env ni keys \
  if $DO_PIP; then pip install --upgrade pip; pip install -r requirements.txt; fi; \
  if $DO_MIGRATE; then python manage.py migrate --noinput; fi; \
  if $DO_COMPILE; then \
    echo Compilando mensajes i18n...; \
    python manage.py compilemessages -l en -l es || true; \
  fi; \
  if $DO_STATIC; then python manage.py collectstatic --noinput; fi; \
  sudo systemctl daemon-reload || true; \
  if $DO_RESTART; then sudo systemctl restart \"$SERVICE\"; fi; \
  sleep 2; \
  HC_CODE=$(curl -s -o /dev/null -w \"%{http_code}\" --unix-socket /run/gunicorn.sock http://localhost/ || echo 000); \
  if $DO_RESTART && [ \"\$HC_CODE\" != \"200\" ] && [ \"\$HC_CODE\" != \"301\" ]; then \
    echo \"Healthcheck failed (\$HC_CODE). Rolling back to \$PREV_COMMIT\"; \
    git reset --hard \"\$PREV_COMMIT\"; \
    sudo systemctl restart \"$SERVICE\"; \
    exit 1; \
  fi; \
  # Healthcheck adicional de API semántica (no bloqueante)
  curl -sS -H \"Accept: application/json\" \"https://vivemedellin.co/api/semantic-search/?q=ping&top=1\" -o /dev/null -w \"API:%{http_code}\\n\" || true; \
  # Healthcheck de jsi18n para ambos idiomas (no bloqueante)
  curl -s -o /dev/null -w \"JS:%{http_code}\\n\" http://localhost/jsi18n/ || true; \
  curl -s -o /dev/null -w \"JS_EN:%{http_code}\\n\" http://localhost/en/jsi18n/ || true; \
  if sudo nginx -t; then sudo systemctl reload nginx || true; else echo \"Skipping nginx reload (config test failed)\"; fi; \
  echo OK'"

if [ $? -ne 0 ]; then
	echo -e "${RED}Failed to update or restart on server${NC}"
	exit 1
fi

echo -e "${GREEN}Deployment completed successfully!${NC}"
