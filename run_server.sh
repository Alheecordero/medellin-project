#!/bin/bash

# Activar el entorno virtual
source /home/alhee/Desktop/DJ5_BOOK/Geodjango/geoapp/Poblado_medellin_app/med/bin/activate

# Crear un archivo settings_dev.py temporal
cat > Medellin/settings_dev.py << EOF
from .settings import *

# Deshabilitar dependencias problemáticas
INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in ['easy_thumbnails', 'storages']]

# Configurar almacenamiento de archivos para desarrollo
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Debug toolbar
DEBUG_TOOLBAR = False
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'django_extensions']

# Configuración de caché
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,  # 5 minutos
    }
}

# Configuración de templates
TEMPLATES[0]['OPTIONS']['debug'] = True

# Configuración de logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'explorer': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
EOF

# Configurar el entorno para usar settings_dev.py
export DJANGO_SETTINGS_MODULE=Medellin.settings_dev

# Ejecutar el servidor
cd /home/alhee/Desktop/Medellin
echo "Iniciando servidor de desarrollo..."
python3 manage.py runserver 