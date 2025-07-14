# 🔐 Plan de Implementación de Google Auth

## 📋 Resumen
Reemplazar el sistema de autenticación actual por Google OAuth2, permitiendo a los usuarios iniciar sesión con su cuenta de Google.

## 🚀 Pasos de Implementación

### 1. Instalar Dependencias Necesarias

```bash
pip install django-allauth
pip install google-auth
pip install google-auth-oauthlib
pip install google-auth-httplib2
```

Actualizar `requirements.txt`:
```
django-allauth==0.57.0
google-auth==2.23.4
google-auth-oauthlib==1.1.0
google-auth-httplib2==0.1.1
```

### 2. Configurar Google Cloud Console

1. **Crear Proyecto en Google Cloud**
   - Ir a https://console.cloud.google.com/
   - Crear nuevo proyecto o usar existente
   - Nombre sugerido: "ViveMedellin-Auth"

2. **Habilitar Google+ API**
   - En el menú: APIs y servicios → Biblioteca
   - Buscar "Google+ API"
   - Habilitar la API

3. **Crear Credenciales OAuth 2.0**
   - APIs y servicios → Credenciales
   - Crear credenciales → ID de cliente OAuth
   - Tipo de aplicación: Aplicación web
   - Nombre: "ViveMedellin OAuth"
   
4. **Configurar URIs**
   - URIs de redirección autorizadas:
     ```
     http://localhost:8000/accounts/google/login/callback/
     http://127.0.0.1:8000/accounts/google/login/callback/
     https://tudominio.com/accounts/google/login/callback/
     ```
   - Guardar Client ID y Client Secret

### 3. Configurar Django Settings

#### Actualizar `settings.py`:

```python
# Agregar a INSTALLED_APPS
INSTALLED_APPS = [
    # ... apps existentes ...
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    # ... resto de apps ...
]

# Agregar después de MIDDLEWARE
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Configuración de django-allauth
SITE_ID = 1

# Configuración de cuenta
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_VERIFICATION = 'optional'

# Configuración de login
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Solo permitir login con Google
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'OAUTH_PKCE_ENABLED': True,
    }
}

# Deshabilitar signup regular (solo Google)
ACCOUNT_SIGNUP_DISABLED = True
```

#### Agregar a `.env`:
```
GOOGLE_OAUTH_CLIENT_ID='tu-client-id.apps.googleusercontent.com'
GOOGLE_OAUTH_CLIENT_SECRET='tu-client-secret'
```

### 4. Actualizar URLs

#### En `Medellin/urls.py`:
```python
urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),  # Agregar esta línea
    # ... resto de URLs ...
]
```

### 5. Migrar Base de Datos

```bash
python manage.py migrate
```

### 6. Configurar el Site en Admin

```bash
python manage.py shell
```

```python
from django.contrib.sites.models import Site
site = Site.objects.get(id=1)
site.domain = 'localhost:8000'  # o tu dominio
site.name = 'ViveMedellín'
site.save()
```

### 7. Agregar Social Application en Admin

1. Ir a `/admin/`
2. Social applications → Add
3. Provider: Google
4. Name: Google OAuth
5. Client id: (tu client ID)
6. Secret key: (tu client secret)
7. Sites: Seleccionar tu site

### 8. Actualizar Templates

#### Nuevo botón de login (`login_google.html`):
```html
{% load socialaccount %}

<a href="{% provider_login_url 'google' %}" class="btn btn-light border w-100 py-3 d-flex align-items-center justify-content-center">
    <img src="https://www.google.com/favicon.ico" alt="Google" width="20" class="me-2">
    <span>Continuar con Google</span>
</a>
```

#### Actualizar navbar en `base.html`:
```html
{% if user.is_authenticated %}
    <div class="dropdown">
        <button class="btn btn-gradient btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown">
            {% if user.socialaccount_set.all.0.get_avatar_url %}
                <img src="{{ user.socialaccount_set.all.0.get_avatar_url }}" 
                     alt="Avatar" class="rounded-circle me-2" width="24">
            {% else %}
                <i class="bi bi-person-circle me-1"></i>
            {% endif %}
            {{ user.get_full_name|default:user.email|truncatechars:15 }}
        </button>
        <!-- ... resto del dropdown ... -->
    </div>
{% else %}
    <a href="{% url 'account_login' %}" class="btn btn-gradient btn-sm">
        <i class="bi bi-google me-1"></i> Iniciar sesión
    </a>
{% endif %}
```

### 9. Crear Páginas de Login/Logout Personalizadas

