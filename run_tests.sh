#!/bin/bash

# Activar el entorno virtual
source /home/alhee/Desktop/DJ5_BOOK/Geodjango/geoapp/Poblado_medellin_app/med/bin/activate

# Ir al directorio del proyecto
cd /home/alhee/Desktop/Medellin

# Crear un archivo settings_test.py temporal
cat > Medellin/settings_test.py << EOF
from .settings import *

# Deshabilitar dependencias problemáticas
INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in ['easy_thumbnails', 'storages']]

# Configurar almacenamiento de archivos para pruebas
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Añadir 'testserver' a ALLOWED_HOSTS
ALLOWED_HOSTS += ['testserver']

# Configuración de caché para pruebas
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Deshabilitar debug toolbar para pruebas
DEBUG_TOOLBAR = False
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'debug_toolbar']

# Configurar base de datos en memoria para pruebas más rápidas
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': ':memory:',
#     }
# }
EOF

# Configurar el entorno para usar settings_test.py
export DJANGO_SETTINGS_MODULE=Medellin.settings_test

# Ejecutar las pruebas
echo "Ejecutando pruebas simples..."
python3 test_views_simple.py

echo -e "\n\nEjecutando pruebas completas..."
python3 test_views_comprehensive.py

# Eliminar el archivo settings_test.py
rm Medellin/settings_test.py

echo "Pruebas completadas y configuración restaurada." 