from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls.i18n import i18n_patterns
from django.views.i18n import JavaScriptCatalog
from django.contrib.sitemaps.views import index as sitemap_index, sitemap
from django.views.generic import RedirectView, TemplateView
from explorer.sitemaps import (
    StaticViewSitemap, PlacesSitemap, ComunasSitemap,
    ImagesSitemap, PlacesSitemapEN, StaticViewSitemapEN
)
from explorer import views as explorer_views
from django.conf import settings
from django.conf.urls.static import static


# Sitemaps organizados
sitemaps = {
    'static': StaticViewSitemap,
    'static-en': StaticViewSitemapEN,
    'places': PlacesSitemap,
    'places-en': PlacesSitemapEN,
    'comunas': ComunasSitemap,
    'images': ImagesSitemap,
}

urlpatterns = [
    # robots.txt
    path('robots.txt', TemplateView.as_view(
        template_name='robots.txt',
        content_type='text/plain'
    ), name='robots_txt'),
    
    # utilidades de i18n
    path('i18n/', include('django.conf.urls.i18n')),
    
    # Sitemaps - usando índice paginado para mejor rendimiento con muchas URLs
    path('sitemap.xml', sitemap_index, {'sitemaps': sitemaps},
         name='django.contrib.sitemaps.views.index'),
    path('sitemap-<section>.xml', sitemap, {'sitemaps': sitemaps},
         name='django.contrib.sitemaps.views.sitemap'),

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

    # Redirect de compatibilidad en español (URLs antiguas)
    re_path(
        r'^lugar/(?P<slug>[\w-]+)/reviews/$',
        RedirectView.as_view(
            url='/lugar/%(slug)s/reseñas/',
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
