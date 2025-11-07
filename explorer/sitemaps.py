from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils.translation import get_language
from explorer.models import Places, RegionOSM

class StaticViewSitemap(Sitemap):
	changefreq = "daily"
	priority = 0.8

	def items(self):
		return ["explorer:home", "explorer:lugares_list"]

	def location(self, item):
		return reverse(item)

class PlacesSitemap(Sitemap):
	changefreq = "weekly"
	priority = 0.6

	def items(self):
		return Places.objects.filter(slug__isnull=False).order_by("-id")

	def location(self, obj):
		return reverse("explorer:lugares_detail", args=[obj.slug])

class ComunasSitemap(Sitemap):
	changefreq = "weekly"
	priority = 0.5

	def items(self):
		return RegionOSM.objects.exclude(slug__isnull=True).exclude(slug="")

	def location(self, obj):
		return reverse("explorer:lugares_por_comuna", args=[obj.slug])
