from django.contrib import admin
from django.contrib.gis import admin as gis_admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Places, Foto, ZonaCubierta, RegionOSM, Initialgrid, TaggedPlace, NewsletterSubscription
import json


class FotoInline(admin.TabularInline):
    model = Foto
    extra = 1
    fields = ('imagen_preview', 'imagen', 'descripcion', 'fecha_subida')
    readonly_fields = ('imagen_preview', 'fecha_subida')
    
    def imagen_preview(self, obj):
        if obj.imagen:
            return format_html(
                '<img src="{}" style="width: 100px; height: 60px; object-fit: cover; border-radius: 4px;" />',
                obj.imagen
            )
        return "Sin imagen"
    imagen_preview.short_description = "Vista previa"


@admin.register(Places)
class PlacesAdmin(gis_admin.GISModelAdmin):
    """Configuración del admin para el modelo Places."""
    gis_widget_kwargs = {
        'attrs': {
            'default_zoom': 12,
            'default_lat': 6.2442,
            'default_lon': -75.5812,
        },
    }
    list_display = ('nombre', 'tipo', 'direccion', 'rating', 'total_reviews', 'comuna', 'es_destacado', 'es_exclusivo', 'tiene_fotos_icon', 'get_tags')
    search_fields = ('nombre', 'direccion', 'tags__name')
    list_filter = ('tipo', 'comuna_osm_id', 'es_destacado', 'es_exclusivo', 'tiene_fotos')
    prepopulated_fields = {'slug': ('nombre',)}
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion', 'tiene_fotos')
    fieldsets = (
        (None, {
            'fields': ('nombre', 'slug', 'tipo', 'direccion', 'ubicacion', 'comuna_osm_id')
        }),
        ('Etiquetas y Destacados', {
            'fields': ('tags', 'es_destacado', 'es_exclusivo', 'tiene_fotos'),
            'description': 'Configura las etiquetas y estados destacados del lugar.',
        }),
        ('Detalles de Google', {
            'classes': ('collapse',),
            'fields': (
                'place_id', 'rating', 'total_reviews', 'abierto_ahora', 'horario_texto', 
                'sitio_web', 'telefono', 'google_maps_uri', 'directions_uri'
            ),
        }),
        ('Características', {
            'classes': ('collapse',),
            'fields': (
                'precio', 'descripcion', 'types', 'areas_google_api', 'takeout', 'dine_in', 'delivery',
                'accepts_credit_cards', 'accepts_debit_cards', 'accepts_cash_only', 'accepts_nfc',
                'wheelchair_accessible_entrance', 'wheelchair_accessible_parking',
                'wheelchair_accessible_restroom', 'wheelchair_accessible_seating',
                'serves_breakfast', 'serves_lunch', 'serves_dinner', 'serves_beer', 'serves_wine',
                'serves_brunch', 'serves_cocktails', 'serves_dessert', 'serves_coffee',
                'good_for_groups', 'good_for_children', 'outdoor_seating', 'menu_for_children',
                'live_music', 'allows_dogs'
            ),
        }),
        ('Búsqueda Semántica', {
            'classes': ('collapse',),
            'fields': ('summary', 'embedding'),
        }),
        ('Reviews Guardadas', {
            'classes': ('collapse',),
            'fields': ('reviews',),
        }),
        ('Metadatos', {
            'fields': ('fecha_creacion', 'fecha_actualizacion', 'google_api_json'),
        }),
    )

    def tiene_fotos_icon(self, obj):
        if obj.tiene_fotos:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')
    tiene_fotos_icon.short_description = "Tiene Fotos"
    tiene_fotos_icon.admin_order_field = 'tiene_fotos'

    def get_tags(self, obj):
        return ", ".join(o.name for o in obj.tags.all())
    get_tags.short_description = "Etiquetas"

@admin.register(Foto)
class FotoAdmin(admin.ModelAdmin):
    """Configuración del admin para el modelo Foto."""
    list_display = ('lugar', 'imagen', 'fecha_subida')
    search_fields = ('lugar__nombre',)
    list_filter = ('fecha_subida',)

@admin.register(ZonaCubierta)
class ZonaCubiertaAdmin(gis_admin.GISModelAdmin):
    """Configuración del admin para Zonas Cubiertas."""
    list_display = ('nombre', 'fecha_creacion')
    search_fields = ('nombre',)
    gis_widget_kwargs = {
        'attrs': {
            'default_zoom': 11,
            'default_lat': 6.2442,
            'default_lon': -75.5812,
        },
    }

