from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView, TemplateView
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.db.models import Count, Q, F, Window, Prefetch
from django.db.models.functions import Rank
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone
import json
import ipaddress
from pgvector.django import CosineDistance
from django.views import View
from django.utils.translation import gettext as _, ngettext, get_language
from explorer.utils.types import get_localized_place_type, get_localized_place_type_from_code
from django.conf import settings
from django.urls import reverse
from django.utils.crypto import salted_hmac
from hashlib import sha1
from urllib.parse import urlencode
import re
import urllib.request
import urllib.parse
import os

from .models import Places, Foto, RegionOSM, Tag, PLACE_TYPE_CHOICES


# ────────────────────────────────────────────────────────────────────────
# Tipos de lugares a EXCLUIR de listados públicos
# (no son relevantes para gastronomía/entretenimiento)
# ────────────────────────────────────────────────────────────────────────
TIPOS_EXCLUIDOS = [
    # Belleza/Personal
    'barber_shop', 'beautician', 'beauty_salon', 'wellness_center', 'spa',
    # Automotriz
    'car_wash', 'parking',
    # Salud
    'doctor', 'health',
    # Educación
    'school', 'childrens_camp',
    # Servicios domésticos
    'laundry', 'real_estate_agency',
    # Solo servicio (sin local físico)
    'catering_service', 'food_delivery',
    # Otros no relevantes
    'internet_cafe', 'playground', 'auditorium', 'barbecue_area',
]


# ────────────────────────────────────────────────────────────────────────
# Rate Limiting para Protección contra Bots
# ────────────────────────────────────────────────────────────────────────

def get_client_ip(request):
    """Obtiene la IP real del cliente (incluso tras proxy)."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip


def rate_limit(requests_per_minute=30, key_prefix='rl'):
    """
    Decorador de rate limiting basado en cache.
    
    Args:
        requests_per_minute: Número máximo de requests por minuto
        key_prefix: Prefijo para la clave de cache
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            ip = get_client_ip(request)
            cache_key = f"{key_prefix}:{ip}"
            
            # Obtener contador actual
            current = cache.get(cache_key, 0)
            
            if current >= requests_per_minute:
                return JsonResponse({
                    'success': False,
                    'error': 'Rate limit exceeded. Please try again later.',
                    'retry_after': 60
                }, status=429)
            
            # Incrementar contador
            cache.set(cache_key, current + 1, timeout=60)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def is_suspicious_request(request):
    """
    Detecta requests sospechosos de bots maliciosos.
    Retorna True si la request parece sospechosa.
    """
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    
    # Bots conocidos maliciosos
    bad_bots = [
        'scrapy', 'python-requests', 'curl/', 'wget/', 
        'sqlmap', 'nikto', 'nmap', 'masscan',
        'zgrab', 'gobuster', 'dirbuster'
    ]
    
    for bot in bad_bots:
        if bot in user_agent:
            return True
    
    # Sin User-Agent
    if not user_agent or len(user_agent) < 10:
        return True
    
    return False


# ────────────────────────────────────────────────────────────────────────
# Helpers para Imágenes Optimizadas
# ────────────────────────────────────────────────────────────────────────

def get_optimized_image_urls(foto, size='thumb'):
    """
    Retorna las URLs de imagen optimizadas.
    
    Args:
        foto: Objeto Foto o None
        size: 'thumb' (220px), 'medium' (800px), 'full' (original)
    
    Returns:
        dict con 'imagen' (URL principal) y 'imagen_full' (para modal)
    """
    if not foto:
        return {'imagen': None, 'imagen_full': None}
    
    thumb = getattr(foto, 'imagen_miniatura', None) or ''
    medium = getattr(foto, 'imagen_mediana', None) or ''
    full = getattr(foto, 'imagen', None) or ''
    
    if size == 'thumb':
        return {'imagen': thumb or medium or full, 'imagen_full': full}
    elif size == 'medium':
        return {'imagen': medium or full, 'imagen_full': full}
    else:
        return {'imagen': full, 'imagen_full': full}


# ────────────────────────────────────────────────────────────────────────
# Mixins Optimizados
# ────────────────────────────────────────────────────────────────────────

class CacheMixin:
    """Mixin para manejar caché en las vistas."""
    cache_timeout = 3600  # 1 hora por defecto

    def get_cache_key(self):
        """Genera una clave de caché única basada en la vista y parámetros."""
        params = "_".join(f"{k}:{v}" for k, v in sorted(self.request.GET.items()))
        return f"{self.__class__.__name__}_{self.request.path}_{params}"

    def get_from_cache(self):
        return cache.get(self.get_cache_key())

    def set_to_cache(self, data):
        # No intentamos cachear querysets con prefetch_related para 'fotos'
        # ya que causan problemas al deserializar
        if hasattr(data, '_prefetch_related_lookups'):
            prefetch_lookups = [str(lookup) for lookup in data._prefetch_related_lookups]
            if 'fotos' in prefetch_lookups or any('fotos' in lookup for lookup in prefetch_lookups):
                # Omitimos el cacheo para evitar el error
                return
        
        cache.set(self.get_cache_key(), data, self.cache_timeout)


class BasePlacesMixin:
    """Mixin base para todas las vistas de lugares con configuraciones comunes."""
    model = Places
    context_object_name = "lugares"
    
    def get_base_queryset(self):
        """Queryset base optimizado para todos los lugares."""
        # Excluir: sin fotos, rating muy bajo, tipos irrelevantes
        return Places.objects.filter(
            tiene_fotos=True
        ).exclude(
            tipo__in=TIPOS_EXCLUIDOS
        ).filter(
            Q(rating__gte=2.0) | Q(rating__isnull=True)
        ).prefetch_related(
            Prefetch('fotos', queryset=Foto.objects.only('imagen', 'imagen_mediana', 'imagen_miniatura')[:3], to_attr='cached_fotos'),
            Prefetch('tags', to_attr='cached_tags')
        )


class SearchMixin:
    """Mixin para búsqueda avanzada con pesos personalizados."""
    search_fields = ['nombre', 'descripcion', 'tipo']
    search_weights = {'nombre': 'A', 'descripcion': 'B', 'tipo': 'C'}

    def get_search_vector(self):
        """Crea un vector de búsqueda ponderado."""
        return sum(
            (SearchVector(field, weight=self.search_weights.get(field, 'D'))
             for field in self.search_fields),
            SearchVector()
        )

    def apply_search(self, queryset, search_term):
        """Aplica búsqueda con ranking de resultados."""
        if not search_term:
            return queryset

        search_query = SearchQuery(search_term)
        search_vector = self.get_search_vector()
        
        return queryset.annotate(
            search=search_vector,
            rank=SearchRank(search_vector, search_query)
        ).filter(
            search=search_query
        ).order_by('-rank')


# ────────────────────────────────────────────────────────────────────────
# Vistas Principales
# ────────────────────────────────────────────────────────────────────────

