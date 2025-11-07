from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from django.views.i18n import JavaScriptCatalog
from django.contrib.sitemaps.views import sitemap
from explorer.sitemaps import StaticViewSitemap, PlacesSitemap, ComunasSitemap
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    # utilidades de i18n
    path('i18n/', include('django.conf.urls.i18n')),
    path('sitemap.xml', sitemap, {
        'sitemaps': {
            'static': StaticViewSitemap,
            'places': PlacesSitemap,
            'comunas': ComunasSitemap,
        }
    }, name='django.contrib.sitemaps.views.sitemap'),
]

urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    # Catálogo JS por idioma (sirve /en/jsi18n/ en inglés)
    path('jsi18n/', JavaScriptCatalog.as_view(domain='djangojs', packages=['explorer']), name='javascript-catalog'),
    # Explorer app (prefija /en/ para inglés; español queda sin prefijo)
    path('', include(('explorer.urls', 'explorer'))),
    prefix_default_language=False,
)

# Para servir archivos multimedia en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
