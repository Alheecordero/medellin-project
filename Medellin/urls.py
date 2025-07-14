from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),

    # Incluye el namespace correctamente
    path('usuarios/', include(('usuarios.urls', 'usuarios'), namespace='usuarios')),  

    # Incluye explorer con namespace también (si lo usas en templates como explorer:algo)
    path('', include(('explorer.urls', 'explorer'))),

    path('__debug__/', include('debug_toolbar.urls')),
    
]

# Para servir archivos multimedia en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
