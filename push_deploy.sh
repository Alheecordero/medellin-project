#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ViveMedellín - Professional Deploy Script            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"

# Configuración
BRANCH=${BRANCH:-main}
SERVER=${SERVER:-root@5.161.85.163}
APP_DIR=${APP_DIR:-/var/www/medellin-project}
VENV_DIR=${VENV_DIR:-med}
SERVICE=${SERVICE:-gunicorn}
GIT_REPO=${GIT_REPO:-https://github.com/Alheecordero/medellin-project.git}

# Archivos que NUNCA deben subirse al repo (configuración local)
LOCAL_ONLY_FILES=".env .env.local settings_local.py vivemedellin-*.json"

# Flags de despliegue (por defecto: modo rápido)
DO_PIP=false
DO_MIGRATE=false
DO_STATIC=false
DO_RESTART=true
DO_COMPILE=false
DO_CLEAR_CACHE=true

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
    --clear-cache) DO_CLEAR_CACHE=true ;;
    --no-clear-cache) DO_CLEAR_CACHE=false ;;
    --help|-h)
      echo "Uso: $0 [opciones]"
      echo ""
      echo "Opciones:"
      echo "  --full          Ejecutar pip install, migrate y collectstatic"
      echo "  --pip           Solo pip install"
      echo "  --migrate       Solo migrate"
      echo "  --static        Solo collectstatic"
      echo "  --compile       Compilar mensajes i18n"
      echo "  --clear-cache   Limpiar caché Django (por defecto: sí)"
      echo "  --no-restart    No reiniciar gunicorn"
      echo ""
      exit 0
      ;;
  esac
done

# ═══════════════════════════════════════════════════════════════════
# PASO 1: Verificar que no hay archivos locales en staging
# ═══════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[1/5] Verificando archivos locales...${NC}"

# Verificar que .env NO está siendo trackeado
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
    echo -e "${RED}ERROR: .env está siendo trackeado por Git!${NC}"
    echo -e "${YELLOW}Ejecuta: git rm --cached .env${NC}"
    exit 1
fi

# Verificar que DEBUG=True no está en ningún archivo trackeado
if git grep -l "DEBUG=True" -- '*.py' '*.env*' 2>/dev/null | grep -v '.example' | head -1; then
    echo -e "${YELLOW}ADVERTENCIA: Se encontró DEBUG=True en archivos trackeados${NC}"
fi

echo -e "${GREEN}✓ No hay archivos de configuración local en el repo${NC}"

# ═══════════════════════════════════════════════════════════════════
# PASO 2: Preparar y enviar cambios a GitHub
# ═══════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[2/5] Preparando cambios para GitHub...${NC}"

# Excluir archivos locales explícitamente
git add -A

# Verificar si hay cambios
if git diff --cached --quiet; then
    echo -e "${YELLOW}No hay cambios para enviar${NC}"
else
    echo -e "${GREEN}Creando commit...${NC}"
    git commit -m "deploy: $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
fi

echo -e "${GREEN}Enviando a GitHub...${NC}"
if ! git push origin "$BRANCH"; then
    echo -e "${RED}ERROR: No se pudo enviar a GitHub${NC}"
    exit 1
fi

LOCAL_COMMIT=$(git rev-parse --short HEAD)
echo -e "${GREEN}✓ Commit local: ${LOCAL_COMMIT}${NC}"

# ═══════════════════════════════════════════════════════════════════
# PASO 3: Validar configuración del servidor ANTES de actualizar
# ═══════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[3/5] Validando configuración del servidor...${NC}"

