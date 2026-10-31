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
from django.http import Http404, JsonResponse
from django.utils import timezone
import json
import ipaddress
import random
from pgvector.django import CosineDistance
from django.views import View
from django.utils.translation import gettext as _, ngettext, get_language
from explorer.utils.media_urls import resolve_media_url
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


def adsense_allowed_for_place(lugar):
    """
    Habilita anuncios solo cuando el lugar no es sensible para AdSense.
    """
    return not bool(getattr(lugar, "is_sensitive_for_ads", False))


def adsense_allowed_for_search_query(query):
    """Desactiva anuncios si la consulta coincide con palabras sensibles."""
    if not query:
        return True
    q = query.strip().lower()
    if not q:
        return True
    keywords = getattr(settings, "ADSENSE_SENSITIVE_KEYWORDS", []) or []
    return not any(kw and kw.lower() in q for kw in keywords)


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
    
    thumb = resolve_media_url(getattr(foto, 'imagen_miniatura', None) or '') or ''
    medium = resolve_media_url(getattr(foto, 'imagen_mediana', None) or '') or ''
    full = resolve_media_url(getattr(foto, 'imagen', None) or '') or ''
    
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
        ).para_buscador().prefetch_related(
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


# Fotos de la zona, no de un local. Todas son archivos de Wikimedia Commons
# (dominio público o Creative Commons). La miniatura la sirve su CDN.
FOTOS_ZONAS_PUBLICAS = {
    "el-poblado": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/77/Barrio_El_Poblado._El_Poblado_neighborhood.jpg/960px-Barrio_El_Poblado._El_Poblado_neighborhood.jpg",
    "laureles-estadio": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/64/Estadio_Atanasio_Girardot_2024.jpg/960px-Estadio_Atanasio_Girardot_2024.jpg",
    "aranjuez": "https://thumb.wikimedia.org/wikipedia/commons/thumb/4/45/Aranjuez%2C_Medell%C3%ADn%2C_Antioquia%2C_Colombia_-_panoramio.jpg/960px-Aranjuez%2C_Medell%C3%ADn%2C_Antioquia%2C_Colombia_-_panoramio.jpg",
    "belen": "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/17/Bel%C3%A9n%2C_Medell%C3%ADn_en_las_horas_de_la_ma%C3%B1ana_2025.jpg/960px-Bel%C3%A9n%2C_Medell%C3%ADn_en_las_horas_de_la_ma%C3%B1ana_2025.jpg",
    "buenos-aires": "https://thumb.wikimedia.org/wikipedia/commons/thumb/5/5f/Cl%C3%ADnica_Sagrado_Coraz%C3%B3n_-_medell%C3%ADn.JPG/960px-Cl%C3%ADnica_Sagrado_Coraz%C3%B3n_-_medell%C3%ADn.JPG",
    "castilla": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/fa/CASTILLA%2C_MEDELLIN_-_panoramio.jpg/960px-CASTILLA%2C_MEDELLIN_-_panoramio.jpg",
    "doce-de-octubre": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/75/Cerro_Picacho-Medellin.jpg/960px-Cerro_Picacho-Medellin.jpg",
    "guayabal": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/76/2018_Medell%C3%ADn_Avenida_Guayabal_a_la_altura_de_la_calle_14.jpg/960px-2018_Medell%C3%ADn_Avenida_Guayabal_a_la_altura_de_la_calle_14.jpg",
    "la-america": "https://thumb.wikimedia.org/wikipedia/commons/thumb/8/87/La_Am%C3%A9rica%2C_Medell%C3%ADn%2C_Colombia.jpg/960px-La_Am%C3%A9rica%2C_Medell%C3%ADn%2C_Colombia.jpg",
    "la-candelaria": "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ed/Medell%C3%ADn%2C_Plaza_Botero%2C_2023-07_CN-01.jpg/960px-Medell%C3%ADn%2C_Plaza_Botero%2C_2023-07_CN-01.jpg",
    "manrique": "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/dc/Empieza_a_llover_en_Medellin_desde_la_45_Manrique_-_panoramio.jpg/960px-Empieza_a_llover_en_Medellin_desde_la_45_Manrique_-_panoramio.jpg",
    "popular": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/7f/Vista_a%C3%A9rea_del_Barrio_La_Avanzada%2C_Comuna_1_-_Popular%2C_Medell%C3%ADn.jpg/960px-Vista_a%C3%A9rea_del_Barrio_La_Avanzada%2C_Comuna_1_-_Popular%2C_Medell%C3%ADn.jpg",
    "robledo": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f3/Medell%C3%ADn%2C_Robledo%2C_2023-07_CN-02.jpg/960px-Medell%C3%ADn%2C_Robledo%2C_2023-07_CN-02.jpg",
    "san-javier": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/61/Comuna_13_San_Javier%2C_Medell%C3%ADn%2C_abril_de_2017.jpg/960px-Comuna_13_San_Javier%2C_Medell%C3%ADn%2C_abril_de_2017.jpg",
    "santa-cruz": "https://thumb.wikimedia.org/wikipedia/commons/thumb/4/44/Barrio_Santo_Domingo_Savio.JPG/960px-Barrio_Santo_Domingo_Savio.JPG",
    "villa-hermosa": "https://thumb.wikimedia.org/wikipedia/commons/thumb/9/90/2018_Medell%C3%ADn_barrio_Villa_Turbay_-_L%C3%ADnea_H_del_Metrocable_entre_las_estaciones_Las_Torres_y_Villa_Sierra.jpg/960px-2018_Medell%C3%ADn_barrio_Villa_Turbay_-_L%C3%ADnea_H_del_Metrocable_entre_las_estaciones_Las_Torres_y_Villa_Sierra.jpg",
    "envigado": "https://thumb.wikimedia.org/wikipedia/commons/thumb/e/e0/Envigado_above.jpg/960px-Envigado_above.jpg",
    "guatape": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/74/Calle_de_Guatap%C3%A9%2C_Antioquia.jpg/960px-Calle_de_Guatap%C3%A9%2C_Antioquia.jpg",
    "itagui": "https://thumb.wikimedia.org/wikipedia/commons/thumb/8/81/CAMI-Itagui.JPG/960px-CAMI-Itagui.JPG",
    "la-estrella": "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/13/Vista_en_perspectiva_de_la_Estaci%C3%B3n_del_Ferrocarril_La_Tablaza._La_Estrella_%28Antioquia%29._Colombia.JPG/960px-Vista_en_perspectiva_de_la_Estaci%C3%B3n_del_Ferrocarril_La_Tablaza._La_Estrella_%28Antioquia%29._Colombia.JPG",
    "rionegro": "https://thumb.wikimedia.org/wikipedia/commons/thumb/0/0a/Concatedral_de_San_Nicol%C3%A1s_el_Magno_de_Rionegro_-_exterior_3.jpg/960px-Concatedral_de_San_Nicol%C3%A1s_el_Magno_de_Rionegro_-_exterior_3.jpg",
    "sabaneta": "https://upload.wikimedia.org/wikipedia/commons/2/2c/Sabaneta_parque_central.jpg",
}


def _asignar_fotos_zonas(regiones):
    """Foto pública de cada zona. Si no hay una, la tarjeta queda sin imagen de local."""
    for region in regiones or []:
        region.foto = FOTOS_ZONAS_PUBLICAS.get(region.slug) or ""


# ────────────────────────────────────────────────────────────────────────
# Vistas Principales
# ────────────────────────────────────────────────────────────────────────

class HomeView(TemplateView):
    """Vista de inicio que muestra lugares agrupados por regiones OSM."""
    template_name = "home.html"

    def get_template_names(self):
        from django.conf import settings
        if getattr(settings, "VIBE_V4", False):
            return ["home_v4.html"]
        return [self.template_name]
    
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
        context['lugares_imperdibles'] = self._get_lugares_imperdibles()
        context['guias_home'] = self._get_guias_home()
        return context

    def _get_guias_home(self):
        from .models import CuratedGuide
        return list(
            CuratedGuide.objects.filter(publicado=True)
            .select_related("zona")
            .order_by("orden", "-fecha_creacion")
        )

    def _get_lugares_imperdibles(self):
        """
        Lista corta rotativa: mezcla aleatoria por request dentro de un pool
        de lugares de alta calidad (rating alto + popularidad).
        """
        lang = (get_language() or "es").lower()
        pool_key = f"home_lugares_imperdibles_pool_v4_{lang}"
        imperdibles_pool = cache.get(pool_key)

        if imperdibles_pool is None:
            candidatos = (
                Places.objects.filter(
                    tiene_fotos=True,
                    slug__isnull=False,
                    rating__gte=4.4,
                ).para_buscador()
                .exclude(slug__exact="")
                .exclude(rating__isnull=True)
                .only(
                    "nombre", "slug", "tipo", "rating", "total_reviews",
                    "es_destacado", "show_in_home", "comuna_osm_id",
                )
                .prefetch_related(
                    Prefetch(
                        "fotos",
                        queryset=Foto.objects.only("imagen", "imagen_mediana", "imagen_miniatura")[:1],
                        to_attr="cached_fotos",
                    )
                )
                .order_by("-weighted_rating", "-total_reviews", "-rating")[:80]
            )

            imperdibles_pool = []
            for lugar in candidatos:
                # Evita contenido sensible en una sección de alto tráfico.
                if getattr(lugar, "is_sensitive_for_ads", False):
                    continue

                score_popular = (
                    bool(getattr(lugar, "show_in_home", False))
                    or bool(getattr(lugar, "es_destacado", False))
                    or (getattr(lugar, "total_reviews", 0) or 0) >= 60
                )
                if not score_popular:
                    continue

                foto = lugar.cached_fotos[0] if getattr(lugar, "cached_fotos", None) else lugar.fotos.first()
                image_data = get_optimized_image_urls(foto, "thumb")
                zona = ""
                comuna = lugar.comuna
                if comuna is not None:
                    zona = getattr(comuna, "name", "") or ""
                imperdibles_pool.append({
                    "nombre": lugar.nombre,
                    "slug": lugar.slug,
                    "tipo": get_localized_place_type(lugar),
                    "rating": round(float(lugar.rating or 0), 1),
                    "total_reviews": lugar.total_reviews or 0,
                    "zona": zona,
                    "imagen": image_data.get("imagen"),
                    "imagen_full": image_data.get("imagen_full"),
                })

            cache.set(pool_key, imperdibles_pool, 3600)

        if not imperdibles_pool:
            return []

        # Rotación por request: muestra una muestra aleatoria del pool.
        sample_size = min(8, len(imperdibles_pool))
        return random.sample(imperdibles_pool, sample_size)

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

        comunas_medellin_chips = comunas_medellin
        otras_regiones_chips = otras_regiones
        _asignar_fotos_zonas(regiones_areas)
        
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


def _paginas_rastreables(actual, total):
    """Saltos cortos y largos para que cualquier página quede a pocos clics de la primera."""
    paginas = {1, total, actual}
    for salto in (1, 2, 10, 50, 100):
        paginas.update((actual - salto, actual + salto))
    return sorted(p for p in paginas if 1 <= p <= total)


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
        ).para_buscador().prefetch_related('fotos').order_by('-es_destacado', '-weighted_rating', '-rating', 'nombre')

        # Búsqueda por nombre
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(nombre__icontains=q)
        
        # Filtro por tipo de lugar (desde dropdown del navbar)
        tipo = self.request.GET.get('tipo')
        if tipo:
            qs = qs.filter(tipo=tipo)
            
        # Filtro por área (slug AJAX) o comuna (osm_id SSR)
        area_slug = (self.request.GET.get('area') or '').strip()
        comuna = self.request.GET.get('comuna')
        if area_slug:
            try:
                region = RegionOSM.objects.get(slug=area_slug)
                qs = qs.filter(comuna_osm_id=region.osm_id)
            except RegionOSM.DoesNotExist:
                pass
        elif comuna:
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

        # Near me: ?lat=&lng= (después de geolocalizar desde ?cerca=1)
        lat = self.request.GET.get('lat')
        lng = self.request.GET.get('lng')
        if lat and lng:
            try:
                from django.contrib.gis.geos import Point
                from django.contrib.gis.db.models.functions import Distance
                from django.contrib.gis.measure import D
                lat_f = float(lat)
                lng_f = float(lng)
                radio_km = float(self.request.GET.get('radio', '3') or 3)
                radio_km = max(0.5, min(radio_km, 15))
                if 5.0 <= lat_f <= 7.0 and -76.0 <= lng_f <= -74.0:
                    user_point = Point(lng_f, lat_f, srid=4326)
                    qs = (
                        qs.filter(ubicacion__distance_lte=(user_point, D(km=radio_km)))
                        .annotate(distancia_m=Distance('ubicacion', user_point))
                        .order_by('distancia_m', '-es_destacado', '-weighted_rating', '-rating')
                    )
            except (TypeError, ValueError):
                pass
            
        return qs
    
    def get_context_data(self, **kwargs):
        """Contexto básico para la lista de lugares."""
        context = super().get_context_data(**kwargs)
        
        # Información de filtros
        tipo_actual = self.request.GET.get("tipo", "")
        busqueda_actual = self.request.GET.get("q", "")
        comuna_actual = self.request.GET.get("comuna", "")
        area_actual = (self.request.GET.get("area") or "").strip()
        context['modo_cerca'] = bool(
            self.request.GET.get('cerca')
            or (self.request.GET.get('lat') and self.request.GET.get('lng'))
        )
        context['cerca_pendiente'] = bool(self.request.GET.get('cerca')) and not (
            self.request.GET.get('lat') and self.request.GET.get('lng')
        )

        # Distancia legible en cards SSR del modo cerca
        if context.get('modo_cerca'):
            for lugar in context.get('lugares') or context.get('object_list') or []:
                dist = getattr(lugar, 'distancia_m', None)
                if dist is None:
                    lugar.distance_display = ''
                    continue
                try:
                    km = float(getattr(dist, 'km', dist) or 0)
                except (TypeError, ValueError):
                    lugar.distance_display = ''
                    continue
                if km < 1:
                    lugar.distance_display = f"{int(round(km * 1000))} m"
                else:
                    lugar.distance_display = f"{km:.1f} km"
        
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
        if area_actual:
            try:
                comuna_info = RegionOSM.objects.get(slug=area_actual)
            except RegionOSM.DoesNotExist:
                pass
        if comuna_info is None and comuna_actual:
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
        
        filtros_query = self.request.GET.copy()
        filtros_query.pop("page", None)

        # Solo el listado sin filtros se pagina como páginas indexables con canonical propio;
        # los filtros siguen noindex para no abrir combinaciones infinitas al rastreo.
        page_obj = context.get("page_obj")
        solo_paginacion = bool(context.get("is_paginated")) and not filtros_query
        pagina_indexable = solo_paginacion and page_obj.number > 1

        context.update({
            "pagina_indexable": pagina_indexable,
            "pagina_query": f"?page={page_obj.number}" if pagina_indexable else "",
            "paginas_rastreables": (
                _paginas_rastreables(page_obj.number, page_obj.paginator.num_pages)
                if solo_paginacion else []
            ),
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
            "region_actual": comuna_info,
            "filtros_url": filtros_query.urlencode(),
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
            Prefetch('fotos', queryset=Foto.objects.only('imagen', 'imagen_mediana', 'imagen_miniatura').order_by('id')[:24], to_attr='cached_fotos'),
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
        
        # Renderizar una muestra de enlaces relacionados en el HTML inicial.
        # Google puede descubrirlos sin depender de JavaScript; AJAX completa
        # después las tres secciones sin penalizar demasiado el tiempo inicial.
        context['lugares_cercanos'] = []
        context['lugares_similares'] = self._get_lugares_similares(lugar, limit=6)
        context['lugares_misma_comuna'] = []
        context['breadcrumbs'] = [
            {'name': _('Inicio'), 'url': reverse('explorer:home')},
            {'name': _('Lugares'), 'url': reverse('explorer:lugares_list')},
        ]
        if lugar.comuna:
            context['breadcrumbs'].append({
                'name': lugar.comuna.name,
                'url': reverse(
                    'explorer:lugares_por_comuna',
                    kwargs={'comuna_slug': lugar.comuna.slug},
                ),
            })
        context['breadcrumbs'].append({
            'name': lugar.nombre,
            'url': self.request.path,
        })
        
        # Meta data para AJAX loading
        context['ajax_endpoints'] = {
            # Respetar prefijo i18n (/en/...) automáticamente
            'lugares_cercanos': reverse('explorer:lugares_cercanos_ajax_slug', kwargs={'slug': lugar.slug}),
            'lugares_similares': reverse('explorer:lugares_similares_ajax_slug', kwargs={'slug': lugar.slug}),
            'lugares_comuna': reverse('explorer:lugares_comuna_ajax_slug', kwargs={'slug': lugar.slug}),
        }
        context['adsense_allowed'] = adsense_allowed_for_place(lugar)
        context['notas_guia'] = self._notas_guia(lugar)
        context['carta'], context['carta_secciones'] = self._carta(lugar)
        
        return context

    def _carta(self, lugar):
        """Carta del partner y platos agrupados por sección."""
        from .models import PlacePartnerMenu

        carta = (
            PlacePartnerMenu.objects.filter(lugar=lugar)
            .prefetch_related("platos")
            .first()
        )
        if carta is None:
            return None, []
        secciones = []
        actual = None
        for plato in carta.platos.all():
            nombre = plato.section or ""
            if actual is None or actual["nombre"] != nombre:
                actual = {"nombre": nombre, "platos": []}
                secciones.append(actual)
            actual["platos"].append(plato)
        return carta, secciones

    def _notas_guia(self, lugar):
        """Frases cortas de las guías publicadas que incluyen este lugar."""
        from .models import CuratedGuideItem

        notas = []
        vistas = set()
        items = (
            CuratedGuideItem.objects
            .filter(lugar=lugar, guia__publicado=True)
            .exclude(comentario='')
            .select_related('guia')
            .order_by('guia__orden', 'posicion')
        )
        for item in items:
            texto = (item.comentario_i18n or '').strip()
            if not texto or texto in vistas:
                continue
            vistas.add(texto)
            notas.append(texto)
        return notas
    
    def _get_lugares_cercanos(self, lugar, distance=500, limit=3):
        """Obtener lugares cercanos con caché y optimización geoespacial."""
        from django.contrib.gis.db.models.functions import Distance as GeoDistance
        
        if not lugar.ubicacion:
            return []
            
        cache_key = f"nearby_optimized_{lugar.id}_{distance}_{limit}_v3"
        result = cache.get(cache_key)
        
        if result is None:
            result = list(Places.objects.filter(
                tiene_fotos=True,
                ubicacion__distance_lte=(lugar.ubicacion, distance)
            ).para_buscador().exclude(
                id=lugar.id
            ).only(
                'id', 'nombre', 'slug', 'tipo', 'rating', 'total_reviews', 'direccion',
                'es_destacado', 'es_exclusivo', 'comuna_osm_id', 'ubicacion'
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
        cache_key = f"related_similares_{lugar.id}_{comuna_id}_{limit}_v2"
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
            qs = Places.objects.filter(**base_filter).para_buscador().exclude(id=lugar.id)

            if tags:
                qs = qs.filter(tags__id__in=tags).distinct()

            def fetch_related(queryset):
                return list(queryset.only(
                    "id",
                    "nombre",
                    "slug",
                    "tipo",
                    "rating",
                    "total_reviews",
                    "direccion",
                    "precio",
                    "es_destacado",
                    "es_exclusivo",
                )
                .prefetch_related(
                    Prefetch(
                        "fotos",
                        queryset=Foto.objects.only("imagen", "imagen_mediana", "imagen_miniatura")[:1],
                        to_attr="cached_fotos",
                    )
                )
                .order_by("-es_destacado", "-weighted_rating", "-rating")[:limit]
                )

            result = fetch_related(qs)
            if not result and tags:
                # No dejar una ficha aislada si sus tags son demasiado específicos.
                fallback_qs = Places.objects.filter(**base_filter).para_buscador().exclude(id=lugar.id)
                result = fetch_related(fallback_qs)
            if not result and comuna_id:
                # Tipo raro en su zona: otros lugares de la misma comuna, luego
                # el mismo tipo en toda la ciudad.
                for filtro in ({"comuna_osm_id": comuna_id}, {"tipo": lugar.tipo}):
                    result = fetch_related(
                        Places.objects.filter(tiene_fotos=True, **filtro)
                        .para_buscador().exclude(id=lugar.id)
                    )
                    if result:
                        break

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
            ).para_buscador().exclude(
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
        context['adsense_allowed'] = adsense_allowed_for_place(lugar)
        
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

    region = RegionOSM.objects.filter(slug=comuna_slug).first()
    if not region:
        region = RegionOSM.objects.filter(
            name__iexact=comuna_slug.replace('-', ' ')
        ).first()
    if not region:
        raise Http404(_("Comuna no encontrada"))
    
    # Crear una versión personalizada de PlacesListView con filtro de comuna
    class LugaresPorComunaView(PlacesListView):
        def get_queryset(self):
            # Queryset base filtrado por comuna, priorizando destacados
            qs = Places.objects.filter(
                tiene_fotos=True,
                comuna_osm_id=region.osm_id
            ).para_buscador().prefetch_related('fotos').order_by('-es_destacado', '-weighted_rating', '-rating', 'nombre')
            
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
        ).para_buscador()
        
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
        ).para_buscador()
        
        q = (request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(nombre__icontains=q)

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
        
        # Geo (modo cerca): preservar lat/lng/radio al filtrar
        lat = request.GET.get('lat')
        lng = request.GET.get('lng')
        geo_active = False
        if lat and lng:
            try:
                from django.contrib.gis.geos import Point
                from django.contrib.gis.db.models.functions import Distance
                from django.contrib.gis.measure import D
                lat_f = float(lat)
                lng_f = float(lng)
                radio_km = float(request.GET.get('radio', '3') or 3)
                radio_km = max(0.5, min(radio_km, 15))
                if 5.0 <= lat_f <= 7.0 and -76.0 <= lng_f <= -74.0:
                    user_point = Point(lng_f, lat_f, srid=4326)
                    qs = (
                        qs.filter(ubicacion__distance_lte=(user_point, D(km=radio_km)))
                        .annotate(distancia_m=Distance('ubicacion', user_point))
                        .order_by('distancia_m', '-es_destacado', '-weighted_rating', '-rating')
                    )
                    geo_active = True
            except (TypeError, ValueError):
                geo_active = False

        # Ordenar
        if not geo_active:
            qs = qs.prefetch_related('fotos').order_by('-es_destacado', '-weighted_rating', '-rating', 'nombre')
        else:
            qs = qs.prefetch_related('fotos')
        
        # Paginación
        total_count = qs.count()
        paginator = Paginator(qs, per_page)
        page_obj = paginator.get_page(page)
        
        # Formatear resultados
        resultados = []
        for lugar in page_obj:
            primera_foto = lugar.fotos.first()
            item = {
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
            }
            dist = getattr(lugar, 'distancia_m', None)
            if dist is not None:
                try:
                    km = float(getattr(dist, 'km', dist) or 0)
                    item['distancia'] = round(km, 2)
                    item['distancia_km'] = round(km, 2)
                except (TypeError, ValueError):
                    pass
            resultados.append(item)
        
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


def _emoji_lugar(lugar):
    """Icono del pin, al estilo de las categorías de MenuRadar."""
    code = (getattr(lugar, "tipo", None) or "").lower()
    tokens = re.findall(r"[a-z0-9]+", code)
    exacto = {
        "bar": "🍸",
        "pub": "🍸",
        "wine": "🍷",
        "cafe": "☕",
        "cafeteria": "☕",
        "coffee": "☕",
        "bakery": "🥐",
        "night": "🌙",
        "nightclub": "🌙",
        "pizza": "🍕",
        "pizzeria": "🍕",
        "burger": "🍔",
        "hamburger": "🍔",
        "sushi": "🍣",
        "kebab": "🥙",
        "chicken": "🍗",
        "rooftop": "🌆",
        "karaoke": "🎵",
    }
    prefijos = (
        ("pizza", "🍕"),
        ("hamburg", "🍔"),
        ("burger", "🍔"),
        ("sushi", "🍣"),
        ("coffee", "☕"),
        ("kebab", "🥙"),
    )
    for token in tokens:
        if token in exacto:
            return exacto[token]
        for prefijo, emoji in prefijos:
            if token.startswith(prefijo):
                return emoji
    return "🍽️"


def _lugar_para_mapa(lugar, distancia_km=None):
    """Ficha corta para un pin del mapa Cerca."""
    if not getattr(lugar, "ubicacion", None):
        return None
    fotos = list(lugar.fotos.all())
    primera_foto = fotos[0] if fotos else None
    if distancia_km is None and getattr(lugar, "distancia_metros", None):
        try:
            distancia_km = round(float(lugar.distancia_metros.km), 2)
        except (TypeError, ValueError, AttributeError):
            distancia_km = None
    if distancia_km is not None and distancia_km < 1:
        distancia_label = f"{int(round(distancia_km * 1000))} m"
    elif distancia_km is not None:
        distancia_label = f"{distancia_km:.1f} km"
    else:
        distancia_label = ""
    return {
        "nombre": lugar.nombre,
        "slug": lugar.slug,
        "lat": lugar.ubicacion.y,
        "lng": lugar.ubicacion.x,
        "rating": lugar.rating or 0.0,
        "total_reviews": lugar.total_reviews or 0,
        "tipo": get_localized_place_type(lugar),
        "emoji": _emoji_lugar(lugar),
        **get_optimized_image_urls(primera_foto, "thumb"),
        "url": reverse("explorer:lugares_detail", kwargs={"slug": lugar.slug}) if lugar.slug else None,
        "distancia": distancia_km,
        "distancia_label": distancia_label,
        "direccion": lugar.direccion or "",
    }


def _geojson_simple(geom):
    """Polígono más liviano para dibujar el mapa, sin perder la forma."""
    simple = geom.simplify(0.0007, preserve_topology=True)
    if getattr(simple, "empty", False) or not getattr(simple, "num_coords", 0):
        simple = geom
    data = json.loads(simple.geojson)

    def walk(coords):
        if not coords:
            return coords
        if isinstance(coords[0], (int, float)):
            return [round(float(coords[0]), 5), round(float(coords[1]), 5)]
        return [walk(item) for item in coords]

    data["coordinates"] = walk(data["coordinates"])
    return data


def _areas_para_mapa():
    """Polígonos de las zonas con lugares. Sin pines: se cargan al elegir una zona."""
    cached = cache.get("mapa_areas_v2")
    if cached:
        return cached
    ids = Places.objects.filter(tiene_fotos=True).values_list("comuna_osm_id", flat=True).distinct()
    regiones = list(
        RegionOSM.objects.filter(
            osm_id__in=ids,
            name__isnull=False,
            geom_4326__isnull=False,
        ).exclude(slug__isnull=True).exclude(slug="")
    )
    conteos = {
        row["comuna_osm_id"]: row["n"]
        for row in (
            Places.objects.filter(
                tiene_fotos=True,
                comuna_osm_id__in=[region.osm_id for region in regiones],
            )
            .exclude(tipo__in=TIPOS_EXCLUIDOS)
            .values("comuna_osm_id")
            .annotate(n=Count("id"))
        )
    }
    areas = []
    lat_min = lat_max = lng_min = lng_max = None
    for region in regiones:
        extent = region.geom_4326.extent
        lng0, lat0, lng1, lat1 = extent
        lat_min = lat0 if lat_min is None else min(lat_min, lat0)
        lat_max = lat1 if lat_max is None else max(lat_max, lat1)
        lng_min = lng0 if lng_min is None else min(lng_min, lng0)
        lng_max = lng1 if lng_max is None else max(lng_max, lng1)
        areas.append({
            "slug": region.slug,
            "name": region.name,
            "nivel": region.admin_level or "",
            "grupo": "valle" if region.geom_4326.centroid.x < -75.45 else "oriente",
            "total": conteos.get(region.osm_id, 0),
            "geojson": _geojson_simple(region.geom_4326),
        })
    areas.sort(key=lambda area: area["name"])
    payload = {
        "areas": areas,
        "bounds": {
            "lat_min": lat_min,
            "lat_max": lat_max,
            "lng_min": lng_min,
            "lng_max": lng_max,
        },
    }
    cache.set("mapa_areas_v2", payload, 3600)
    return payload


def _lugares_de_area(slug, limit=24):
    """Lugares de una zona, solo cuando alguien la abre."""
    region = RegionOSM.objects.filter(slug=slug, geom_4326__isnull=False).first()
    if not region:
        return None
    qs = (
        Places.objects.filter(
            tiene_fotos=True,
            ubicacion__isnull=False,
            comuna_osm_id=region.osm_id,
        )
        .exclude(tipo__in=TIPOS_EXCLUIDOS)
        .filter(Q(rating__gte=3.5) | Q(rating__isnull=True))
        .prefetch_related("fotos")
        .order_by("-weighted_rating", "-total_reviews", "-rating")[:limit]
    )
    lugares = []
    for lugar in qs:
        payload = _lugar_para_mapa(lugar)
        if payload:
            lugares.append(payload)
    lng0, lat0, lng1, lat1 = region.geom_4326.extent
    bounds = {"lat_min": lat0, "lat_max": lat1, "lng_min": lng0, "lng_max": lng1}
    return region, lugares, bounds


@require_GET
@rate_limit(requests_per_minute=30, key_prefix='near_me')
def lugares_cercanos_ajax_view(request):
    """API AJAX para lugares cercanos basados en geolocalización."""
    from django.http import JsonResponse
    from django.contrib.gis.geos import Point
    from django.contrib.gis.measure import D  # Para distancias
    from django.db import models
    from django.db.models import functions
    from explorer.utils.vive_areas import point_in_scan_areas
    
    # Obtener coordenadas
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')
    radio = request.GET.get('radio', '3')  # Radio por defecto 3km (antes 0.8 quedaba vacío)
    
    # Obtener filtros opcionales
    tipo = request.GET.get('tipo', '').strip()
    caracteristica = request.GET.get('caracteristica', '').strip()
    
    quiere_general = request.GET.get("general") == "1" or not lat or not lng
    area_slug = (request.GET.get("area") or "").strip()

    def respuesta_general(fuera=False):
        payload = _areas_para_mapa()
        return JsonResponse({
            "success": True,
            "modo": "areas",
            "fuera": fuera,
            "en_ciudad": False,
            "total": len(payload["areas"]),
            "areas": payload["areas"],
            "lugares": [],
            "bounds": payload["bounds"],
            "mensaje": _("Toca una zona para ver sus lugares."),
        })

    def respuesta_area(slug):
        encontrado = _lugares_de_area(slug)
        if not encontrado:
            return JsonResponse({"success": False, "error": _("Zona no encontrada")}, status=404)
        region, lugares, bounds = encontrado
        count = len(lugares)
        return JsonResponse({
            "success": True,
            "modo": "area",
            "fuera": True,
            "en_ciudad": False,
            "zona": region.name,
            "slug": region.slug,
            "total": count,
            "lugares": lugares,
            "bounds": bounds,
            "mensaje": ngettext(
                "%(count)s lugar en %(zona)s",
                "%(count)s lugares en %(zona)s",
                count,
            ) % {"count": count, "zona": region.name},
        })

    if area_slug:
        return respuesta_area(area_slug)

    if quiere_general:
        return respuesta_general(fuera=False)

    try:
        # Convertir a float y validar
        lat = float(lat)
        lng = float(lng)
        radio = float(radio)

        if not point_in_scan_areas(lat, lng):
            return respuesta_general(fuera=True)
        
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
        ).para_buscador()
        
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
        ).order_by('distancia_metros', '-es_destacado', '-weighted_rating', '-rating')[:24]
        
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
                'emoji': _emoji_lugar(lugar),
                **get_optimized_image_urls(primera_foto, 'thumb'),
                'es_destacado': lugar.es_destacado,
                'es_exclusivo': lugar.es_exclusivo,
                # URL resuelta por Django según idioma actual
                'url': reverse('explorer:lugares_detail', kwargs={'slug': lugar.slug}) if lugar.slug else None,
                'lat': lugar.ubicacion.y if lugar.ubicacion else None,
                'lng': lugar.ubicacion.x if lugar.ubicacion else None,
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
            'tipo_label': tipo_labels.get(tipo) or (get_localized_place_type_from_code(tipo) if tipo else None),
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
            'modo': 'cerca',
            'fuera': False,
            'en_ciudad': True,
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
            distancia_m = None
            if hasattr(lugar_cercano, 'distancia_metros') and lugar_cercano.distancia_metros:
                distancia_m = int(round(lugar_cercano.distancia_metros.m))
                distancia_km = round(distancia_m / 1000, 3)
            
            foto = lugar_cercano.cached_fotos[0] if lugar_cercano.cached_fotos else None
            data.append({
                'id': lugar_cercano.id,
                'nombre': lugar_cercano.nombre,
                'slug': lugar_cercano.slug,
                'tipo': get_localized_place_type(lugar_cercano),
                'emoji': _emoji_lugar(lugar_cercano),
                'rating': lugar_cercano.rating,
                'total_reviews': lugar_cercano.total_reviews or 0,
                'es_destacado': lugar_cercano.es_destacado,
                'es_exclusivo': lugar_cercano.es_exclusivo,
                'direccion': lugar_cercano.direccion or '',
                'lat': lugar_cercano.ubicacion.y if lugar_cercano.ubicacion else None,
                'lng': lugar_cercano.ubicacion.x if lugar_cercano.ubicacion else None,
                **get_optimized_image_urls(foto, 'thumb'),
                'url': reverse('explorer:lugares_detail', args=[lugar_cercano.slug]) if lugar_cercano.slug else None,
                'distancia_km': distancia_km,
                'distancia_m': distancia_m,
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
		.para_buscador()
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

        lugares = []
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

                lugares = list(lugares_qs.prefetch_related("fotos")[:10])

                if as_json:
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
                lugares = []

        if as_json:
            return JsonResponse({"resultados": resultados, "error": error})
        return render(request, "semantic_results.html", {
            "query": query,
            "lugares": lugares,
            "error": error,
            "adsense_allowed": adsense_allowed_for_search_query(query),
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


@require_POST
@rate_limit(requests_per_minute=8, key_prefix='newsletter')
def newsletter_subscribe(request):
    """Guarda un correo para el envío mensual. Sin correo de confirmación."""
    from .models import NewsletterSubscription

    if (request.POST.get('company') or '').strip():
        return JsonResponse({'ok': True, 'message': _('Listo. Una vez al mes, sin spam.')})

    email = (request.POST.get('email') or '').strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'ok': False, 'message': _('Escribe un correo válido.')}, status=400)

    ip = get_client_ip(request)
    agent = (request.META.get('HTTP_USER_AGENT') or '')[:400]
    sub, created = NewsletterSubscription.objects.get_or_create(
        email=email,
        defaults={
            'fuente': 'home',
            'ip_address': ip,
            'user_agent': agent,
            'confirmado': True,
            'fecha_confirmacion': timezone.now(),
        },
    )
    if created:
        return JsonResponse({'ok': True, 'message': _('Listo. Una vez al mes, sin spam.')})
    if not sub.activo:
        sub.activo = True
        sub.confirmado = True
        sub.fecha_confirmacion = sub.fecha_confirmacion or timezone.now()
        sub.fuente = 'home'
        sub.save(update_fields=['activo', 'confirmado', 'fecha_confirmacion', 'fuente'])
    return JsonResponse({'ok': True, 'message': _('Ese correo ya está en la lista.')})


# ────────────────────────────────────────────────────────────────────────
# Guías Curadas
# ────────────────────────────────────────────────────────────────────────

@require_GET
def guias_index(request):
    """Índice de todas las guías curadas publicadas."""
    from .models import CuratedGuide, GUIDE_CATEGORY_CHOICES
    
    guias = CuratedGuide.objects.filter(
        publicado=True
    ).prefetch_related('items__lugar__fotos').order_by('orden', '-fecha_creacion')
    
    # Agrupar por categoría
    categorias = {}
    for cat_code, cat_label in GUIDE_CATEGORY_CHOICES:
        guias_cat = [g for g in guias if g.categoria == cat_code]
        if guias_cat:
            categorias[cat_label] = guias_cat
    
    context = {
        'guias': guias,
        'categorias': categorias,
        'titulo_pagina': _('Guías de Medellín'),
        'descripcion_pagina': _('Recomendaciones personales de un local. Los mejores lugares de Medellín organizados por zona, temática y experiencia.'),
    }
    return render(request, 'guias/guias_index.html', context)


@require_GET
def guia_detail(request, slug):
    """Detalle de una guía curada con los lugares rankeados."""
    from .models import CuratedGuide
    
    guia = get_object_or_404(
        CuratedGuide.objects.prefetch_related(
            'items__lugar__fotos',
        ),
        slug=slug,
        publicado=True
    )
    
    items = guia.items.select_related('lugar').order_by('posicion')
    
    # Datos de mapa para cada lugar con ubicación
    import json as _json
    markers = []
    for item in items:
        lugar = item.lugar
        if lugar.ubicacion:
            foto = lugar.get_primera_foto()
            img_url = ''
            if foto:
                img_url = resolve_media_url(
                    getattr(foto, 'imagen_miniatura', None)
                    or getattr(foto, 'imagen_mediana', None)
                    or foto.imagen
                    or ''
                ) or ''
            markers.append({
                'lat': lugar.ubicacion.y,
                'lng': lugar.ubicacion.x,
                'nombre': lugar.nombre,
                'slug': lugar.slug,
                'posicion': item.posicion,
                'rating': float(lugar.rating) if lugar.rating else None,
                'imagen': str(img_url),
            })
    
    context = {
        'guia': guia,
        'items': items,
        'markers_json': _json.dumps(markers),
        'titulo_pagina': guia.titulo,
        'descripcion_pagina': guia.descripcion,
    }
    return render(request, 'guias/guia_detail.html', context)