class HomeView(TemplateView):
    """Vista de inicio que muestra lugares agrupados por regiones OSM."""
    template_name = "home.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Datos para filtros
        context.update(self._get_filtros_data())
        
        # Verificar caché (por idioma)
        cache_key = f"home_regiones_osm_{(get_language() or 'es').lower()}"
        comuna_con_lugares = cache.get(cache_key)
        
        if comuna_con_lugares is None:
            # Obtener regiones que tienen lugares destacados para home
            # Orden personalizado: El Poblado, Laureles, comunas (nivel 8), municipios (nivel 6)
            from django.db.models import Case, When, IntegerField
            
            regiones_con_lugares = RegionOSM.objects.filter(
                osm_id__in=Places.objects.filter(
                    show_in_home=True,
                    tiene_fotos=True
                ).values_list('comuna_osm_id', flat=True).distinct()
            ).annotate(
                orden_prioridad=Case(
                    When(name__icontains='Poblado', then=1),
                    When(name__icontains='Laureles', then=2),
                    When(admin_level='8', then=3),  # Comunas
                    When(admin_level='6', then=4),  # Municipios
                    default=5,
                    output_field=IntegerField()
                )
            ).order_by('orden_prioridad', 'name')[:6]  # Máximo 6 regiones
            
            # Si no hay lugares con show_in_home, usar regiones con mejor rating
            if not regiones_con_lugares.exists():
                regiones_con_lugares = RegionOSM.objects.filter(
                    osm_id__in=Places.objects.filter(
                        tiene_fotos=True,
                        rating__gte=4.0
                    ).values_list('comuna_osm_id', flat=True).distinct()
                ).annotate(
                    orden_prioridad=Case(
                        When(name__icontains='Poblado', then=1),
                        When(name__icontains='Laureles', then=2),
                        When(admin_level='8', then=3),  # Comunas
                        When(admin_level='6', then=4),  # Municipios
                        default=5,
                        output_field=IntegerField()
                    )
                ).order_by('orden_prioridad', 'name')[:6]
            
            # Procesar datos por región
            comuna_con_lugares = []
            for region in regiones_con_lugares:
                # Obtener lugares de esta región
                lugares_region = Places.objects.filter(
                    comuna_osm_id=region.osm_id,
                    tiene_fotos=True,
                    show_in_home=True
                ).prefetch_related('fotos').order_by('-es_destacado', '-weighted_rating', '-rating')[:6]
                
                # Si no hay lugares con show_in_home en esta región, usar los mejores
                if not lugares_region.exists():
                    lugares_region = Places.objects.filter(
                        comuna_osm_id=region.osm_id,
                        tiene_fotos=True,
                        rating__gte=4.0
                    ).prefetch_related('fotos').order_by('-es_destacado', '-weighted_rating', '-rating')[:6]
                
                if lugares_region.exists():
                    # Procesar lugares de la región
                    lugares_data = []
                    for lugar in lugares_region:
                        primera_foto = lugar.fotos.first()
                        lugares_data.append({
                            'nombre': lugar.nombre,
                            'slug': lugar.slug,
                            'rating': lugar.rating or 0.0,
                            'total_reviews': lugar.total_reviews,
                            'tipo': get_localized_place_type(lugar),
                            **get_optimized_image_urls(primera_foto, 'thumb'),
                            'es_destacado': lugar.es_destacado,
                            'es_exclusivo': lugar.es_exclusivo
                        })
                    
                    comuna_con_lugares.append({
                        'nombre': _(region.name),
                        'slug': region.slug,
                        'lugares': lugares_data,
                        'es_municipio': region.admin_level == '6',
                        'osm_id': region.osm_id
                    })
            
            # Guardar en caché por 1 hora
            cache.set(cache_key, comuna_con_lugares, 3600)
        
        context['comuna_con_lugares'] = comuna_con_lugares
        return context

    def _get_filtros_data(self):
        """Obtiene datos para los filtros del home."""
        # 1. ÁREAS - Dropdown debe mostrar listas completas; chips pueden ser una selección.
        from django.db.models import Case, When, IntegerField
        
        regiones_con_lugares = Places.objects.filter(tiene_fotos=True).values_list('comuna_osm_id', flat=True).distinct()

        regiones_qs = RegionOSM.objects.filter(
            osm_id__in=regiones_con_lugares,
            name__isnull=False,
        ).annotate(
            orden_area=Case(
                When(name__icontains='Poblado', then=1),
                When(name__icontains='Laureles', then=2),
                When(admin_level='8', then=3),  # comunas
                When(admin_level='6', then=4),  # municipios
                default=5,
                output_field=IntegerField()
            )
        ).order_by('orden_area', 'name')

        # Listas completas para dropdown
        regiones_areas = list(regiones_qs)
        comunas_medellin = [r for r in regiones_areas if getattr(r, "admin_level", None) == "8"]
        otras_regiones = [r for r in regiones_areas if getattr(r, "admin_level", None) != "8"]

        # Selección para chips (evita una nube enorme en mobile)
        comunas_medellin_chips = comunas_medellin[:18]
        otras_regiones_chips = otras_regiones[:10]
        
        # 2. TIPOS - Lista completa (antes estaba recortada y por eso no veías todo)
        # home.html espera estructura: [{name, icon, color, subcategorias:[{value,name}]}]
        # Hacemos grupos "humanos" por heurística sobre el code.
        def _label_for(code: str, es_label: str) -> str:
            # En ES usamos la etiqueta del choice; en EN se traduce si existe, o se deriva en frontend.
            return _(es_label)

        restaurants: list[dict] = []
        nightlife: list[dict] = []
        cafes: list[dict] = []
        culture: list[dict] = []
        other: list[dict] = []

        for code, es_label in PLACE_TYPE_CHOICES:
            # Excluir tipos irrelevantes de los filtros
            if code in TIPOS_EXCLUIDOS:
                continue
            item = {"value": code, "name": _label_for(code, es_label)}
            c = (code or "").lower()
            if "restaurant" in c or c in {"food", "food_court", "meal_delivery", "meal_takeaway"}:
                restaurants.append(item)
            elif c in {"bar", "wine_bar", "pub", "night_club", "karaoke", "bar_and_grill"}:
                nightlife.append(item)
            elif "cafe" in c or c in {"cafeteria", "acai_shop", "cat_cafe", "dog_cafe"}:
                cafes.append(item)
            elif "museum" in c or "art" in c or "cultural" in c or "historical" in c or "attraction" in c or "tour" in c or "landmark" in c:
                culture.append(item)
            else:
                other.append(item)

        categorias_reales = []
        if restaurants:
            categorias_reales.append({"name": _("Restaurantes y comida"), "icon": "bi-cup-hot", "color": "success", "subcategorias": restaurants})
        if nightlife:
            categorias_reales.append({"name": _("Bares y vida nocturna"), "icon": "bi-cup-straw", "color": "warning", "subcategorias": nightlife})
        if cafes:
            categorias_reales.append({"name": _("Cafeterías"), "icon": "bi-cup", "color": "info", "subcategorias": cafes})
        if culture:
            categorias_reales.append({"name": _("Cultura y atracciones"), "icon": "bi-camera", "color": "primary", "subcategorias": culture})
        # Nota: Categoría "Bienestar y spa" eliminada porque todos sus tipos están excluidos
        if other:
            categorias_reales.append({"name": _("Otros"), "icon": "bi-three-dots", "color": "secondary", "subcategorias": other})
        
        # 3. ETIQUETAS ESPECIALES - Características y servicios
        etiquetas_especiales = [
            {
                'name': _('Servicios de Entrega'),
                'icon': 'bi-bicycle',
                'opciones': [
                    {'field': 'delivery', 'name': _('Delivery'), 'icon': 'bi-bicycle'},
                    {'field': 'takeout', 'name': _('Para Llevar'), 'icon': 'bi-bag'},
                    {'field': 'dine_in', 'name': _('Comer en Local'), 'icon': 'bi-house'},
                ]
            },
            {
                'name': _('Ambiente & Experiencia'),
                'icon': 'bi-stars',
                'opciones': [
                    {'field': 'outdoor_seating', 'name': _('Terraza'), 'icon': 'bi-tree'},
                    {'field': 'live_music', 'name': _('Música en Vivo'), 'icon': 'bi-music-note-beamed'},
                    {'field': 'good_for_groups', 'name': _('Para Grupos'), 'icon': 'bi-people'},
                    {'field': 'good_for_children', 'name': _('Para Niños'), 'icon': 'bi-emoji-smile'},
                ]
            },
            {
                'name': _('Especialidades'),
                'icon': 'bi-cup-straw',
                'opciones': [
                    {'field': 'serves_cocktails', 'name': _('Cócteles'), 'icon': 'bi-cup-straw'},
                    {'field': 'serves_wine', 'name': _('Vinos'), 'icon': 'bi-cup'},
                    {'field': 'serves_coffee', 'name': _('Café Especialidad'), 'icon': 'bi-cup-hot'},
                    {'field': 'serves_dessert', 'name': _('Postres'), 'icon': 'bi-cake'},
                ]
            },
            {
                'name': _('Accesibilidad & Comodidades'),
                'icon': 'bi-universal-access',
                'opciones': [
                    {'field': 'wheelchair_accessible_entrance', 'name': _('Acceso Accesible'), 'icon': 'bi-universal-access'},
                    {'field': 'allows_dogs', 'name': _('Pet Friendly'), 'icon': 'bi-heart'},
                    {'field': 'accepts_credit_cards', 'name': _('Tarjetas de Crédito'), 'icon': 'bi-credit-card'},
                ]
            }
        ]
        
        return {
            'regiones_areas': regiones_areas,
            'comunas_medellin': comunas_medellin,
            'otras_regiones': otras_regiones,
            'comunas_medellin_chips': comunas_medellin_chips,
            'otras_regiones_chips': otras_regiones_chips,
            'categorias_reales': categorias_reales,
            'etiquetas_especiales': etiquetas_especiales,
        }