#### `templates/account/login.html`:
```html
{% extends "base.html" %}
{% load socialaccount %}

{% block content %}
<section class="min-vh-100 d-flex align-items-center py-5">
    <div class="container">
        <div class="row justify-content-center">
            <div class="col-md-5 col-lg-4">
                <div class="card shadow-lg border-0 rounded-4">
                    <div class="card-body p-5">
                        <div class="text-center mb-4">
                            <i class="bi bi-geo-alt-fill display-4 text-gradient"></i>
                            <h3 class="mt-3">Bienvenido a ViveMedellín</h3>
                            <p class="text-muted">Inicia sesión para continuar</p>
                        </div>
                        
                        <a href="{% provider_login_url 'google' %}" 
                           class="btn btn-light border w-100 py-3 d-flex align-items-center justify-content-center">
                            <img src="https://www.google.com/favicon.ico" alt="Google" width="20" class="me-2">
                            <span>Continuar con Google</span>
                        </a>
                        
                        <p class="text-center text-muted small mt-4 mb-0">
                            Al continuar, aceptas nuestros términos y condiciones
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</section>
{% endblock %}
```

### 10. Migrar Usuarios Existentes

Si tienes usuarios existentes, crear comando de gestión:

```python
# explorer/management/commands/migrate_to_google_auth.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialAccount

User = get_user_model()

class Command(BaseCommand):
    help = 'Prepara usuarios existentes para Google Auth'

    def handle(self, *args, **options):
        users = User.objects.all()
        for user in users:
            # Asegurar que el email está configurado
            if not user.email:
                self.stdout.write(
                    self.style.WARNING(
                        f'Usuario {user.username} no tiene email'
                    )
                )
            # Marcar usuarios para que actualicen su auth
            user.set_unusable_password()
            user.save()
        
        self.stdout.write(
            self.style.SUCCESS('Usuarios preparados para Google Auth')
        )
```

### 11. Signals para Personalizar el Proceso

```python
# explorer/signals.py
from allauth.socialaccount.signals import pre_social_login
from django.dispatch import receiver

@receiver(pre_social_login)
def link_to_local_user(sender, request, sociallogin, **kwargs):
    """
    Vincula automáticamente cuentas de Google con usuarios 
    existentes basándose en el email
    """
    email = sociallogin.account.extra_data.get('email')
    if email:
        try:
            user = User.objects.get(email=email)
            sociallogin.connect(request, user)
        except User.DoesNotExist:
            pass
```

### 12. Configuración de Producción

#### Variables de entorno en producción:
```bash
GOOGLE_OAUTH_CLIENT_ID='production-client-id'
GOOGLE_OAUTH_CLIENT_SECRET='production-secret'
ALLOWED_HOSTS='tudominio.com,www.tudominio.com'
```

#### Actualizar URIs en Google Console:
- Agregar dominio de producción
- Verificar dominio si es necesario

## 🔒 Seguridad

1. **Nunca commitear credenciales**
   - Usar variables de entorno
   - Agregar a `.gitignore`

2. **HTTPS obligatorio en producción**
   ```python
   if not DEBUG:
       SECURE_SSL_REDIRECT = True
       SESSION_COOKIE_SECURE = True
       CSRF_COOKIE_SECURE = True
   ```

3. **Limitar dominios de email (opcional)**
   ```python
   SOCIALACCOUNT_ADAPTER = 'myapp.adapters.CustomSocialAccountAdapter'
   ```

## 📊 Ventajas de este Approach

1. ✅ **Sin gestión de contraseñas**
2. ✅ **Login más rápido** (un click)
3. ✅ **Mayor seguridad** (2FA de Google)
4. ✅ **Menos código que mantener**
5. ✅ **Información del perfil** automática
6. ✅ **Avatar del usuario** gratis

## 🚨 Consideraciones

1. **Dependencia de Google**
   - Usuarios necesitan cuenta Google
   - Si Google cae, no hay login

2. **Privacidad**
   - Google sabe quién usa tu app
   - Cumplir con GDPR/privacidad

3. **Límites de API**
   - Google tiene cuotas gratuitas generosas
   - Monitorear uso

## 🎯 Próximos Pasos Opcionales

1. **Agregar más proveedores**
   - Facebook Login
   - GitHub
   - Twitter

2. **Personalizar perfil**
   - Guardar foto de Google
   - Sincronizar nombre

3. **Analytics**
   - Track de logins
   - Origen de usuarios

## 🧪 Testing

```python
# Probar login
python manage.py runserver
# Visitar http://localhost:8000/accounts/login/

# Verificar en shell
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> User.objects.filter(socialaccount__provider='google').count()
```

## 📝 Checklist de Implementación

- [ ] Instalar paquetes
- [ ] Configurar Google Cloud Console
- [ ] Actualizar settings.py
- [ ] Agregar URLs
- [ ] Ejecutar migraciones
- [ ] Configurar Site en admin
- [ ] Agregar Social Application
- [ ] Actualizar templates
- [ ] Probar login local
- [ ] Configurar producción
- [ ] Probar en producción

¡Con esto tendrás Google Auth funcionando en tu proyecto! 