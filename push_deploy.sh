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
if ! git diff --quiet || ! git diff --cached --quiet; then
	echo -e "${GREEN}Auto-commit de cambios locales...${NC}"
	git add -A
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
  mkdir -p "$APP_DIR"; cd "$APP_DIR"; \
  git config --global --add safe.directory "$APP_DIR" || true; \
  git config --global init.defaultBranch main || true; \
  if [ -d .git ]; then \
    git fetch origin "$BRANCH" || true; \
    (git checkout -f "$BRANCH" || git checkout -B "$BRANCH"); \
    git reset --hard "origin/$BRANCH" || true; \
    git clean -fd || true; \
  else \
    if [ -z "$(ls -A .)" ]; then \
      git clone -b "$BRANCH" "$GIT_REPO" .; \
    else \
      git init; \
      git remote remove origin 2>/dev/null || true; \
      git remote add origin "$GIT_REPO"; \
      git fetch origin "$BRANCH"; \
      git checkout -B "$BRANCH"; \
      git reset --hard "origin/$BRANCH"; \
      git clean -fd; \
    fi; \
  fi; \
  if [ ! -d "$VENV_DIR" ]; then python3 -m venv "$VENV_DIR"; fi; \
  source "$VENV_DIR"/bin/activate; \
  pip install --upgrade pip; \
  pip install -r requirements.txt; \
  python manage.py migrate --noinput; \
  python manage.py collectstatic --noinput; \
  sudo systemctl daemon-reload || true; \
  sudo systemctl restart "$SERVICE" || true; \
  sudo systemctl status "$SERVICE" --no-pager || true; \
  sudo systemctl reload nginx || true; \
  echo OK'"

if [ $? -ne 0 ]; then
	echo -e "${RED}Failed to update or restart on server${NC}"
	exit 1
fi

echo -e "${GREEN}Deployment completed successfully!${NC}"