@admin.register(RegionOSM)
class RegionOSMAdmin(gis_admin.GISModelAdmin):
    """Configuración del admin para Regiones OSM."""
    list_display = ('osm_id', 'name', 'admin_level', 'ciudad', 'fecha_importacion')
    search_fields = ('name', 'osm_id')
    list_filter = ('admin_level', 'ciudad')
    gis_widget_kwargs = {
        'attrs': {
            'default_zoom': 11,
            'default_lat': 6.2442,
            'default_lon': -75.5812,
            'display_wkt': True,
        },
    }
    
@admin.register(Initialgrid)
class InitialgridAdmin(gis_admin.GISModelAdmin):
    """Configuración del admin para el modelo Initialgrid."""
    list_display = ('id', 'points', 'fecha_creacion')
    
    # Especificamos una plantilla personalizada para la vista de lista
    change_list_template = 'admin/explorer/initialgrid/change_list.html'

    def changelist_view(self, request, extra_context=None):
        """
        Sobrescribe la vista de lista para inyectar las coordenadas
        de todos los puntos en el contexto.
        """
        # Obtenemos todos los puntos
        queryset = self.get_queryset(request)
        
        # Serializamos los puntos a un formato que JavaScript pueda leer ([lat, lon])
        points_data = [
            [p.points.y, p.points.x] for p in queryset if p.points
        ]
        
        # Añadimos los puntos al contexto
        extra_context = extra_context or {}
        extra_context['points_json'] = json.dumps(points_data)
        
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(NewsletterSubscription)
class NewsletterSubscriptionAdmin(admin.ModelAdmin):
    """Configuración del admin para suscripciones del newsletter."""
    
    list_display = [
        'email', 
        'nombre',
        'status_display', 
        'confirmado_display',
        'fecha_suscripcion', 
        'fuente',
        'ip_address'
    ]
    
    list_filter = [
        'activo', 
        'confirmado', 
        'fuente',
        'fecha_suscripcion',
        'fecha_confirmacion'
    ]
    
    search_fields = [
        'email', 
        'nombre', 
        'ip_address'
    ]
    
    readonly_fields = [
        'fecha_suscripcion', 
        'fecha_confirmacion', 
        'token_confirmacion',
        'ip_address',
        'user_agent'
    ]
    
    list_per_page = 50
    date_hierarchy = 'fecha_suscripcion'
    
    fieldsets = (
        ('Información del Suscriptor', {
            'fields': ('email', 'nombre')
        }),
        ('Estado de Suscripción', {
            'fields': ('activo', 'confirmado', 'fecha_confirmacion')
        }),
        ('Información Técnica', {
            'fields': ('fecha_suscripcion', 'token_confirmacion', 'fuente'),
            'classes': ('collapse',)
        }),
        ('Información de Registro', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activar_suscripciones', 'desactivar_suscripciones', 'confirmar_suscripciones']
    
    def status_display(self, obj):
        if obj.activo:
            return format_html('<span style="color: green;">🟢 Activo</span>')
        else:
            return format_html('<span style="color: red;">🔴 Inactivo</span>')
    status_display.short_description = 'Estado'
    
    def confirmado_display(self, obj):
        if obj.confirmado:
            return format_html('<span style="color: green;">✅ Confirmado</span>')
        else:
            return format_html('<span style="color: orange;">⏳ Pendiente</span>')
    confirmado_display.short_description = 'Confirmación'
    
    def activar_suscripciones(self, request, queryset):
        updated = queryset.update(activo=True)
        self.message_user(request, f'{updated} suscripciones activadas.')
    activar_suscripciones.short_description = "Activar suscripciones seleccionadas"
    
    def desactivar_suscripciones(self, request, queryset):
        updated = queryset.update(activo=False)
        self.message_user(request, f'{updated} suscripciones desactivadas.')
    desactivar_suscripciones.short_description = "Desactivar suscripciones seleccionadas"
    
    def confirmar_suscripciones(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(confirmado=False).update(
            confirmado=True, 
            fecha_confirmacion=timezone.now()
        )
        self.message_user(request, f'{updated} suscripciones confirmadas.')
    confirmar_suscripciones.short_description = "Confirmar suscripciones seleccionadas"
    
    def get_queryset(self, request):
        return super().get_queryset(request).order_by('-fecha_suscripcion')


# Personalización del título del admin
admin.site.site_header = "ViveMedellín - Administración"
admin.site.site_title = "ViveMedellín Admin"
admin.site.index_title = "Panel de Administración"
    
