# Instrucciones para Actualizar Servidor de Producción

## 1. Conectarse al Servidor

```bash
ssh usuario@tu-servidor.com
cd /ruta/a/tu/proyecto
```

## 2. Hacer Pull de los Cambios

```bash
# Activar entorno virtual
source venv/bin/activate  # o el nombre de tu entorno

# Hacer pull de los cambios
git pull origin main
```

## 3. Instalar Dependencias (si hay nuevas)

```bash
pip install -r requirements.txt
```

## 4. Collectstatic para los Nuevos Archivos CSS/JS

```bash
python manage.py collectstatic --noinput
```

## 5. Configurar Variables de Entorno

Asegúrate de que `.env` tenga estas variables:

```bash
DEBUG=False
SHOW_DEBUG_TOOLBAR=False
USE_GCS_IN_DEBUG=False

# Redis (muy importante para el caché)
REDIS_URL=redis://127.0.0.1:6379/1

# Google Cloud Storage
GS_BUCKET_NAME=vivemedellin-bucket
GS_CREDENTIALS_PATH=vivemedellin-fdc8cbb3b441.json

# Base de datos
DATABASE_URL=postgis://usuario:password@host:5432/nombre_db
```

## 6. Limpiar Caché (Importante)

```bash
python manage.py shell
>>> from django.core.cache import cache
>>> cache.clear()
>>> exit()
```

## 7. Pre-calentar el Caché

```bash
# Ejecutar este script para pre-cargar el caché
python manage.py shell << EOF
from explorer.views import home_view
from django.test import RequestFactory
factory = RequestFactory()
request = factory.get('/')
home_view(request)
print("✅ Caché pre-calentado")
EOF
```

## 8. Reiniciar Servicios

```bash
# Si usas Gunicorn
sudo systemctl restart gunicorn

# Si usas supervisor
sudo supervisorctl restart tu-proyecto

# Reiniciar Nginx
sudo systemctl restart nginx

# Verificar Redis
redis-cli ping
# Debe responder: PONG
```

## 9. Verificar el Sitio

1. Visita tu sitio web
2. La primera carga puede tardar 5-10 segundos (generando caché)
3. Las siguientes cargas deben ser <100ms

## 10. Monitoreo

```bash
# Ver logs de Gunicorn
sudo journalctl -u gunicorn -f

# Ver logs de Nginx
sudo tail -f /var/log/nginx/error.log

# Monitorear Redis
redis-cli monitor
```

## Cambios Principales en Esta Actualización

1. **Optimizaciones de Rendimiento**
   - Sistema de caché agresivo implementado
   - Consultas optimizadas con prefetch_related
   - Context processor con caché de 24 horas

2. **Nuevo Diseño Frontend**
   - CSS moderno en `explorer/static/css/style.css`
   - JavaScript optimizado en `explorer/static/js/optimizations.js`
   - Lazy loading de imágenes
   - Diseño responsive mejorado

3. **Configuraciones**
   - Debug Toolbar desactivado en producción
   - Compresión GZip activada
   - Sesiones en caché

## Troubleshooting

### Si el sitio está lento:

1. Verificar que Redis esté funcionando:
   ```bash
   redis-cli ping
   ```

2. Verificar el caché:
   ```bash
   python manage.py shell
   >>> from django.core.cache import cache
   >>> cache.get('home_view_data_v2')  # Debe retornar datos
   ```

3. Limpiar y regenerar caché si es necesario

### Si hay errores 500:

1. Verificar logs de Gunicorn
2. Ejecutar `python manage.py check`
3. Verificar permisos en archivos estáticos

## Rendimiento Esperado

- **Home**: <100ms (con caché)
- **Lista lugares**: <200ms (con caché)
- **Mapa**: <300ms (con caché)

¡Éxito con la actualización! 🚀 