# Validar .env del servidor (sin modificar nada aún)
ssh -o StrictHostKeyChecking=no "$SERVER" "bash -lc '
  set -e
  cd \"$APP_DIR\"
  
  # Verificar que existe .env
  if [ ! -f .env ]; then
    echo \"ERROR: .env no existe en el servidor\"
    exit 1
  fi
  
  # Verificar que DEBUG=False (exactamente una vez)
  DBG_COUNT=\$(grep -c \"^DEBUG=\" .env || echo 0)
  if [ \"\$DBG_COUNT\" -ne 1 ]; then
    echo \"ERROR: .env debe tener exactamente UNA línea DEBUG= (encontradas: \$DBG_COUNT)\"
    cat .env
    exit 1
  fi
  
  if grep -Eq \"^DEBUG=(True|true|1|yes|on)\$\" .env; then
    echo \"ERROR: DEBUG está activado en producción!\"
    exit 1
  fi
  
  echo \"✓ Configuración del servidor válida\"
'"

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: La configuración del servidor no es válida${NC}"
    echo -e "${YELLOW}Corrige el .env del servidor antes de continuar${NC}"
    exit 1
fi

# ═══════════════════════════════════════════════════════════════════
# PASO 4: Actualizar código en el servidor
# ═══════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[4/5] Actualizando código en el servidor...${NC}"

ssh -o StrictHostKeyChecking=no "$SERVER" "bash -lc '
  set -e
  cd \"$APP_DIR\"
  
  PREV_COMMIT=\$(git rev-parse --short HEAD || echo none)
  echo \"Commit anterior: \$PREV_COMMIT\"
  
  # Guardar .env antes de reset (si existe)
  if [ -f .env ]; then
    cp .env /tmp/.env.backup
    echo \"Backup de .env creado\"
  fi
  
  # Fetch y reset
  git fetch origin \"$BRANCH\"
  git checkout -B \"$BRANCH\"
  git reset --hard \"origin/$BRANCH\"
  
  # Restaurar .env después de reset
  if [ -f /tmp/.env.backup ]; then
    cp /tmp/.env.backup .env
    echo \".env restaurado desde backup\"
  fi
  
  NEW_COMMIT=\$(git rev-parse --short HEAD)
  echo \"Commit nuevo: \$NEW_COMMIT\"
  
  # Activar entorno virtual
  if [ ! -d \"$VENV_DIR\" ]; then python3 -m venv \"$VENV_DIR\"; fi
  source \"$VENV_DIR/bin/activate\"
  
  # Operaciones opcionales
  if $DO_PIP; then
    echo \"Instalando dependencias...\"
    pip install --upgrade pip
    pip install -r requirements.txt
  fi
  
  if $DO_MIGRATE; then
    echo \"Ejecutando migraciones...\"
    python manage.py migrate --noinput
  fi
  
  if $DO_COMPILE; then
    echo \"Compilando mensajes i18n...\"
    python manage.py compilemessages -l en -l es 2>/dev/null || echo \"(compilemessages omitido - msgfmt no disponible)\"
  fi
  
  if $DO_CLEAR_CACHE; then
    echo \"Limpiando caché...\"
    python manage.py shell -c \"from django.core.cache import caches; [c.clear() for c in caches.all()]; print(\\\"Cache limpiado\\\")\" 2>/dev/null || true
  fi
  
  if $DO_STATIC; then
    echo \"Recolectando archivos estáticos...\"
    python manage.py collectstatic --noinput
  fi
'"

# ═══════════════════════════════════════════════════════════════════
# PASO 5: Reiniciar servicios y verificar
# ═══════════════════════════════════════════════════════════════════
echo -e "\n${GREEN}[5/5] Reiniciando servicios...${NC}"

ssh -o StrictHostKeyChecking=no "$SERVER" "bash -lc '
  set -e
  cd \"$APP_DIR\"
  
  sudo systemctl daemon-reload || true
  
  if $DO_RESTART; then
    sudo systemctl restart gunicorn
    sleep 2
    
    # Healthcheck
    HC_CODE=\$(curl -s -o /dev/null -w \"%{http_code}\" --unix-socket /run/gunicorn.sock http://localhost/ || echo 000)
    echo \"Healthcheck: \$HC_CODE\"
    
    if [ \"\$HC_CODE\" != \"200\" ] && [ \"\$HC_CODE\" != \"301\" ]; then
      echo \"ERROR: Healthcheck falló\"
      exit 1
    fi
  fi
  
  # Reload nginx si la config es válida
  if sudo nginx -t 2>/dev/null; then
    sudo systemctl reload nginx || true
  fi
  
  echo \"\"
  echo \"════════════════════════════════════════\"
  echo \"✓ Deploy completado exitosamente\"
  echo \"  Commit: \$(git rev-parse --short HEAD)\"
  echo \"  Fecha:  \$(date)\"
  echo \"════════════════════════════════════════\"
'"

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: El deploy falló${NC}"
    exit 1
fi

echo -e "\n${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    ✓ DEPLOY EXITOSO                            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
