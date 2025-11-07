# Configuración local - NO SUBIR A GIT
# Este archivo sobrescribe las configuraciones de settings.py

from pathlib import Path
import os

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Configuraciones básicas
DEBUG = True
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
SECRET_KEY = 'django-insecure-dev-key-only-for-local-development'

# API Keys
GOOGLE_API_KEY = 'AIzaSyAyepBu9y5XMYUWsfkxClZ1W2kcLdvIfow'  # Reemplazar con tu key real si la necesitas
GOOGLE_ANALYTICS_ID = 'G-7T6TJ7020J'

# Base de datos de desarrollo (SQLite para pruebas locales rápidas)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Cache local simple (sin Redis)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,
        'MAX_ENTRIES': 100,
    }
}

# Google Cloud Storage - Configurado pero no usado en desarrollo local
GS_BUCKET_NAME = 'vivemedellin-bucket'  # Necesario para evitar errores
# GS_CREDENTIALS = service_account.Credentials.from_service_account_file(
#     os.path.join(BASE_DIR, 'vivemedellin-fdc8cbb3b441.json')
# )

# Para desarrollo local, usar almacenamiento de archivos estáticos local
# NOTA: Comentado para permitir usar GCS cuando USE_GCS_IN_DEBUG=True
# STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
# DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Configuración de archivos estáticos
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / "Medellin" / "static",
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Archivos media
# NOTA: Comentado para permitir usar GCS cuando USE_GCS_IN_DEBUG=True
# MEDIA_URL = '/media/'
# MEDIA_ROOT = BASE_DIR / 'media'

# Activar debug toolbar
DEBUG_TOOLBAR = True

# Remover storages de INSTALLED_APPS si no está instalado
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
    'easy_thumbnails',  # Para manejo de thumbnails
    'rest_framework',
    'explorer',
    'storages',
    'django_extensions',
    # 'debug_toolbar',  # Comentado temporalmente
]

# Middleware con debug_toolbar
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 'debug_toolbar.middleware.DebugToolbarMiddleware',  # Comentado temporalmente
]

# IPs internas para debug toolbar
INTERNAL_IPS = [
    '127.0.0.1',
]

# Configuración adicional para Django Debug Toolbar
DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda request: DEBUG,
    'SHOW_COLLAPSED': True,
    'SQL_WARNING_THRESHOLD': 100,  # Advertir si una consulta toma más de 100ms
} 