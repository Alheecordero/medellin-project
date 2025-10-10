## Informe de configuración y estado del servidor (Medellin)

### 1) Resumen ejecutivo
- Estado: operativo. Búsqueda semántica (Vertex + pgvector) responde con resultados.
- Causa raíz del incidente: el servicio usaba una key antigua de la cuenta de servicio; al sustituir por la key nueva activa y reiniciar, la API de Vertex comenzó a emitir embeddings correctamente.

### 2) Stack y despliegue
- Framework: Django 5.2.x, PostgreSQL/PostGIS, Redis (caché), Nginx + gunicorn.
- Despliegue: systemd (gunicorn) + socket unix; Nginx termina TLS (80→301→443). Script auxiliar: `push_deploy.sh`.

### 3) Configuración Django (resaltado)
- Context processor expone `settings.GOOGLE_ANALYTICS_ID` a templates.
- GA en templates: `explorer/templates/base.html` inserta gtag si hay `GOOGLE_ANALYTICS_ID`.
- Variables de entorno: `.env` en el servidor; `settings.py` prioriza la última ocurrencia para evitar valores viejos.

### 4) Google Analytics
- Variable: `GOOGLE_ANALYTICS_ID`.
- Estado: configurado (ID de medición GA4). El snippet se inyecta condicionalmente en `base.html`.

### 5) Búsqueda semántica (Vertex AI + pgvector)
- Proveedor: Vertex AI únicamente (sin API key de Generative AI).
- Modelo: `gemini-embedding-001` con `output_dimensionality=768`.
- Ranking: SQL con operador pgvector `<=>` sobre el campo `embedding` (768 dims), orden `-score`.
- Endpoints:
  - Página: `/semantic-search/`
  - API JSON: `/api/semantic-search/` (usar slash final para evitar 301 de Nginx).

### 6) Credenciales Vertex AI (producción)
- Ruta activa (gunicorn): `/var/www/medellin-project/vivemedellin-fdc8cbb3b441.json`
- Cuenta de servicio: `vertex-express@vivemedellin.iam.gserviceaccount.com`
- Proyecto: `vivemedellin`
- Estado: sustituido por la key nueva y reiniciado el servicio.

### 7) Nginx
- VirtualHost:
  - `server_name` = `vivemedellin.co` y `www.vivemedellin.co`.
  - `listen 80` → redirección 301 a `https://$host$request_uri`.
  - `listen 443 ssl` con certificados de Let’s Encrypt.

### 8) Gunicorn (systemd)
- Unidad: `gunicorn.service` (3 workers; socket `/run/gunicorn.sock`).
- Environment (override):
  - `GOOGLE_APPLICATION_CREDENTIALS=/var/www/medellin-project/vivemedellin-fdc8cbb3b441.json`
  - `GOOGLE_CLOUD_PROJECT=vivemedellin`

### 9) Salud y verificación (última ejecución)
- `GET /` → 200 (TLS OK)
- `GET /api/semantic-search/?q=arepa` → `{"success": true, "total": N, ...}` (devuelve resultados)

### 10) Riesgos y recomendaciones
- Mantener una sola key activa por cuenta de servicio; borrar claves antiguas para evitar `invalid_grant` por firmas no reconocidas.
- Monitorizar salud tras despliegue: comprobar 200/301 y un `GET /api/semantic-search/?q=ping` que valide embeddings.
- En `.env` de producción: evitar duplicados (usar solo una ocurrencia por variable crítica: `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `GOOGLE_ANALYTICS_ID`).
- Confirmar `DEBUG=False` en producción y dominios en `ALLOWED_HOSTS`.
- Rotación periódica de credenciales y verificación de NTP (reloj sincronizado) para evitar errores de firma.

### 11) Procedimiento de recuperación (resumen)
1. Subir key JSON descargada de GCP (sin editar) a la ruta activa del servicio.
2. `chmod 600` y `chown root:www-data` sobre la key.
3. `systemctl restart gunicorn` y prueba de `/api/semantic-search/`.

---
Este informe refleja el estado tras la sustitución de la credencial y la validación de la búsqueda semántica en producción.


