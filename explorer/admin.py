from django.contrib import admin
from .models import Places
from django.contrib.gis import admin as gis_admin


@admin.register(Places)
class PobladoAdmin(gis_admin.GISModelAdmin):
    list_display = ('nombre', 'tipo',)
    search_fields = ("nombre", "tipo", "direccion")
    
