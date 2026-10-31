from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.db.models import Max, Q
from explorer.models import CuratedGuide, Places, RegionOSM


class StaticViewSitemap(Sitemap):
    """Sitemap para páginas estáticas principales."""
    changefreq = "daily"
    priority = 1.0

    def items(self):
        return [
            "explorer:home",
            "explorer:lugares_list",
            "explorer:guias_index",
            "explorer:about_es",
            "explorer:privacy_policy",
            "explorer:terms",
            "explorer:contact",
        ]

    def location(self, item):
        return reverse(item)


class PlacesSitemap(Sitemap):
    """Sitemap para lugares individuales con alta prioridad para lugares destacados.

    Django automáticamente pagina si hay más URLs que el límite.
    El orden prioriza lugares destacados y con mejor rating primero.

    Solo fichas indexables (ver PlacesQuerySet.indexables): el resto sigue
    publicado pero no se anuncia, para no gastar el crawl budget en thin pages.
    """
    changefreq = "weekly"
    priority = 0.8
    limit = 5000  # Límite por página de sitemap para mejor rendimiento

    def items(self):
        return Places.objects.indexables().only(
            'slug', 'es_destacado', 'rating', 'id', 'fecha_actualizacion', 'contenido_actualizado'
        ).order_by("-es_destacado", "-rating", "-id")

    def location(self, obj):
        return reverse("explorer:lugares_detail", args=[obj.slug])

    def priority(self, obj):
        # Prioridad dinámica basada en rating y destacado
        if obj.es_destacado:
            return 0.9
        if obj.rating and obj.rating >= 4.5:
            return 0.85
        if obj.rating and obj.rating >= 4.0:
            return 0.8
        return 0.7

    def lastmod(self, obj):
        return obj.contenido_actualizado or obj.fecha_actualizacion

    def get_latest_lastmod(self):
        # El índice lo pide por sección; el de Django recorre todas las fichas en Python.
        return self.items().aggregate(latest=Max("contenido_actualizado"))["latest"]


class ComunasSitemap(Sitemap):
    """Sitemap para páginas de comunas/regiones."""
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return RegionOSM.objects.exclude(
            slug__isnull=True
        ).exclude(
            slug=""
        ).order_by("name")

    def location(self, obj):
        return reverse("explorer:lugares_por_comuna", args=[obj.slug])


class ComunasSitemapEN(ComunasSitemap):
    """Sitemap para páginas de comunas/regiones en inglés."""

    def location(self, obj):
        return f"/en/places/{obj.slug}/"


class GuidesSitemap(Sitemap):
    """Sitemap de guías editoriales publicadas."""
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return CuratedGuide.objects.filter(publicado=True).only(
            "slug", "fecha_actualizacion"
        ).order_by("-fecha_actualizacion")

    def location(self, obj):
        return reverse("explorer:guia_detail", args=[obj.slug])

    def lastmod(self, obj):
        return obj.fecha_actualizacion

    def get_latest_lastmod(self):
        return self.items().aggregate(latest=Max("fecha_actualizacion"))["latest"]


class GuidesSitemapEN(GuidesSitemap):
    """Sitemap de guías editoriales en inglés."""

    def location(self, obj):
        return f"/en/guides/{obj.slug}/"


# ImagesSitemap eliminado - las imágenes ya están en las páginas de lugares
# y causaba timeout al cargar demasiadas fotos


# Para versión en inglés
class PlacesSitemapEN(PlacesSitemap):
    """Sitemap para lugares en inglés."""
    
    def location(self, obj):
        return f"/en/place/{obj.slug}/"


class StaticViewSitemapEN(Sitemap):
    """Sitemap para páginas estáticas en inglés."""
    changefreq = "daily"
    priority = 1.0

    def items(self):
        return ["/en/", "/en/places/", "/en/guides/", "/en/about-us/"]

    def location(self, item):
        return item