class PlacesListView(ListView):
    """Lista paginada de lugares - SIMPLIFICADA PARA QUE FUNCIONE."""
    template_name = "lugares/places_list.html"
    model = Places
    context_object_name = "lugares"
    paginate_by = 24
    
    def get_queryset(self):
        """Obtiene y filtra lugares según parámetros de búsqueda."""
        # Queryset base: con fotos, sin tipos irrelevantes, rating decente
        qs = Places.objects.filter(
            tiene_fotos=True
        ).exclude(
            tipo__in=TIPOS_EXCLUIDOS
        ).filter(
            Q(rating__gte=2.0) | Q(rating__isnull=True)
        ).prefetch_related('fotos').order_by('-es_destacado', '-weighted_rating', '-rating', 'nombre')

        # Búsqueda por nombre
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(nombre__icontains=q)
        
        # Filtro por tipo de lugar (desde dropdown del navbar)
        tipo = self.request.GET.get('tipo')
        if tipo:
            qs = qs.filter(tipo=tipo)
            
        # Filtro por comuna/barrio
        comuna = self.request.GET.get('comuna')
        if comuna:
            qs = qs.filter(comuna_osm_id=comuna)
            
        # Filtros especiales de características
        filtros_especiales = [
            'delivery', 'takeout', 'dine_in', 'outdoor_seating', 'live_music', 
            'allows_dogs', 'good_for_groups', 'good_for_children', 'serves_cocktails', 
            'serves_wine', 'serves_coffee', 'serves_dessert',
            'wheelchair_accessible_entrance', 'accepts_credit_cards'
        ]
        
        for filtro in filtros_especiales:
            valor = self.request.GET.get(filtro)
            if valor == 'true':
                qs = qs.filter(**{filtro: True})
            
        return qs
    
    def get_context_data(self, **kwargs):
        """Contexto básico para la lista de lugares."""
        context = super().get_context_data(**kwargs)
        
        # Información de filtros
        tipo_actual = self.request.GET.get("tipo", "")
        busqueda_actual = self.request.GET.get("q", "")
        comuna_actual = self.request.GET.get("comuna", "")
        
        # Mapeo de tipos a títulos y descripciones SEO-friendly
        # Diccionario base con tipos comunes y sus descripciones SEO
        tipos_info = {
            'restaurant': {
                'titulo': _('Mejores Restaurantes en Medellín'),
                'descripcion': _('Descubre los sabores más auténticos de la gastronomía paisa y mundial'),
                'icono': 'bi-cup-hot'
            },
            'bar': {
                'titulo': _('Mejores Bares en Medellín'), 
                'descripcion': _('Vive la mejor vida nocturna de la ciudad de la eterna primavera'),
                'icono': 'bi-cup-straw'
            },
            'cafe': {
                'titulo': _('Mejores Cafeterías en Medellín'),
                'descripcion': _('Experimenta la auténtica cultura cafetera paisa'),
                'icono': 'bi-cup'
            },
            'night_club': {
                'titulo': _('Mejores Discotecas en Medellín'),
                'descripcion': _('Las mejores discotecas y clubes nocturnos de la ciudad'),
                'icono': 'bi-moon-stars'
            },
            'pub': {
                'titulo': _('Mejores Pubs en Medellín'),
                'descripcion': _('Descubre los pubs más auténticos de la ciudad'),
                'icono': 'bi-cup-straw'
            },
            'wine_bar': {
                'titulo': _('Mejores Bares de Vinos en Medellín'),
                'descripcion': _('Los mejores lugares para disfrutar de una copa de vino'),
                'icono': 'bi-cup'
            },
            'spa': {
                'titulo': _('Mejores Spas en Medellín'),
                'descripcion': _('Relájate en los mejores spas y centros de bienestar'),
                'icono': 'bi-droplet'
            },
            'karaoke': {
                'titulo': _('Mejores Karaokes en Medellín'),
                'descripcion': _('Canta y diviértete en los mejores karaokes de la ciudad'),
                'icono': 'bi-mic'
            },
            # Restaurantes por cocina
            'italian_restaurant': {
                'titulo': _('Mejores Restaurantes Italianos en Medellín'),
                'descripcion': _('Disfruta de la auténtica cocina italiana en Medellín'),
                'icono': 'bi-cup-hot'
            },
            'mexican_restaurant': {
                'titulo': _('Mejores Restaurantes Mexicanos en Medellín'),
                'descripcion': _('Sabores auténticos de la cocina mexicana'),
                'icono': 'bi-cup-hot'
            },
            'japanese_restaurant': {
                'titulo': _('Mejores Restaurantes Japoneses en Medellín'),
                'descripcion': _('Sushi, ramen y más en los mejores restaurantes japoneses'),
                'icono': 'bi-cup-hot'
            },
            'chinese_restaurant': {
                'titulo': _('Mejores Restaurantes Chinos en Medellín'),
                'descripcion': _('Disfruta de la auténtica cocina china'),
                'icono': 'bi-cup-hot'
            },
            'french_restaurant': {
                'titulo': _('Mejores Restaurantes Franceses en Medellín'),
                'descripcion': _('Haute cuisine francesa en la ciudad'),
                'icono': 'bi-cup-hot'
            },
            'seafood_restaurant': {
                'titulo': _('Mejores Marisquerías en Medellín'),
                'descripcion': _('Los mejores mariscos y pescados frescos'),
                'icono': 'bi-cup-hot'
            },
            'pizza_restaurant': {
                'titulo': _('Mejores Pizzerías en Medellín'),
                'descripcion': _('Las pizzas más deliciosas de la ciudad'),
                'icono': 'bi-cup-hot'
            },
            'hamburger_restaurant': {
                'titulo': _('Mejores Hamburgueserías en Medellín'),
                'descripcion': _('Las hamburguesas más jugosas y deliciosas'),
                'icono': 'bi-cup-hot'
            },
            'steak_house': {
                'titulo': _('Mejores Asaderos en Medellín'),
                'descripcion': _('Las mejores carnes a la parrilla'),
                'icono': 'bi-cup-hot'
            },
            'sushi_restaurant': {
                'titulo': _('Mejores Restaurantes de Sushi en Medellín'),
                'descripcion': _('El sushi más fresco de la ciudad'),
                'icono': 'bi-cup-hot'
            },
            'fast_food_restaurant': {
                'titulo': _('Mejores Restaurantes de Comida Rápida en Medellín'),
                'descripcion': _('Comida rápida deliciosa para cualquier momento'),
                'icono': 'bi-cup-hot'
            },
            'vegan_restaurant': {
                'titulo': _('Mejores Restaurantes Veganos en Medellín'),
                'descripcion': _('Opciones veganas deliciosas para todos'),
                'icono': 'bi-cup-hot'
            },
            'vegetarian_restaurant': {
                'titulo': _('Mejores Restaurantes Vegetarianos en Medellín'),
                'descripcion': _('Comida vegetariana saludable y deliciosa'),
                'icono': 'bi-cup-hot'
            },
            'fine_dining_restaurant': {
                'titulo': _('Mejores Restaurantes Gourmet en Medellín'),
                'descripcion': _('Experiencias gastronómicas de alto nivel'),
                'icono': 'bi-cup-hot'
            },
            'breakfast_restaurant': {
                'titulo': _('Mejores Restaurantes de Desayuno en Medellín'),
                'descripcion': _('Comienza el día con los mejores desayunos'),
                'icono': 'bi-cup-hot'
            },
            'brunch_restaurant': {
                'titulo': _('Mejores Lugares de Brunch en Medellín'),
                'descripcion': _('Los mejores brunchs de la ciudad'),
                'icono': 'bi-cup-hot'
            },
        }
        
        # Detectar filtros especiales activos
        filtros_activos = []
        filtros_especiales_map = {
            'delivery': _('con Delivery'),
            'takeout': _('Para Llevar'),
            'dine_in': _('Comer en Local'),
            'outdoor_seating': _('con Terraza'),
            'live_music': _('con Música en Vivo'),
            'allows_dogs': _('Pet Friendly'),
            'good_for_groups': _('Para Grupos'),
            'good_for_children': _('Para Niños'),
            'serves_cocktails': _('con Cócteles'),
            'serves_wine': _('con Vinos'),
            'serves_coffee': _('Café Especialidad'),
            'serves_dessert': _('con Postres'),
            'wheelchair_accessible_entrance': _('Accesibles'),
            'accepts_credit_cards': _('Aceptan Tarjetas'),
        }
        
        for filtro, nombre in filtros_especiales_map.items():
            if self.request.GET.get(filtro) == 'true':
                filtros_activos.append(nombre)

        # Obtener información de la comuna si está filtrada
        comuna_info = None
        if comuna_actual:
            try:
                comuna_info = RegionOSM.objects.get(osm_id=comuna_actual)
            except RegionOSM.DoesNotExist:
                pass

        # Obtener label traducido del tipo actual (para tipos no predefinidos)
        tipo_label_traducido = None
        if tipo_actual:
            # Buscar en PLACE_TYPE_CHOICES para obtener el label en español
            for code, es_label in PLACE_TYPE_CHOICES:
                if code == tipo_actual:
                    tipo_label_traducido = _(es_label)  # Traducir al idioma actual
                    break
            if not tipo_label_traducido:
                # Fallback: humanizar el código
                tipo_label_traducido = tipo_actual.replace('_', ' ').title()
        
        # Título y descripción dinámicos - lógica SEO completa
        ubicacion = comuna_info.name if comuna_info else _('Medellín')
        filtros_text = _(' y ').join(filtros_activos[:2]) if filtros_activos else ''
        
        if busqueda_actual:
            # Búsqueda textual
            titulo_pagina = _("Resultados para \"%(query)s\"") % {"query": busqueda_actual}
            descripcion_pagina = _('Lugares que coinciden con tu búsqueda en %(ubicacion)s') % {'ubicacion': ubicacion}
        
        elif tipo_actual:
            # Tenemos un tipo seleccionado
            if tipo_actual in tipos_info:
                # Tipo con descripción SEO predefinida
                info = tipos_info[tipo_actual]
                if comuna_info:
                    # Reemplazar "en Medellín" por "en {comuna}"
                    titulo_base = str(info['titulo']).replace(_('en Medellín'), '')
                    titulo_base = str(titulo_base).replace('en Medellín', '').strip()
                    titulo_pagina = _('%(titulo)s en %(comuna)s') % {'titulo': titulo_base, 'comuna': comuna_info.name}
                else:
                    titulo_pagina = info['titulo']
                
                if filtros_activos:
                    titulo_pagina = str(titulo_pagina) + ' ' + filtros_text
                
                if comuna_info:
                    descripcion_pagina = _('%(desc)s en la zona de %(comuna)s') % {'desc': info['descripcion'], 'comuna': comuna_info.name}
                else:
                    descripcion_pagina = info['descripcion']
            else:
                # Tipo dinámico (no predefinido) - generar título SEO
                if comuna_info:
                    titulo_pagina = _('Mejores %(tipo)s en %(comuna)s') % {'tipo': tipo_label_traducido, 'comuna': comuna_info.name}
                    descripcion_pagina = _('Descubre los mejores %(tipo)s en la zona de %(comuna)s') % {'tipo': tipo_label_traducido.lower(), 'comuna': comuna_info.name}
                else:
                    titulo_pagina = _('Mejores %(tipo)s en Medellín') % {'tipo': tipo_label_traducido}
                    descripcion_pagina = _('Descubre los mejores %(tipo)s en la ciudad') % {'tipo': tipo_label_traducido.lower()}
                
                if filtros_activos:
                    titulo_pagina = str(titulo_pagina) + ' ' + filtros_text
        
        elif comuna_info and filtros_activos:
            # Comuna + filtros especiales (sin tipo)
            titulo_pagina = _('Lugares %(filters)s en %(comuna)s') % {'filters': filtros_text, 'comuna': comuna_info.name}
            descripcion_pagina = _('Lugares especializados en %(comuna)s que cumplen tus criterios') % {'comuna': comuna_info.name}
        
        elif comuna_info:
            # Solo comuna, sin tipo ni filtros
            titulo_pagina = _('Los Mejores Lugares en %(comuna)s') % {'comuna': comuna_info.name}
            descripcion_pagina = _('Descubre los sitios más destacados de %(comuna)s') % {'comuna': comuna_info.name}
        
        elif filtros_activos:
            # Solo filtros especiales, sin comuna ni tipo
            titulo_pagina = _('Lugares %(filters)s en Medellín') % {'filters': filtros_text}
            descripcion_pagina = _('Lugares especializados que cumplen tus criterios de búsqueda')
        
        else:
            # Vista general sin filtros
            titulo_pagina = _('Todos los Lugares en Medellín')
            descripcion_pagina = _('Descubre los mejores sitios que ofrece la ciudad')
        
        # Obtener regiones para filtros
        from django.db.models import Case, When, IntegerField
        regiones_filtro = RegionOSM.objects.filter(
            osm_id__in=Places.objects.filter(tiene_fotos=True).values_list('comuna_osm_id', flat=True).distinct()
        ).annotate(
            orden_area=Case(
                When(name__icontains='Poblado', then=1),
                When(name__icontains='Laureles', then=2),
                default=3,
                output_field=IntegerField()
            )
        ).order_by('orden_area', 'name')

        # Split para dropdown de áreas (template places_list.html lo espera así)
        comunas_medellin = [r for r in regiones_filtro if getattr(r, "admin_level", None) == "8"]
        otras_regiones = [r for r in regiones_filtro if getattr(r, "admin_level", None) != "8"]

        # Dropdown de tipos (template places_list.html espera `tipo_grupos_ui`)
        # Estructura: [{emoji, name, items:[{code,label}]}]
        from explorer.utils.types import derive_english_from_code
        lang = (get_language() or "").lower()

        def label_for(code: str, es_label: str) -> str:
            # Usar traducción si existe; si estamos en EN y no hay, derivar del code.
            tr = _(es_label)
            if lang.startswith("en") and tr == es_label:
                return derive_english_from_code(code)
            return tr

        groups = [
            {"key": "food", "emoji": "🍽️", "name": _("Restaurantes y comida"), "items": []},
            {"key": "nightlife", "emoji": "🍸", "name": _("Bares y vida nocturna"), "items": []},
            {"key": "cafes", "emoji": "☕", "name": _("Cafeterías"), "items": []},
            {"key": "culture", "emoji": "🎭", "name": _("Cultura y atracciones"), "items": []},
            {"key": "other", "emoji": "✨", "name": _("Otros"), "items": []},
        ]
        idx = {g["key"]: g for g in groups}

        for code, es_label in PLACE_TYPE_CHOICES:
            # Excluir tipos irrelevantes de los filtros
            if code in TIPOS_EXCLUIDOS:
                continue
            item = {"code": code, "label": label_for(code, es_label)}
            c = (code or "").lower()
            if "restaurant" in c or c in {"food", "food_court", "meal_delivery", "meal_takeaway"}:
                idx["food"]["items"].append(item)
            elif c in {"bar", "wine_bar", "pub", "night_club", "karaoke", "bar_and_grill"}:
                idx["nightlife"]["items"].append(item)
            elif "cafe" in c or c in {"cafeteria", "acai_shop", "cat_cafe", "dog_cafe"}:
                idx["cafes"]["items"].append(item)
            elif "museum" in c or "art" in c or "cultural" in c or "historical" in c or "attraction" in c or "tour" in c or "landmark" in c:
                idx["culture"]["items"].append(item)
            else:
                idx["other"]["items"].append(item)

        tipo_grupos_ui = [g for g in groups if g["items"]]
        tipo_actual_label = None
        if tipo_actual:
            for g in tipo_grupos_ui:
                for it in g["items"]:
                    if it["code"] == tipo_actual:
                        tipo_actual_label = it["label"]
                        break
                if tipo_actual_label:
                    break
        
        context.update({
            "busqueda_actual": busqueda_actual,
            "tipo_actual": tipo_actual,
            "tipo_actual_label": tipo_actual_label,
            "titulo_pagina": titulo_pagina,
            "descripcion_pagina": descripcion_pagina,
            "tipos_info": tipos_info,
            "regiones_filtro": regiones_filtro,
            "comunas_medellin": comunas_medellin,
            "otras_regiones": otras_regiones,
            "tipo_grupos_ui": tipo_grupos_ui,
        })
        return context





