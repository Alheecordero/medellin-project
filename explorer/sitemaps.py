from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.db.models import Q
from explorer.models import Places, RegionOSM, Foto


class StaticViewSitemap(Sitemap):
    """Sitemap para páginas estáticas principales."""
    changefreq = "daily"
    priority = 1.0

    def items(self):
        return ["explorer:home", "explorer:lugares_list", "explorer:about_es"]

    def location(self, item):
        return reverse(item)


class PlacesSitemap(Sitemap):
    """Sitemap para lugares individuales con alta prioridad para lugares destacados."""
    changefreq = "weekly"
    priority = 0.8
    limit = 2000  # Límite por sitemap (reducido para evitar timeout)

    def items(self):
        return Places.objects.filter(
            slug__isnull=False
        ).exclude(
            slug=""
        ).filter(
            Q(rating__gte=2.0) | Q(rating__isnull=True)
        ).order_by("-es_destacado", "-rating", "-id")[:self.limit]

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
        return obj.updated_at if hasattr(obj, 'updated_at') else None


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


class ImagesSitemap(Sitemap):
    """Sitemap de imágenes para Google Images."""
    changefreq = "monthly"
    priority = 0.5
    limit = 2000  # Reducido para evitar timeout

    def items(self):
        return Foto.objects.exclude(
            Q(imagen__isnull=True) | Q(imagen="")
        ).select_related("lugar").filter(
            lugar__slug__isnull=False
        ).order_by("-id")[:self.limit]

    def location(self, obj):
        if obj.lugar and obj.lugar.slug:
            return reverse("explorer:lugares_detail", args=[obj.lugar.slug])
        return "/"


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
        return ["/en/", "/en/places/", "/en/about-us/"]

    def location(self, item):
        return item
