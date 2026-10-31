from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls.i18n import i18n_patterns
from django.views.i18n import JavaScriptCatalog
from django.contrib.sitemaps.views import index as sitemap_index, sitemap
from django.views.generic import RedirectView, TemplateView
from explorer.sitemaps import (
    CentrosComercialesSitemap, CentrosComercialesSitemapEN,
    ComunasSitemap, ComunasSitemapEN, GuidesSitemap, GuidesSitemapEN,
    PlacesSitemap, PlacesSitemapEN, StaticViewSitemap, StaticViewSitemapEN,
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
    'comunas-en': ComunasSitemapEN,
    'guides': GuidesSitemap,
    'guides-en': GuidesSitemapEN,
    'malls': CentrosComercialesSitemap,
    'malls-en': CentrosComercialesSitemapEN,
}

urlpatterns = [
    # robots.txt
    path('robots.txt', TemplateView.as_view(
        template_name='robots.txt',
        content_type='text/plain'
    ), name='robots_txt'),

    # ads.txt (Google AdSense)
    path('ads.txt', TemplateView.as_view(
        template_name='ads.txt',
        content_type='text/plain'
    ), name='ads_txt'),

    # Bing Webmaster Tools
    path('BingSiteAuth.xml', TemplateView.as_view(
        template_name='BingSiteAuth.xml',
        content_type='application/xml'
    ), name='bing_site_auth'),

    # utilidades de i18n
    path('i18n/', include('django.conf.urls.i18n')),

    # Sitemaps - índice paginado para muchas URLs
    path('sitemap.xml', sitemap_index, {'sitemaps': sitemaps},
         name='django.contrib.sitemaps.views.index'),
    path('sitemap-<section>.xml', sitemap, {'sitemaps': sitemaps},
         name='django.contrib.sitemaps.views.sitemap'),

    # ── SEO: paths EN sin prefijo /en/ (GSC ~13k 404 en /place/…) ──────────
    # Causa: hreflang con slice incorrecto publicó /place/foo/ como alternate.
    # Estos 301 consolidan a la URL canónica /en/place/foo/.
    re_path(
        r'^place/(?P<slug>[\w-]+)/reviews/$',
        RedirectView.as_view(url='/en/place/%(slug)s/reviews/', permanent=True),
    ),
    re_path(
        r'^place/(?P<slug>[\w-]+)/reseñas/$',
        RedirectView.as_view(url='/en/place/%(slug)s/reviews/', permanent=True),
    ),
    re_path(
        r'^place/(?P<slug>[\w-]+)/$',
        RedirectView.as_view(url='/en/place/%(slug)s/', permanent=True),
    ),
    re_path(
        r'^places/$',
        RedirectView.as_view(url='/en/places/', permanent=True),
    ),
    re_path(
        r'^places/(?P<comuna_slug>[\w-]+)/$',
        RedirectView.as_view(url='/en/places/%(comuna_slug)s/', permanent=True),
    ),
    re_path(
        r'^guides/$',
        RedirectView.as_view(url='/en/guides/', permanent=True),
    ),
    re_path(
        r'^guides/(?P<slug>[\w-]+)/$',
        RedirectView.as_view(url='/en/guides/%(slug)s/', permanent=True),
    ),

    # Legacy / idioma mezclado bajo /en/
    re_path(
        r'^en/lugares/$',
        RedirectView.as_view(url='/en/places/', permanent=True),
    ),
    re_path(
        r'^en/lugares/(?P<comuna_slug>[\w-]+)/$',
        RedirectView.as_view(url='/en/places/%(comuna_slug)s/', permanent=True),
    ),
    re_path(
        r'^en/lugar/(?P<slug>[\w-]+)/$',
        RedirectView.as_view(url='/en/place/%(slug)s/', permanent=True),
    ),
    re_path(
        r'^en/lugar/(?P<slug>[\w-]+)/reviews/$',
        RedirectView.as_view(url='/en/place/%(slug)s/reviews/', permanent=True),
    ),
    re_path(
        r'^en/lugar/(?P<slug>[\w-]+)/reseñas/$',
        RedirectView.as_view(url='/en/place/%(slug)s/reviews/', permanent=True),
    ),
    re_path(
        r'^en/place/(?P<slug>[\w-]+)/reseñas/$',
        RedirectView.as_view(url='/en/place/%(slug)s/reviews/', permanent=True),
    ),
    re_path(
        r'^en/guias/$',
        RedirectView.as_view(url='/en/guides/', permanent=True),
    ),
    re_path(
        r'^en/guias/(?P<slug>[\w-]+)/$',
        RedirectView.as_view(url='/en/guides/%(slug)s/', permanent=True),
    ),
    re_path(
        r'^en/nosotros/$',
        RedirectView.as_view(url='/en/about-us/', permanent=True),
    ),

    # Español: reviews en inglés → reseñas
    re_path(
        r'^lugar/(?P<slug>[\w-]+)/reviews/$',
        RedirectView.as_view(url='/lugar/%(slug)s/reseñas/', permanent=True),
    ),
]

urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    path(
        'jsi18n/',
        JavaScriptCatalog.as_view(domain='djangojs', packages=['explorer']),
        name='javascript-catalog',
    ),

    path('nosotros/', explorer_views.about, name='about_es'),
    path('about-us/', explorer_views.about, name='about'),

    path('', include(('explorer.urls', 'explorer'))),
    prefix_default_language=False,
)

if settings.DEBUG:
    from explorer import views_staging_local as staging_local

    urlpatterns += [
        path(
            "local/staging-details/",
            staging_local.staging_details_list,
            name="staging_local_list",
        ),
        path(
            "local/staging-details/<str:place_id>/",
            staging_local.staging_details_detail,
            name="staging_local_detail",
        ),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