class PlaceDetailView(DetailView, BasePlacesMixin):
    """Vista detallada de un lugar con información completa y recomendaciones."""
    template_name = "lugares/places_detail.html"
    slug_field = "slug"
    context_object_name = "lugar"
    
    def get_queryset(self):
        """Queryset optimizado específicamente para vista de detalle."""
        return Places.objects.filter(tiene_fotos=True).prefetch_related(
            Prefetch('fotos', queryset=Foto.objects.only('imagen', 'imagen_mediana', 'imagen_miniatura')[:5], to_attr='cached_fotos'),
            Prefetch('tags', to_attr='cached_tags')
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lugar = self.object
        
        # 🚀 PROGRESSIVE LOADING: Solo cargar info esencial inicialmente
        
        # Características del lugar (muy rápido - sin DB)
        context['caracteristicas'] = self._get_caracteristicas(lugar)
        
        # Horarios formateados (muy rápido - solo procesamiento)
        context['horarios'] = self._format_horarios(lugar)
        
        # 🎯 LAZY LOADING: Lugares relacionados se cargan con AJAX
        # Esto reduce el tiempo inicial de ~2.2s a ~0.5s
        context['lugares_cercanos'] = []
        context['lugares_similares'] = []
        context['lugares_misma_comuna'] = []
        
        # Meta data para AJAX loading
        context['ajax_endpoints'] = {
            # Respetar prefijo i18n (/en/...) automáticamente
            'lugares_cercanos': reverse('explorer:lugares_cercanos_ajax_slug', kwargs={'slug': lugar.slug}),
            'lugares_similares': reverse('explorer:lugares_similares_ajax_slug', kwargs={'slug': lugar.slug}),
            'lugares_comuna': reverse('explorer:lugares_comuna_ajax_slug', kwargs={'slug': lugar.slug}),
        }
        
        return context
    
    def _get_lugares_cercanos(self, lugar, distance=500, limit=3):
        """Obtener lugares cercanos con caché y optimización geoespacial."""
        from django.contrib.gis.db.models.functions import Distance as GeoDistance
        
        if not lugar.ubicacion:
            return []
            
        cache_key = f"nearby_optimized_{lugar.id}_{distance}_{limit}_v2"
        result = cache.get(cache_key)
        
        if result is None:
            result = list(Places.objects.filter(
                tiene_fotos=True,
                ubicacion__distance_lte=(lugar.ubicacion, distance)
            ).exclude(
                id=lugar.id
            ).only(
                'id', 'nombre', 'slug', 'tipo', 'rating', 'es_destacado', 'es_exclusivo', 'comuna_osm_id', 'ubicacion'
            ).prefetch_related(
                Prefetch('fotos', queryset=Foto.objects.only('imagen', 'imagen_mediana', 'imagen_miniatura')[:1], to_attr='cached_fotos')
            ).annotate(
                distancia_metros=GeoDistance('ubicacion', lugar.ubicacion)
            ).order_by('distancia_metros', '-es_destacado', '-weighted_rating', '-rating')[:limit])
            
            cache.set(cache_key, result, 3600)
        
        return result
    
    def _get_lugares_similares(self, lugar, limit=3):
        """
        Obtener lugares similares:
        - Siempre del MISMO tipo de lugar
        - Preferiblemente en la MISMA zona (misma comuna_osm_id cuando exista)
        - Priorizando destacados y mejor rating
        """
        comuna_id = getattr(lugar, "comuna_osm_id", None)
        cache_key = f"related_similares_{lugar.id}_{comuna_id}_{limit}"
        result = cache.get(cache_key)
        
        if result is None:
            # Filtro base: mismo tipo y siempre con fotos
            base_filter = {
                "tiene_fotos": True,
                "tipo": lugar.tipo,
            }
            # Si conocemos la comuna, restringimos a la misma zona
            if comuna_id:
                base_filter["comuna_osm_id"] = comuna_id

            # Opcional: usar tags para afinar, pero siempre dentro del mismo tipo/zona
            tags = list(lugar.tags.values_list('id', flat=True)[:5])  # Máx 5 tags
            qs = Places.objects.filter(**base_filter).exclude(id=lugar.id)

            if tags:
                qs = qs.filter(tags__id__in=tags).distinct()

            result = list(
                qs.only(
                    "id",
                    "nombre",
                    "slug",
                    "tipo",
                    "rating",
                    "es_destacado",
                    "es_exclusivo",
                )
                .prefetch_related(
                    Prefetch(
                        "fotos",
                        queryset=Foto.objects.only("imagen")[:1],
                        to_attr="cached_fotos",
                    )
                )
                .order_by("-es_destacado", "-weighted_rating", "-rating")[:limit]
            )
            
            cache.set(cache_key, result, 3600)  # 1 hora de caché
        
        return result
    
    def _get_lugares_misma_comuna(self, lugar, limit=6):
        """Obtener otros lugares de la misma comuna."""
        if not lugar.comuna_osm_id:
            return []
            
        cache_key = f"comuna_optimized_{lugar.comuna_osm_id}_{lugar.id}_{limit}"
        result = cache.get(cache_key)
        
        if result is None:
            result = list(Places.objects.filter(
                tiene_fotos=True,
                comuna_osm_id=lugar.comuna_osm_id
            ).exclude(
                id=lugar.id
            ).only(
                'id', 'nombre', 'slug', 'tipo', 'rating', 'es_destacado', 'es_exclusivo'
            ).prefetch_related(
                Prefetch('fotos', queryset=Foto.objects.only('imagen', 'imagen_mediana', 'imagen_miniatura')[:1], to_attr='cached_fotos')
            ).order_by('-es_destacado', '-weighted_rating', '-rating')[:limit])
            
            cache.set(cache_key, result, 3600)
        
        return result
    
    def _get_caracteristicas(self, lugar):
        """Obtener características del lugar para mostrar en UI."""
        caracteristicas = []
        
        # Servicios
        if lugar.takeout:
            caracteristicas.append({'icon': 'bi-bag', 'name': 'Para llevar'})
        
        if lugar.delivery:
            caracteristicas.append({'icon': 'bi-bicycle', 'name': 'Entrega a domicilio'})
        
        if lugar.dine_in:
            caracteristicas.append({'icon': 'bi-cup-hot', 'name': 'Servicio en mesa'})
        
        # Pagos
        if lugar.accepts_credit_cards:
            caracteristicas.append({'icon': 'bi-credit-card', 'name': 'Tarjetas de crédito'})
        
        # Accesibilidad
        if lugar.wheelchair_accessible_entrance:
            caracteristicas.append({'icon': 'bi-universal-access', 'name': 'Acceso para sillas de ruedas'})
        
        # Otros servicios
        if lugar.outdoor_seating:
            caracteristicas.append({'icon': 'bi-tree', 'name': 'Terraza al aire libre'})
        
        if lugar.good_for_children:
            caracteristicas.append({'icon': 'bi-people', 'name': 'Apto para niños'})
        
        if lugar.allows_dogs:
            caracteristicas.append({'icon': 'bi-emoji-smile', 'name': 'Admite mascotas'})
        
        return caracteristicas
    
    def _format_horarios(self, lugar):
        """Formatear horarios para mostrar en UI."""
        if not lugar.horario_json:
            return []
        
        dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        horarios = []
        
        try:
            for i, dia in enumerate(dias):
                key = str(i)
                if key in lugar.horario_json:
                    horario = lugar.horario_json[key]
                    if horario:
                        horarios.append({
                            'dia': dia,
                            'horario': horario
                        })
                    else:
                        horarios.append({
                            'dia': dia,
                            'horario': 'Cerrado'
                        })
        except (TypeError, KeyError):
            pass
        
        return horarios


class PlaceReviewsView(DetailView):
    """Vista para mostrar y gestionar reseñas de un lugar."""
    model = Places
    template_name = "lugares/reviews_lugar.html"
    slug_field = "slug"
    context_object_name = "lugar"
    
    def get_queryset(self):
        return Places.objects.filter(tiene_fotos=True).prefetch_related(
            Prefetch('fotos', queryset=Foto.objects.only('imagen', 'imagen_mediana', 'imagen_miniatura'), to_attr='cached_fotos')
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lugar = self.object
        
        # Procesar reviews desde JSON (máximo 5 de Google API)
        reviews = []
        if lugar.reviews:
            try:
                # Procesar todas las reseñas disponibles (Google solo envía máximo 5)
                reviews_to_process = lugar.reviews
                for review in reviews_to_process:
                    # Procesar el texto de la review correctamente
                    texto_review = review.get('text', '')
                    if isinstance(texto_review, dict):
                        # Si el texto viene como dict, tomar el valor del texto
                        texto_review = texto_review.get('text', '') if texto_review else ''
                    elif isinstance(texto_review, list):
                        # Si viene como lista, unir todos los elementos
                        texto_review = ' '.join(str(item) for item in texto_review if item)
                    
                    # Limpiar y formatear el texto
                    if texto_review:
                        texto_review = str(texto_review).strip()
                        # Remover caracteres de escape y formatear
                        texto_review = texto_review.replace('\\n', '\n').replace('\\r', '\r')
                        texto_review = texto_review.replace('\\"', '"').replace("\\'", "'")
                    
                    # Procesar fecha (preferir publishTime sobre time)
                    fecha_review = review.get('publishTime', '') or review.get('time', '') or review.get('relativePublishTimeDescription', '')
                    if fecha_review and str(fecha_review).isdigit():
                        try:
                            from datetime import datetime
                            fecha_review = datetime.fromtimestamp(int(fecha_review)).strftime('%d/%m/%Y')
                        except:
                            fecha_review = 'Fecha no disponible'
                    elif not fecha_review:
                        fecha_review = 'Fecha no disponible'
                    
                    # Procesar autor (preferir authorAttribution sobre author_name)
                    autor_review = 'Anónimo'
                    if review.get('authorAttribution'):
                        author_attr = review['authorAttribution']
                        if isinstance(author_attr, dict):
                            autor_review = author_attr.get('displayName', 'Anónimo')
                        else:
                            autor_review = str(author_attr)
                    elif review.get('author_name'):
                        autor_review = review['author_name']
                    
                    reviews.append({
                        'autor': autor_review,
                        'rating': int(review.get('rating', 0)) if review.get('rating') else 0,
                        'texto': texto_review,
                        'fecha': fecha_review,
                        'foto_perfil': review.get('profile_photo_url', '')
                    })
            except (AttributeError, TypeError) as e:
                # Log error silently instead of printing to console
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Error procesando reviews: {e}")
                pass
        
        context['reviews'] = reviews
        context['rating_promedio'] = lugar.rating
        # Total de reseñas (no lo mostramos en el template)
        actual_total = len(lugar.reviews) if lugar.reviews else 0
        context['total_reviews'] = lugar.total_reviews or actual_total
        
        return context


# ────────────────────────────────────────────────────────────────────────
# Funciones de Vista
# ────────────────────────────────────────────────────────────────────────

# @cache_page(60 * 60)  # desactivado temporalmente para ver cambios inmediatos
def home(request):
    """Vista de inicio que usa HomeView OPTIMIZADA."""
    view = HomeView.as_view()
    return view(request)


def about(request):
    """Página About/Manual de uso de ViveMedellín."""
    total_lugares = Places.objects.filter(tiene_fotos=True).count()
    total_comunas = RegionOSM.objects.filter(admin_level='8').count()
    tipos_unicos = (
        Places.objects.exclude(tipo__isnull=True)
        .exclude(tipo__exact='')
        .values_list('tipo', flat=True)
        .distinct()
        .count()
    )
    context = {
        "total_lugares": total_lugares,
        "total_comunas": total_comunas,
        "total_tipos": tipos_unicos,
    }
    return render(request, "about.html", context)


def lugares_list(request):
    """Vista de lista de lugares que usa PlacesListView."""
    view = PlacesListView.as_view()
    return view(request)


def lugares_detail(request, slug):
    """Vista de detalle de lugar que usa PlaceDetailView."""
    view = PlaceDetailView.as_view()
    return view(request, slug=slug)


def reviews_lugar(request, slug):
    """Vista de reseñas de lugar que usa PlaceReviewsView."""
    view = PlaceReviewsView.as_view()
    return view(request, slug=slug)


def lugares_por_comuna(request, comuna_slug):
    """Vista de lugares filtrada por comuna usando slug SEO-friendly."""
    
    # Obtener la región por slug
    try:
        # Buscar región por slug directo (método principal)
        region = RegionOSM.objects.filter(slug=comuna_slug).first()
        
        if not region:
            # Fallback: buscar por nombre convertido a slug
            region = RegionOSM.objects.filter(
                name__icontains=comuna_slug.replace('-', ' ')
            ).first()
        
        if not region:
            # Si no se encuentra la región, usar la vista normal con mensaje
            from django.shortcuts import render
            return render(request, 'lugares/places_list.html', {
                'lugares': [],
                'titulo_pagina': 'Comuna no encontrada',
                'descripcion_pagina': f'No se encontró información para "{comuna_slug}"',
                'regiones_filtro': RegionOSM.objects.all()[:20]
            })
            
    except Exception:
        from django.shortcuts import render
        return render(request, 'lugares/places_list.html', {
            'lugares': [],
            'titulo_pagina': 'Error',
            'descripcion_pagina': 'Error al buscar la comuna',
            'regiones_filtro': RegionOSM.objects.all()[:20]
        })
    
    # Crear una versión personalizada de PlacesListView con filtro de comuna
    class LugaresPorComunaView(PlacesListView):
        def get_queryset(self):
            # Queryset base filtrado por comuna, priorizando destacados
            qs = Places.objects.filter(
                tiene_fotos=True,
                comuna_osm_id=region.osm_id
            ).prefetch_related('fotos').order_by('-es_destacado', '-weighted_rating', '-rating', 'nombre')
            
            # Aplicar filtros adicionales de la URL
            q = self.request.GET.get("q")
            if q:
                qs = qs.filter(nombre__icontains=q)
            
            tipo = self.request.GET.get('tipo')
            if tipo:
                qs = qs.filter(tipo=tipo)

            # Filtros especiales
            filtros_especiales = [
                'delivery', 'takeout', 'dine_in', 'outdoor_seating', 'live_music', 
                'allows_dogs', 'good_for_groups', 'good_for_children', 'serves_cocktails', 
                'serves_wine', 'serves_coffee', 'serves_dessert',
                'wheelchair_accessible_entrance', 'accepts_credit_cards'
            ]
            
            for filtro in filtros_especiales:
                valor = self.request.GET.get(filtro)
                if valor == 'true':
                    qs = qs.filter(**{filtro: True})
                
            return qs
        
        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            
            # Información de filtros actuales
            tipo_actual = self.request.GET.get("tipo", "")
            busqueda_actual = self.request.GET.get("q", "")
            
            # Mapeo de tipos SEO para comuna específica (lista extendida)
            tipos_info = {
                'restaurant': {'titulo': _('Mejores Restaurantes'), 'descripcion': _('Descubre los sabores más auténticos')},
                'bar': {'titulo': _('Mejores Bares'), 'descripcion': _('Vive la mejor vida nocturna')},
                'cafe': {'titulo': _('Mejores Cafeterías'), 'descripcion': _('Experimenta la cultura cafetera')},
                'night_club': {'titulo': _('Mejores Discotecas'), 'descripcion': _('Las mejores discotecas y clubes nocturnos')},
                'pub': {'titulo': _('Mejores Pubs'), 'descripcion': _('Descubre los pubs más auténticos')},
                'wine_bar': {'titulo': _('Mejores Bares de Vinos'), 'descripcion': _('Los mejores lugares para una copa de vino')},
                'spa': {'titulo': _('Mejores Spas'), 'descripcion': _('Relájate en los mejores spas')},
                'karaoke': {'titulo': _('Mejores Karaokes'), 'descripcion': _('Canta y diviértete')},
                'italian_restaurant': {'titulo': _('Mejores Restaurantes Italianos'), 'descripcion': _('Auténtica cocina italiana')},
                'mexican_restaurant': {'titulo': _('Mejores Restaurantes Mexicanos'), 'descripcion': _('Sabores auténticos de México')},
                'japanese_restaurant': {'titulo': _('Mejores Restaurantes Japoneses'), 'descripcion': _('Sushi, ramen y más')},
                'chinese_restaurant': {'titulo': _('Mejores Restaurantes Chinos'), 'descripcion': _('Auténtica cocina china')},
                'seafood_restaurant': {'titulo': _('Mejores Marisquerías'), 'descripcion': _('Los mejores mariscos frescos')},
                'pizza_restaurant': {'titulo': _('Mejores Pizzerías'), 'descripcion': _('Las pizzas más deliciosas')},
                'hamburger_restaurant': {'titulo': _('Mejores Hamburgueserías'), 'descripcion': _('Las hamburguesas más jugosas')},
                'steak_house': {'titulo': _('Mejores Asaderos'), 'descripcion': _('Las mejores carnes a la parrilla')},
                'sushi_restaurant': {'titulo': _('Mejores Restaurantes de Sushi'), 'descripcion': _('El sushi más fresco')},
                'fast_food_restaurant': {'titulo': _('Mejores Restaurantes de Comida Rápida'), 'descripcion': _('Comida rápida deliciosa')},
                'vegan_restaurant': {'titulo': _('Mejores Restaurantes Veganos'), 'descripcion': _('Opciones veganas deliciosas')},
                'vegetarian_restaurant': {'titulo': _('Mejores Restaurantes Vegetarianos'), 'descripcion': _('Comida vegetariana saludable')},
                'fine_dining_restaurant': {'titulo': _('Mejores Restaurantes Gourmet'), 'descripcion': _('Experiencias gastronómicas de alto nivel')},
                'breakfast_restaurant': {'titulo': _('Mejores Restaurantes de Desayuno'), 'descripcion': _('Comienza el día con los mejores desayunos')},
                'brunch_restaurant': {'titulo': _('Mejores Lugares de Brunch'), 'descripcion': _('Los mejores brunchs')},
            }
            
            # Detectar filtros especiales activos
            filtros_activos = []
            filtros_especiales_map = {
                'delivery': _('con Delivery'), 'takeout': _('Para Llevar'), 
                'dine_in': _('Comer en Local'), 'outdoor_seating': _('con Terraza'),
                'live_music': _('con Música en Vivo'), 'allows_dogs': _('Pet Friendly'),
                'good_for_groups': _('Para Grupos'), 'good_for_children': _('Para Niños'),
                'serves_cocktails': _('con Cócteles'), 'serves_wine': _('con Vinos'),
                'serves_coffee': _('Café Especialidad'), 'serves_dessert': _('con Postres'),
                'wheelchair_accessible_entrance': _('Accesibles'),
                'accepts_credit_cards': _('Aceptan Tarjetas'),
            }
            
            for filtro, nombre in filtros_especiales_map.items():
                if self.request.GET.get(filtro) == 'true':
                    filtros_activos.append(nombre)

            # Obtener label traducido del tipo actual (para tipos no predefinidos)
            tipo_label_traducido = None
            if tipo_actual:
                for code, es_label in PLACE_TYPE_CHOICES:
                    if code == tipo_actual:
                        tipo_label_traducido = _(es_label)
                        break
                if not tipo_label_traducido:
                    tipo_label_traducido = tipo_actual.replace('_', ' ').title()

            # Título dinámico para comuna específica - SEO optimizado
            filtros_text = _(' y ').join(filtros_activos[:2]) if filtros_activos else ''
            
            if busqueda_actual:
                    titulo_pagina = _('Resultados para "%(query)s" en %(comuna)s') % {
                        'query': busqueda_actual,
                        'comuna': region.name,
                    }
                    descripcion_pagina = _('Lugares que coinciden con tu búsqueda en %(comuna)s') % {
                        'comuna': region.name,
                    }
            elif tipo_actual:
                if tipo_actual in tipos_info:
                    # Tipo predefinido - usar título + " en {comuna}"
                    info = tipos_info[tipo_actual]
                    # Construir directamente sin doble traducción
                    titulo_pagina = str(info['titulo']) + ' ' + _('en') + ' ' + region.name
                    descripcion_pagina = str(info['descripcion']) + ' ' + _('en') + ' ' + region.name
                else:
                    # Tipo dinámico
                    titulo_pagina = _('Mejores %(tipo)s en %(comuna)s') % {'tipo': tipo_label_traducido, 'comuna': region.name}
                    descripcion_pagina = _('Descubre los mejores %(tipo)s en %(comuna)s') % {'tipo': tipo_label_traducido.lower(), 'comuna': region.name}
                
                if filtros_activos:
                    titulo_pagina = str(titulo_pagina) + ' ' + filtros_text
            
            elif filtros_activos:
                titulo_pagina = _('Lugares %(filters)s en %(comuna)s') % {
                    'filters': filtros_text,
                    'comuna': region.name,
                }
                descripcion_pagina = _('Lugares especializados en %(comuna)s que cumplen tus criterios') % {
                        'comuna': region.name,
                    }
            else:
                titulo_pagina = _('Los Mejores Lugares en %(comuna)s') % {
                    'comuna': region.name,
                }
                descripcion_pagina = _('Descubre los sitios más destacados de %(comuna)s') % {
                    'comuna': region.name,
                }
            
            # Actualizar contexto
            context.update({
                "titulo_pagina": titulo_pagina,
                "descripcion_pagina": descripcion_pagina,
                "region_actual": region,
                "comuna_slug": comuna_slug,
            })
            
            return context
    
    # Usar la vista personalizada
    view = LugaresPorComunaView.as_view()
    return view(request)




@require_GET
def filtros_ajax_view(request):
    """API AJAX para filtros combinados del home."""
    from django.http import JsonResponse
    
    # Obtener parámetros
    area_id = request.GET.get('area')
    categoria = request.GET.get('categoria') 
    caracteristica = request.GET.get('caracteristica')
    
    if not all([area_id, categoria]):
        return JsonResponse({
            'error': _('Se requieren área y categoría. La característica es opcional.')
        }, status=400)
    
    try:
        # Construir queryset base - excluir tipos irrelevantes y ratings muy bajos
        qs = Places.objects.filter(tiene_fotos=True).exclude(
            tipo__in=TIPOS_EXCLUIDOS
        ).filter(
            Q(rating__gte=2.0) | Q(rating__isnull=True)
        )
        
        # Aplicar filtros
        if area_id != 'all':
            qs = qs.filter(comuna_osm_id=area_id)
            
        if categoria != 'all':
            qs = qs.filter(tipo=categoria)
            
        if caracteristica and caracteristica != 'all':
            qs = qs.filter(**{caracteristica: True})
        
        # Obtener resultados con prefetch, priorizando destacados
        lugares = qs.prefetch_related('fotos').order_by('-es_destacado', '-weighted_rating', '-rating', 'nombre')[:12]
        
        # Formatear datos para JSON
        resultados = []
        for lugar in lugares:
            primera_foto = lugar.fotos.first()
            resultados.append({
                'nombre': lugar.nombre,
                'slug': lugar.slug,
                'rating': lugar.rating or 0.0,
                'total_reviews': lugar.total_reviews or 0,
                'tipo': get_localized_place_type(lugar),
                **get_optimized_image_urls(primera_foto, 'thumb'),
                'es_destacado': lugar.es_destacado,
                'es_exclusivo': lugar.es_exclusivo,
                # Siempre enviar URL ya resuelta (evita bugs de prefijo /en en frontend)
                'url': reverse('explorer:lugares_detail', kwargs={'slug': lugar.slug}) if lugar.slug else None
            })
        
        # Obtener información del área
        area_info = None
        if area_id != 'all':
            try:
                region = RegionOSM.objects.get(osm_id=area_id)
                area_info = {
                    'nombre': region.name,
                    'osm_id': region.osm_id,
                    'slug': region.slug
                }
            except RegionOSM.DoesNotExist:
                pass
        
        return JsonResponse({
            'success': True,
            'total': len(resultados),
            'lugares': resultados,
            'area_info': area_info,
            'filtros_aplicados': {
                'area': area_id,
                'categoria': categoria,
                'caracteristica': caracteristica
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'error': _('Error en la búsqueda: %(err)s') % {'err': str(e)}
        }, status=500)


@require_GET
@rate_limit(requests_per_minute=60, key_prefix='places_filter')
def places_filter_ajax(request):
    """
    API AJAX profesional para filtrado dinámico en places_list.
    Soporta: área, tipo, características múltiples, paginación.
    """
    from django.http import JsonResponse
    from django.core.paginator import Paginator
    
    # Parámetros
    area_slug = request.GET.get('area', '').strip()
    tipo = request.GET.get('tipo', '').strip()
    page = request.GET.get('page', '1')
    per_page = 12
    
    # Características booleanas
    caracteristicas = [
        'delivery', 'takeout', 'dine_in', 'outdoor_seating', 'live_music',
        'good_for_groups', 'good_for_children', 'serves_cocktails', 'serves_wine',
        'serves_coffee', 'serves_dessert', 'wheelchair_accessible_entrance',
        'allows_dogs', 'accepts_credit_cards', 'reservable'
    ]
    
    try:
        page = int(page)
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    
    try:
        # Construir queryset base - excluir tipos irrelevantes y ratings muy bajos
        qs = Places.objects.filter(tiene_fotos=True).exclude(
            tipo__in=TIPOS_EXCLUIDOS
        ).filter(
            Q(rating__gte=2.0) | Q(rating__isnull=True)
        )
        
        # Filtrar por área
        region_info = None
        if area_slug:
            try:
                region = RegionOSM.objects.get(slug=area_slug)
                qs = qs.filter(comuna_osm_id=region.osm_id)
                region_info = {
                    'slug': region.slug,
                    'name': region.name,
                    'osm_id': region.osm_id
                }
            except RegionOSM.DoesNotExist:
                pass
        
        # Filtrar por tipo
        tipo_label = None
        if tipo:
            qs = qs.filter(tipo=tipo)
            tipo_label = get_localized_place_type_from_code(tipo)
        
        # Filtrar por características
        caracteristicas_activas = []
        caracteristicas_labels = {
            'delivery': _('Delivery'),
            'takeout': _('Para Llevar'),
            'dine_in': _('Comer en Local'),
            'outdoor_seating': _('Terraza'),
            'live_music': _('Música en Vivo'),
            'good_for_groups': _('Para Grupos'),
            'good_for_children': _('Para Niños'),
            'serves_cocktails': _('Cócteles'),
            'serves_wine': _('Vinos'),
            'serves_coffee': _('Café Especialidad'),
            'serves_dessert': _('Postres'),
            'wheelchair_accessible_entrance': _('Acceso Accesible'),
            'allows_dogs': _('Pet Friendly'),
            'accepts_credit_cards': _('Tarjetas de Crédito'),
            'reservable': _('Reservaciones'),
        }
        
        for caract in caracteristicas:
            if request.GET.get(caract) == 'true':
                qs = qs.filter(**{caract: True})
                caracteristicas_activas.append({
                    'key': caract,
                    'label': str(caracteristicas_labels.get(caract, caract))
                })
        
        # Ordenar
        qs = qs.prefetch_related('fotos').order_by('-es_destacado', '-weighted_rating', '-rating', 'nombre')
        
        # Paginación
        total_count = qs.count()
        paginator = Paginator(qs, per_page)
        page_obj = paginator.get_page(page)
        
        # Formatear resultados
        resultados = []
        for lugar in page_obj:
            primera_foto = lugar.fotos.first()
            resultados.append({
                'nombre': lugar.nombre,
                'slug': lugar.slug,
                'rating': lugar.rating or 0.0,
                'total_reviews': lugar.total_reviews or 0,
                'tipo': get_localized_place_type(lugar),
                **get_optimized_image_urls(primera_foto, 'thumb'),
                'es_destacado': lugar.es_destacado,
                'es_exclusivo': lugar.es_exclusivo,
                'precio': lugar.precio,
                'direccion': lugar.direccion,
                'url': reverse('explorer:lugares_detail', kwargs={'slug': lugar.slug}) if lugar.slug else None
            })
        
        # Construir mensaje
        if total_count == 0:
            if tipo_label and region_info:
                mensaje = _('No encontramos %(tipo)s en %(area)s') % {'tipo': tipo_label, 'area': region_info['name']}
            elif tipo_label:
                mensaje = _('No encontramos %(tipo)s') % {'tipo': tipo_label}
            elif region_info:
                mensaje = _('No encontramos lugares en %(area)s') % {'area': region_info['name']}
            else:
                mensaje = _('No encontramos lugares con estos filtros')
        else:
            if tipo_label and region_info:
                mensaje = ngettext(
                    '%(count)s %(tipo)s en %(area)s',
                    '%(count)s %(tipo)s en %(area)s',
                    total_count
                ) % {'count': total_count, 'tipo': tipo_label, 'area': region_info['name']}
            elif tipo_label:
                mensaje = ngettext(
                    '%(count)s %(tipo)s encontrados',
                    '%(count)s %(tipo)s encontrados',
                    total_count
                ) % {'count': total_count, 'tipo': tipo_label}
            elif region_info:
                mensaje = ngettext(
                    '%(count)s lugar en %(area)s',
                    '%(count)s lugares en %(area)s',
                    total_count
                ) % {'count': total_count, 'area': region_info['name']}
            else:
                mensaje = ngettext(
                    '%(count)s lugar encontrado',
                    '%(count)s lugares encontrados',
                    total_count
                ) % {'count': total_count}
        
        return JsonResponse({
            'success': True,
            'total': total_count,
            'lugares': resultados,
            'mensaje': mensaje,
            'filtros_aplicados': {
                'area': region_info,
                'tipo': tipo if tipo else None,
                'tipo_label': tipo_label,
                'caracteristicas': caracteristicas_activas
            },
            'paginacion': {
                'pagina_actual': page,
                'total_paginas': paginator.num_pages,
                'tiene_anterior': page_obj.has_previous(),
                'tiene_siguiente': page_obj.has_next(),
                'pagina_anterior': page_obj.previous_page_number() if page_obj.has_previous() else None,
                'pagina_siguiente': page_obj.next_page_number() if page_obj.has_next() else None,
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'error': _('Error en la búsqueda: %(err)s') % {'err': str(e)}
        }, status=500)


@require_GET
@rate_limit(requests_per_minute=30, key_prefix='near_me')
def lugares_cercanos_ajax_view(request):
    """API AJAX para lugares cercanos basados en geolocalización."""
    from django.http import JsonResponse
    from django.contrib.gis.geos import Point
    from django.contrib.gis.measure import D  # Para distancias
    from django.db import models
    from django.db.models import functions
    
    # Obtener coordenadas
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')
    radio = request.GET.get('radio', '0.8')  # Radio por defecto 800m
    
    # Obtener filtros opcionales
    tipo = request.GET.get('tipo', '').strip()
    caracteristica = request.GET.get('caracteristica', '').strip()
    
    if not lat or not lng:
        return JsonResponse({
            'error': 'Se requieren las coordenadas de latitud y longitud'
        }, status=400)
    
    try:
        # Convertir a float y validar
        lat = float(lat)
        lng = float(lng)
        radio = float(radio)
        
        # Validar rango de coordenadas (aproximado para Medellín)
        if not (5.0 <= lat <= 7.0) or not (-76.0 <= lng <= -74.0):
            return JsonResponse({
                'error': 'Las coordenadas parecen estar fuera del área de Medellín'
            }, status=400)
        
        # Crear punto de ubicación del usuario
        user_location = Point(lng, lat, srid=4326)
        
        # Buscar lugares cercanos - enfoque simplificado
        from django.contrib.gis.db.models.functions import Distance
        
        # Construir queryset base - excluir tipos irrelevantes y ratings muy bajos
        qs = Places.objects.filter(
            tiene_fotos=True,
            ubicacion__distance_lte=(user_location, D(km=radio))
        ).exclude(
            tipo__in=TIPOS_EXCLUIDOS
        ).filter(
            Q(rating__gte=2.0) | Q(rating__isnull=True)
        )
        
        # Aplicar filtro de tipo si existe
        if tipo:
            # Mapeo de tipos del frontend a tipos de la BD
            tipo_mapping = {
                'restaurant': ['restaurant', 'fine_dining_restaurant', 'seafood_restaurant', 
                              'italian_restaurant', 'mexican_restaurant', 'japanese_restaurant',
                              'chinese_restaurant', 'thai_restaurant', 'indian_restaurant',
                              'french_restaurant', 'american_restaurant', 'mediterranean_restaurant',
                              'korean_restaurant', 'vietnamese_restaurant', 'brazilian_restaurant',
                              'spanish_restaurant', 'greek_restaurant', 'pizza_restaurant',
                              'hamburger_restaurant', 'burger_restaurant', 'steak_house',
                              'fast_food_restaurant', 'vegetarian_restaurant', 'vegan_restaurant',
                              'brunch_restaurant', 'buffet_restaurant', 'food_court'],
                'bar': ['bar', 'pub', 'cocktail_bar', 'wine_bar', 'beer_bar', 'beer_garden',
                       'beer_hall', 'whiskey_bar', 'tequila_bar', 'sports_bar', 'hookah_bar',
                       'dive_bar', 'lounge'],
                'cafe': ['cafe', 'coffee_shop', 'tea_house', 'tea_room'],
                'bakery': ['bakery', 'pastry_shop', 'dessert_shop'],
                'night_club': ['night_club', 'nightclub', 'disco', 'dance_club'],
                'rooftop_bar': ['rooftop_bar', 'rooftop'],
                'karaoke': ['karaoke', 'karaoke_bar'],
                'sports_bar': ['sports_bar'],
                'casino': ['casino', 'gambling_house'],
                'bowling_alley': ['bowling_alley', 'bowling_center'],
                'spa': ['spa', 'wellness_center', 'sauna'],
                'art_gallery': ['art_gallery', 'gallery'],
                'museum': ['museum', 'history_museum', 'art_museum', 'science_museum'],
                'tourist_attraction': ['tourist_attraction', 'landmark', 'monument', 'historical_landmark'],
            }
            
            # Obtener tipos relacionados o usar el tipo directamente
            tipos_buscar = tipo_mapping.get(tipo, [tipo])
            qs = qs.filter(tipo__in=tipos_buscar)
        
        # Aplicar filtro de característica si existe
        if caracteristica:
            caracteristica_filters = {
                'outdoor_seating': {'outdoor_seating': True},
                'live_music': {'live_music': True},
                'good_for_groups': {'good_for_groups': True},
                'good_for_children': {'good_for_children': True},
                'delivery': {'delivery': True},
                'takeout': {'takeout': True},
                'dine_in': {'dine_in': True},
                'reservable': {'reservable': True},
                'serves_cocktails': {'serves_cocktails': True},
                'serves_wine': {'serves_wine': True},
                'serves_coffee': {'serves_coffee': True},
                'serves_dessert': {'serves_dessert': True},
                'allows_dogs': {'allows_dogs': True},
                'wheelchair_accessible_entrance': {'wheelchair_accessible_entrance': True},
                'accepts_credit_cards': {'accepts_credit_cards': True},
            }
            
            if caracteristica in caracteristica_filters:
                qs = qs.filter(**caracteristica_filters[caracteristica])
        
        lugares_cercanos = qs.prefetch_related('fotos').annotate(
            distancia_metros=Distance('ubicacion', user_location)
        ).order_by('distancia_metros', '-es_destacado', '-weighted_rating', '-rating')[:15]
        
        # Formatear resultados
        resultados = []
        for lugar in lugares_cercanos:
            primera_foto = lugar.fotos.first()
            resultados.append({
                'nombre': lugar.nombre,
                'slug': lugar.slug,
                'rating': lugar.rating or 0.0,
                'total_reviews': lugar.total_reviews or 0,
                'tipo': get_localized_place_type(lugar),
                **get_optimized_image_urls(primera_foto, 'thumb'),
                'es_destacado': lugar.es_destacado,
                'es_exclusivo': lugar.es_exclusivo,
                # URL resuelta por Django según idioma actual
                'url': reverse('explorer:lugares_detail', kwargs={'slug': lugar.slug}) if lugar.slug else None,
                'distancia': round(lugar.distancia_metros.km, 2) if hasattr(lugar, 'distancia_metros') and lugar.distancia_metros else None,
                'direccion': lugar.direccion
            })
        
        count = len(resultados)
        distancia_str = f"{int(radio * 1000)}m" if radio < 1 else f"{radio}km"
        
        # Labels traducidos para tipos
        tipo_labels = {
            'restaurant': _('Restaurantes'),
            'bar': _('Bares'),
            'cafe': _('Cafés'),
            'bakery': _('Panaderías'),
            'night_club': _('Discotecas'),
            'rooftop_bar': _('Rooftops'),
            'karaoke': _('Karaokes'),
            'sports_bar': _('Bares Deportivos'),
            'casino': _('Casinos'),
            'bowling_alley': _('Boleras'),
            'spa': _('Spas'),
            'art_gallery': _('Galerías de Arte'),
            'museum': _('Museos'),
            'tourist_attraction': _('Atracciones Turísticas'),
        }
        
        # Labels traducidos para características
        caracteristica_labels = {
            'outdoor_seating': _('Terraza'),
            'live_music': _('Música en Vivo'),
            'good_for_groups': _('Para Grupos'),
            'good_for_children': _('Para Niños'),
            'delivery': _('Delivery'),
            'takeout': _('Para Llevar'),
            'dine_in': _('Comer en Local'),
            'reservable': _('Reservaciones'),
            'serves_cocktails': _('Cócteles'),
            'serves_wine': _('Vinos'),
            'serves_coffee': _('Café Especialidad'),
            'serves_dessert': _('Postres'),
            'allows_dogs': _('Pet Friendly'),
            'wheelchair_accessible_entrance': _('Acceso Accesible'),
            'accepts_credit_cards': _('Tarjetas de Crédito'),
        }
        
        # Construir información de filtros aplicados
        filtros_aplicados = {
            'tipo': tipo if tipo else None,
            'tipo_label': tipo_labels.get(tipo, None) if tipo else None,
            'caracteristica': caracteristica if caracteristica else None,
            'caracteristica_label': caracteristica_labels.get(caracteristica, None) if caracteristica else None,
            'radio_km': radio,
            'radio_display': distancia_str,
        }
        
        # Mensaje dinámico basado en filtros reales
        tipo_label = filtros_aplicados['tipo_label']
        caract_label = filtros_aplicados['caracteristica_label']
        
        if count == 0:
            # Sin resultados
            if tipo_label and caract_label:
                mensaje = _('No encontramos %(tipo)s con %(caract)s en un radio de %(dist)s') % {
                    'tipo': tipo_label, 'caract': caract_label, 'dist': distancia_str
                }
            elif tipo_label:
                mensaje = _('No encontramos %(tipo)s en un radio de %(dist)s') % {
                    'tipo': tipo_label, 'dist': distancia_str
                }
            elif caract_label:
                mensaje = _('No encontramos lugares con %(caract)s en un radio de %(dist)s') % {
                    'caract': caract_label, 'dist': distancia_str
                }
            else:
                mensaje = _('No encontramos lugares en un radio de %(dist)s') % {'dist': distancia_str}
        else:
            # Con resultados
            if tipo_label and caract_label:
                mensaje = ngettext(
                    '%(count)s %(tipo)s con %(caract)s a menos de %(dist)s',
                    '%(count)s %(tipo)s con %(caract)s a menos de %(dist)s',
                    count
                ) % {'count': count, 'tipo': tipo_label, 'caract': caract_label, 'dist': distancia_str}
            elif tipo_label:
                mensaje = ngettext(
                    '%(count)s %(tipo)s a menos de %(dist)s',
                    '%(count)s %(tipo)s a menos de %(dist)s',
                    count
                ) % {'count': count, 'tipo': tipo_label, 'dist': distancia_str}
            elif caract_label:
                mensaje = ngettext(
                    '%(count)s lugar con %(caract)s a menos de %(dist)s',
                    '%(count)s lugares con %(caract)s a menos de %(dist)s',
                    count
                ) % {'count': count, 'caract': caract_label, 'dist': distancia_str}
            else:
                mensaje = ngettext(
                    '%(count)s lugar a menos de %(dist)s',
                    '%(count)s lugares a menos de %(dist)s',
                    count
                ) % {'count': count, 'dist': distancia_str}

        return JsonResponse({
            'success': True,
            'total': count,
            'lugares': resultados,
            'filtros_aplicados': filtros_aplicados,
            'ubicacion_usuario': {
                'lat': lat,
                'lng': lng,
                'radio': radio
            },
            'mensaje': mensaje
        })
        
    except ValueError:
        return JsonResponse({
            'error': _('Las coordenadas proporcionadas no son válidas')
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': _('Error al buscar lugares cercanos: %(err)s') % {'err': str(e)}
        }, status=500)


# ────────────────────────────────────────────────────────────────────────
# Newsletter Views
# ────────────────────────────────────────────────────────────────────────

def get_client_ip(request):
    """Obtiene la IP real del cliente."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

@require_GET
def lugares_cercanos_ajax(request, slug):
    """AJAX endpoint para cargar lugares cercanos."""
    try:
        lugar = Places.objects.filter(tiene_fotos=True, slug=slug).first()
        if not lugar:
            return JsonResponse({'error': _('Lugar no encontrado')}, status=404)
        
        view = PlaceDetailView()
        lugares_cercanos = view._get_lugares_cercanos(lugar, distance=1000, limit=6) if lugar.ubicacion else []
        
        # Serializar lugares
        data = []
        for lugar_cercano in lugares_cercanos:
            # Calcular distancia en km
            distancia_km = None
            if hasattr(lugar_cercano, 'distancia_metros') and lugar_cercano.distancia_metros:
                distancia_km = round(lugar_cercano.distancia_metros.km, 2)
            
            foto = lugar_cercano.cached_fotos[0] if lugar_cercano.cached_fotos else None
            data.append({
                'id': lugar_cercano.id,
                'nombre': lugar_cercano.nombre,
                'slug': lugar_cercano.slug,
                'tipo': get_localized_place_type(lugar_cercano),
                'rating': lugar_cercano.rating,
                'total_reviews': lugar_cercano.total_reviews or 0,
                'es_destacado': lugar_cercano.es_destacado,
                'es_exclusivo': lugar_cercano.es_exclusivo,
                **get_optimized_image_urls(foto, 'thumb'),
                'url': reverse('explorer:lugares_detail', args=[lugar_cercano.slug]) if lugar_cercano.slug else None,
                'distancia_km': distancia_km,
            })
        
        return JsonResponse({'lugares': data})
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET  
def lugares_similares_ajax(request, slug):
    """AJAX endpoint para cargar lugares similares."""
    try:
        lugar = Places.objects.filter(tiene_fotos=True, slug=slug).first()
        if not lugar:
            return JsonResponse({'error': _('Lugar no encontrado')}, status=404)
        
        view = PlaceDetailView()
        lugares_similares = view._get_lugares_similares(lugar, limit=6)
        
        # Serializar lugares
        data = []
        for lugar_similar in lugares_similares:
            foto = lugar_similar.cached_fotos[0] if lugar_similar.cached_fotos else None
            data.append({
                'id': lugar_similar.id,
                'nombre': lugar_similar.nombre,
                'slug': lugar_similar.slug,
                'tipo': get_localized_place_type(lugar_similar),
                'rating': lugar_similar.rating,
                'total_reviews': lugar_similar.total_reviews or 0,
                'es_destacado': lugar_similar.es_destacado,
                'es_exclusivo': lugar_similar.es_exclusivo,
                **get_optimized_image_urls(foto, 'thumb'),
                'url': reverse('explorer:lugares_detail', args=[lugar_similar.slug]) if lugar_similar.slug else None,
            })
        
        return JsonResponse({'lugares': data})
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_GET
def lugares_comuna_ajax(request, slug):
    """AJAX endpoint para cargar lugares de la misma comuna."""
    try:
        lugar = Places.objects.filter(tiene_fotos=True, slug=slug).first()
        if not lugar:
            return JsonResponse({'error': _('Lugar no encontrado')}, status=404)
        
        view = PlaceDetailView()
        lugares_comuna = view._get_lugares_misma_comuna(lugar, limit=6) if lugar.comuna_osm_id else []
        
        # Serializar lugares
        data = []
        for lugar_comuna_item in lugares_comuna:
            foto = lugar_comuna_item.cached_fotos[0] if lugar_comuna_item.cached_fotos else None
            data.append({
                'id': lugar_comuna_item.id,
                'nombre': lugar_comuna_item.nombre,
                'slug': lugar_comuna_item.slug,
                'tipo': get_localized_place_type(lugar_comuna_item),
                'rating': lugar_comuna_item.rating,
                'total_reviews': lugar_comuna_item.total_reviews or 0,
                'es_destacado': lugar_comuna_item.es_destacado,
                'es_exclusivo': lugar_comuna_item.es_exclusivo,
                **get_optimized_image_urls(foto, 'thumb'),
                'url': reverse('explorer:lugares_detail', args=[lugar_comuna_item.slug]) if lugar_comuna_item.slug else None,
            })
        
        return JsonResponse({'lugares': data, 'comuna_nombre': lugar.comuna.name if hasattr(lugar, 'comuna') and lugar.comuna else 'esta zona'})
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500) 


def _build_genai_client():
	"""Crea SIEMPRE un cliente Vertex AI (camino único)."""
	from google import genai as genai_vertex
	return ('genai', genai_vertex)

@require_GET
@rate_limit(requests_per_minute=20, key_prefix='semantic')
def semantic_search_ajax(request):
	from django.http import JsonResponse
	from google import genai as vertex_genai
	from google.genai import types as vertex_types

	query = request.GET.get('q', '').strip()
	top_k = int(request.GET.get('top', '12') or 12)
	if not query:
		return JsonResponse({'success': False, 'error': _('Parámetro q requerido')}, status=400)
	try:
		client = vertex_genai.Client(vertexai=True, project='vivemedellin', location='us-central1')
		result = client.models.embed_content(
			model='gemini-embedding-001',
			contents=query,
			config=vertex_types.EmbedContentConfig(
				output_dimensionality=768,
				task_type='RETRIEVAL_QUERY'
			)
		)
		query_embedding = result.embeddings[0].values
	except Exception as e:
		return JsonResponse({'success': False, 'error': f'Error generando embedding: {e}'}, status=500)

	qs = (
		Places.objects
		.extra(select={"score": "1 - (embedding <=> %s::vector)"}, select_params=[query_embedding])
		.filter(tiene_fotos=True, embedding__isnull=False)
		.exclude(tipo__in=TIPOS_EXCLUIDOS)  # Excluir tipos irrelevantes
		.filter(Q(rating__gte=2.0) | Q(rating__isnull=True))  # Excluir ratings muy bajos
		.order_by('-score')
		.prefetch_related('fotos')
	)[:top_k]

	resp = []
	for lugar in qs:
		foto = lugar.fotos.first()
		resp.append({
			'nombre': lugar.nombre,
			'slug': lugar.slug,
			'tipo': get_localized_place_type(lugar),
			'direccion': lugar.direccion,
			'rating': lugar.rating or 0.0,
			**get_optimized_image_urls(foto, 'thumb'),
			'score': round(getattr(lugar, 'score', 0.0), 4),
			# URL resuelta por Django según idioma actual
			'url': reverse('explorer:lugares_detail', kwargs={'slug': lugar.slug}) if lugar.slug else None,
			'es_destacado': bool(getattr(lugar, 'es_destacado', False)),
			'es_exclusivo': bool(getattr(lugar, 'es_exclusivo', False)),
			'total_reviews': lugar.total_reviews or 0,
		})
	return JsonResponse({'success': True, 'query': query, 'total': len(resp), 'lugares': resp}) 


class SemanticSearchView(View):
    def get(self, request):
        # Forzar Vertex AI como en la versión original solicitada
        from google import genai as vertex_genai
        from google.genai import types as vertex_types

        query = request.GET.get("q", "").strip()
        as_json = request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("json") == "1"

        resultados = []
        error = ""

        if query:
            try:
                genai_client = vertex_genai.Client(vertexai=True, project="vivemedellin", location="us-central1")
                result = genai_client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=query,
                    config=vertex_types.EmbedContentConfig(
                        output_dimensionality=768,
                        task_type="RETRIEVAL_QUERY"
                    )
                )
                query_embedding = result.embeddings[0].values

                lugares_qs = Places.objects.extra(
                    select={"score": "1 - (embedding <=> %s::vector)"},
                    select_params=[query_embedding]
                ).filter(
                    embedding__isnull=False,
                    tiene_fotos=True
                ).order_by("-score")

                lugares = lugares_qs.prefetch_related("fotos")[:10]

                resultados = []
                for l in lugares:
                    primera_foto = l.get_primera_foto()
                    comuna_nombre = l.comuna.name if hasattr(l, "comuna") and l.comuna else None
                    resultados.append({
                        "nombre": l.nombre,
                        "tipo": get_localized_place_type(l),
                        "direccion": l.direccion,
                        "rating": l.rating,
                        "score": round(getattr(l, "score", 0.0), 3),
                        "slug": l.slug,
                        **get_optimized_image_urls(primera_foto, 'thumb'),
                        "es_destacado": bool(getattr(l, "es_destacado", False)),
                        "es_exclusivo": bool(getattr(l, "es_exclusivo", False)),
                        "precio": getattr(l, "precio", None),
                        "abierto_ahora": getattr(l, "abierto_ahora", None),
                        "comuna_nombre": comuna_nombre,
                        "telefono": getattr(l, "telefono", None),
                        "sitio_web": getattr(l, "sitio_web", None),
                    })
            except Exception as e:
                error = str(e)

        if as_json:
            return JsonResponse({"resultados": resultados, "error": error})
        else:
            return render(request, "semantic_results.html", {
                "query": query,
                "resultados": resultados,
                "error": error
            })


# ────────────────────────────────────────────────────────────────────────
# Traducción de Reseñas (Proxy con caché)
# ────────────────────────────────────────────────────────────────────────

def _cache_key_translation(text: str, target: str) -> str:
    digest = sha1((text + "|" + target).encode("utf-8")).hexdigest()
    return f"review_translation_{target}_{digest}"


def _rate_limit_key(ip: str) -> str:
    return f"translate_rl_{ip}"


def _normalize_review_text(text: str) -> str:
    r"""Normaliza saltos de línea y caracteres de control en reseñas.
    - Convierte secuencias literales \u000A / \U000A (con o sin espacios) a \n
    - Elimina CR, normaliza espacios y controla longitud
    """
    if not text:
        return ""
    s = str(text)
    # Variantes de secuencias escapadas
    s = re.sub(r"\\\s*u000a", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"\\\s*n", "\n", s)
    # Normalizar CR y caracteres de control
    s = s.replace("\r", "")
    s = re.sub(r"[\t\x00-\x08\x0b\x0c\x0e-\x1f]", " ", s)
    # Compactar saltos/espacios excesivos
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"\s{3,}", "  ", s)
    # Limitar tamaño
    if len(s) > 4500:
        s = s[:4500]
    return s.strip()


def _guess_lang_es_en(text: str) -> str:
    """Heurística simple ES/EN para evitar 'AUTO' en MyMemory.
    Devuelve 'ES' o 'EN'.
    """
    if not text or len(text.strip()) < 3:
        return 'ES'  # Por defecto español para textos muy cortos
    
    lowered = text.lower()
    
    # Señales de español: tildes, eñes, signos de ¿¡
    if re.search(r"[áéíóúñ¿¡]", lowered):
        return 'ES'
    
    # Stopwords de español (más completo)
    spanish_tokens = {
        " el ", " la ", " de ", " y ", " en ", " los ", " las ", " una ", " un ", 
        " que ", " con ", " para ", " por ", " es ", " muy ", " bien ", " mal ",
        " pero ", " como ", " más ", " del ", " al ", " este ", " esta ", " eso ",
        " bueno ", " excelente ", " rico ", " delicioso ", " recomendado ", " lugar "
    }
    padded = f" {lowered} "
    spanish_matches = sum(1 for tok in spanish_tokens if tok in padded)
    
    # Stopwords de inglés
    english_tokens = {
        " the ", " and ", " is ", " are ", " was ", " were ", " this ", " that ",
        " good ", " great ", " nice ", " food ", " place ", " very ", " but ",
        " with ", " for ", " from ", " have ", " has ", " been ", " really "
    }
    english_matches = sum(1 for tok in english_tokens if tok in padded)
    
    # Decidir basado en qué idioma tiene más coincidencias
    if spanish_matches > english_matches:
        return 'ES'
    elif english_matches > spanish_matches:
        return 'EN'
    
    # Por defecto español (contexto de Colombia)
    return 'ES'


def _mymemory_translate(text: str, source: str, target: str) -> str | None:
    """Traduce texto usando MyMemory API.
    
    Limitaciones de MyMemory:
    - Textos muy cortos (< 3 chars) a veces fallan
    - Textos muy largos (> 500 chars) requieren cuenta premium
    """
    # Textos muy cortos: retornar sin traducir
    if len(text.strip()) < 3:
        return text
    
    # Textos muy largos: truncar a 500 caracteres (límite gratuito de MyMemory)
    max_length = 500
    truncated = False
    original_text = text
    if len(text) > max_length:
        # Intentar cortar en un espacio para no romper palabras
        cut_point = text.rfind(' ', 0, max_length)
        if cut_point > max_length * 0.7:  # Si encontramos un espacio razonable
            text = text[:cut_point]
        else:
            text = text[:max_length]
        truncated = True
    
    params = {
        "q": text,
        "langpair": f"{source}|{target}",
    }
    url = "https://api.mymemory.translated.net/get?" + urlencode(params)
    try:
        import json as _json
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = _json.loads(resp.read().decode("utf-8", errors="ignore"))
            status = int(data.get("responseStatus", 500))
            translated = (data.get("responseData") or {}).get("translatedText") or ""
            
            # Rechazar mensajes de error de la API
            if "INVALID SOURCE LANGUAGE" in translated or "'AUTO'" in translated:
                return None
            
            # Rechazar si la respuesta es igual al input (no se tradujo)
            if translated.strip().lower() == text.strip().lower():
                return None
            
            if status == 200 and translated:
                # Si truncamos, agregar indicador
                if truncated:
                    translated = translated + "..."
                return translated
    except Exception:
        return None
    return None


def _translate_with_mymemory(text: str, target: str) -> str | None:
    # Usar MyMemory como fallback sin credenciales (POC). Producción debería usar proveedor de pago.
    target = (target or 'en').upper()
    source = _guess_lang_es_en(text)
    if source == target:
        return text
    # Intento 1: con fuente detectada
    out = _mymemory_translate(text, source, target)
    if out:
        return out
    # Intento 2: invertir fuente común (ES<->EN)
    alt_source = 'EN' if source == 'ES' else 'ES'
    out = _mymemory_translate(text, alt_source, target)
    if out:
        return out
    return None


@require_POST
@rate_limit(requests_per_minute=15, key_prefix='translate')
def translate_review_api(request):
    """Proxy seguro para traducir texto de reseñas con caché y rate limit.

    Body JSON: { text: str, target: 'en' }
    """
    try:
        import json as _json
        payload = _json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        payload = {}

    text = _normalize_review_text(payload.get("text") or "")
    target = (payload.get("target") or "en").strip().lower()

    if not text:
        return JsonResponse({"success": False, "error": _("Texto vacío")}, status=400)

    # Rate limit básico por IP (20 solicitudes / 60s)
    ip = request.META.get("REMOTE_ADDR", "")
    rl_key = _rate_limit_key(ip)
    window = 60
    limit = 20
    current = cache.get(rl_key) or 0
    if current >= limit:
        return JsonResponse({"success": False, "error": _("Límite de traducciones temporal alcanzado. Intenta más tarde.")}, status=429)
    cache.set(rl_key, current + 1, window)

    # Cache de traducción
    ck = _cache_key_translation(text, target)
    cached = cache.get(ck)
    if cached:
        return JsonResponse({"success": True, "text_translated": cached, "cached": True})

    # Traducir (fallback MyMemory)
    translated = _translate_with_mymemory(text, target)
    if not translated:
        # Si falla, devolvemos original con flag
        return JsonResponse({"success": True, "text_translated": text, "detected_same": True})

    cache.set(ck, translated, 60 * 60 * 24 * 14)  # 14 días
    return JsonResponse({"success": True, "text_translated": translated, "cached": False})


# Funciones de API de reseñas (comentadas - Google solo envía 5 reseñas)
# def _serialize_reviews(lugar: Places) -> list[dict]:
# 	items = []
# 	if not lugar or not lugar.reviews:
# 		return items
# 	try:
# 		for review in lugar.reviews:
# 			texto_review = review.get('text', '')
# 			if isinstance(texto_review, dict):
# 				texto_review = texto_review.get('text', '') if texto_review else ''
# 			elif isinstance(texto_review, list):
# 				texto_review = ' '.join(str(item) for item in texto_review if item)
# 			if texto_review:
# 				texto_review = str(texto_review).strip().replace('\\n', '\n').replace('\\r', '\r').replace('\\"', '"').replace("\\'", "'")
# 			fecha_review = review.get('publishTime', '') or review.get('time', '') or review.get('relativePublishTimeDescription', '')
# 			if fecha_review and str(fecha_review).isdigit():
# 				from datetime import datetime
# 				try:
# 					fecha_review = datetime.fromtimestamp(int(fecha_review)).strftime('%d/%m/%Y')
# 				except Exception:
# 					fecha_review = 'Fecha no disponible'
# 			elif not fecha_review:
# 				fecha_review = 'Fecha no disponible'
# 			autor_review = 'Anónimo'
# 			if review.get('authorAttribution'):
# 				author_attr = review['authorAttribution']
# 				if isinstance(author_attr, dict):
# 					autor_review = author_attr.get('displayName', 'Anónimo')
# 				else:
# 					autor_review = str(author_attr)
# 			elif review.get('author_name'):
# 				autor_review = review['author_name']
# 			items.append({
# 				'autor': autor_review,
# 				'rating': int(review.get('rating', 0)) if review.get('rating') else 0,
# 				'texto': texto_review,
# 				'fecha': fecha_review,
# 				'foto_perfil': review.get('profile_photo_url', '')
# 			})
# 	except Exception:
# 		pass
# 	return items


# def reviews_lugar_ajax(request, slug):
# 	from django.shortcuts import get_object_or_404
# 	offset = int(request.GET.get('offset') or 0)
# 	limit = int(request.GET.get('limit') or 10)
# 	limit = max(1, min(limit, 50))
# 	lugar = get_object_or_404(Places, slug=slug)
# 	all_reviews = _serialize_reviews(lugar)
# 	total = len(all_reviews)
# 	chunk = all_reviews[offset:offset+limit]
# 	return JsonResponse({'success': True, 'total': total, 'count': len(chunk), 'offset': offset, 'limit': limit, 'reviews': chunk})


# ────────────────────────────────────────────────────────────────────────
# Páginas Legales (Privacy Policy, Terms, Contact)
# Requeridas para Google AdSense
# ────────────────────────────────────────────────────────────────────────

@require_GET
def privacy_policy(request):
    """Página de Política de Privacidad."""
    return render(request, 'legal/privacy_policy.html')


@require_GET
def terms(request):
    """Página de Términos y Condiciones."""
    return render(request, 'legal/terms.html')


@require_GET
def contact(request):
    """Página de Contacto con formulario."""
    return render(request, 'legal/contact.html')

