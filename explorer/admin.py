from django.contrib import admin
from .models import Places
from django.contrib.gis.admin import OSMGeoAdmin


@admin.register(Places)
class PobladoAdmin(OSMGeoAdmin):
    list_display = ( str('id'),'nombre', 'tipo',)
    search_fields = ("nombre", "tipo", "direccion")
    
