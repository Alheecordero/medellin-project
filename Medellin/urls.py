from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls.i18n import i18n_patterns
from django.views.i18n import JavaScriptCatalog
from django.contrib.sitemaps.views import sitemap
from django.views.generic import RedirectView
from explorer.sitemaps import StaticViewSitemap, PlacesSitemap, ComunasSitemap
from explorer import views as explorer_views
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

    # Redirects antiguos SOLO para inglés (compatibilidad con URLs viejas)
    re_path(
        r'^en/lugares/$',
        RedirectView.as_view(url='/en/places/', permanent=True)
    ),
    re_path(
        r'^en/lugares/(?P<comuna_slug>[\w-]+)/$',
        RedirectView.as_view(
            url='/en/places/%(comuna_slug)s/',
            permanent=True
        )
    ),
    re_path(
        r'^en/lugar/(?P<slug>[\w-]+)/$',
        RedirectView.as_view(
            url='/en/place/%(slug)s/',
            permanent=True
        )
    ),
    re_path(
        r'^en/lugar/(?P<slug>[\w-]+)/reviews/$',
        RedirectView.as_view(
            url='/en/place/%(slug)s/reviews/',
            permanent=True
        )
    ),
]

urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    # Catálogo JS por idioma (sirve /en/jsi18n/ en inglés)
    path('jsi18n/', JavaScriptCatalog.as_view(domain='djangojs', packages=['explorer']), name='javascript-catalog'),

    # Rutas principales de Explorer sin namespace para compatibilidad con templates antiguos
    # Nota: también están registradas dentro de explorer.urls con namespace 'explorer'
    path('nosotros/', explorer_views.about, name='about_es'),
    path('about-us/', explorer_views.about, name='about'),

    # Explorer app (prefija /en/ para inglés; español queda sin prefijo)
    path('', include(('explorer.urls', 'explorer'))),
    prefix_default_language=False,
)

# Para servir archivos multimedia en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
