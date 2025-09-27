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
  PREV_COMMIT=$(git rev-parse --short HEAD || echo none); \
  git fetch origin \"$BRANCH\" || true; \
  git checkout -B \"$BRANCH\"; \
  git reset --hard \"origin/$BRANCH\"; \
  # Do NOT remove untracked files to preserve .env and keys \
  if [ ! -d \"$VENV_DIR\" ]; then python3 -m venv \"$VENV_DIR\"; fi; \
  source \"$VENV_DIR\"/bin/activate; \
  pip install --upgrade pip; \
  pip install -r requirements.txt; \
  python manage.py migrate --noinput; \
  python manage.py collectstatic --noinput; \
  sudo systemctl daemon-reload || true; \
  sudo systemctl restart \"$SERVICE\"; \
  sleep 2; \
  HC_CODE=$(curl -s -o /dev/null -w \"%{http_code}\" --unix-socket /run/gunicorn.sock http://localhost/ || echo 000); \
  if [ \"\$HC_CODE\" != \"200\" ] && [ \"\$HC_CODE\" != \"301\" ]; then \
    echo \"Healthcheck failed (\$HC_CODE). Rolling back to \$PREV_COMMIT\"; \
    git reset --hard \"\$PREV_COMMIT\"; \
    sudo systemctl restart \"$SERVICE\"; \
    exit 1; \
  fi; \
  if sudo nginx -t; then sudo systemctl reload nginx || true; else echo \"Skipping nginx reload (config test failed)\"; fi; \
  echo OK'"

if [ $? -ne 0 ]; then
	echo -e "${RED}Failed to update or restart on server${NC}"
	exit 1
fi

echo -e "${GREEN}Deployment completed successfully!${NC}"
