# Configuración para Producción - ViveMedellín

## 1. Crear archivo .env en el servidor

En el servidor, crear el archivo `/var/www/medellin-project/.env` con el siguiente contenido:

```bash
# Django settings
SECRET_KEY=django-insecure-vc#z)l3j98nx4g34y*3!q@#medellin2024
DEBUG=False
ALLOWED_HOSTS=5.161.85.163,vivemedellin.co,www.vivemedellin.co

# Base de datos (credenciales reales)
DATABASE_URL=postgres://Alhee:Alhee166817502@medellin-db.c94u0qig8wiy.us-east-2.rds.amazonaws.com:5432/colombia-osm

# Google Cloud Storage
USE_GCS=False
GS_BUCKET_NAME=vivemedellin-bucket
GS_CREDENTIALS_PATH=vivemedellin-6018549fb373.json

# Google Maps API (API key real)
GOOGLE_API_KEY=AIzaSyAyepBu9y5XMYUWsfkxClZ1W2kcLdvIfow

# Redis cache
REDIS_URL=redis://localhost:6379/1
```

## 2. Comandos a ejecutar en el servidor

```bash
# 1. Conectarse al servidor
ssh root@5.161.85.163

# 2. Ir al directorio del proyecto
cd /var/www/medellin-project

# 3. Activar el entorno virtual
source venv/bin/activate

# 4. Hacer pull de los cambios
git pull origin main

# 5. Instalar dependencias actualizadas
pip install -r requirements.txt

# 6. Crear el archivo .env
cat > .env << 'EOF'
# Django settings
SECRET_KEY=django-insecure-vc#z)l3j98nx4g34y*3!q@#medellin2024
DEBUG=False
ALLOWED_HOSTS=5.161.85.163,vivemedellin.co,www.vivemedellin.co

# Base de datos (credenciales reales)
DATABASE_URL=postgres://Alhee:Alhee166817502@medellin-db.c94u0qig8wiy.us-east-2.rds.amazonaws.com:5432/colombia-osm

# Google Cloud Storage
USE_GCS=False
GS_BUCKET_NAME=vivemedellin-bucket
GS_CREDENTIALS_PATH=vivemedellin-6018549fb373.json

# Google Maps API (API key real)
GOOGLE_API_KEY=AIzaSyAyepBu9y5XMYUWsfkxClZ1W2kcLdvIfow

# Redis cache
REDIS_URL=redis://localhost:6379/1
EOF

# 7. Asegurar permisos del archivo .env
chmod 600 .env

# 8. Ejecutar migraciones (ya están marcadas como aplicadas)
python manage.py migrate

# 9. Colectar archivos estáticos
python manage.py collectstatic --noinput

# 10. Reiniciar servicios
sudo systemctl restart gunicorn
sudo systemctl restart nginx

# 11. Verificar que todo funcione
sudo systemctl status gunicorn
sudo systemctl status nginx
```

## 3. Verificación

1. Visitar https://vivemedellin.co
2. Verificar que NO aparezca el Django Debug Toolbar
3. Verificar que las páginas carguen correctamente
4. Revisar logs si hay errores:
   ```bash
   sudo journalctl -u gunicorn -f
   ```

## 4. Notas importantes

- La base de datos está alojada en AWS RDS (medellin-db.c94u0qig8wiy.us-east-2.rds.amazonaws.com)
- El archivo `.env` NUNCA debe subirse a git
- Las credenciales son las mismas que usas en local 