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
from explorer.utils.types import get_localized_place_type
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
        return Places.objects.filter(tiene_fotos=True).prefetch_related(
            Prefetch('fotos', queryset=Foto.objects.only('imagen')[:3], to_attr='cached_fotos'),
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
                ).prefetch_related('fotos').order_by('-es_destacado', '-rating')[:6]
                
                # Si no hay lugares con show_in_home en esta región, usar los mejores
                if not lugares_region.exists():
                    lugares_region = Places.objects.filter(
                        comuna_osm_id=region.osm_id,
                        tiene_fotos=True,
                        rating__gte=4.0
                    ).prefetch_related('fotos').order_by('-es_destacado', '-rating')[:6]
                
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
                            'imagen': primera_foto.imagen if primera_foto else None,
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
        wellness: list[dict] = []
        other: list[dict] = []

        for code, es_label in PLACE_TYPE_CHOICES:
            item = {"value": code, "name": _label_for(code, es_label)}
            c = (code or "").lower()
            if "restaurant" in c or c in {"food", "food_court", "meal_delivery", "meal_takeaway", "catering_service"}:
                restaurants.append(item)
            elif c in {"bar", "wine_bar", "pub", "night_club", "karaoke", "bar_and_grill"}:
                nightlife.append(item)
            elif "cafe" in c or c in {"cafeteria", "acai_shop", "cat_cafe", "dog_cafe", "internet_cafe"}:
                cafes.append(item)
            elif "museum" in c or "art" in c or "cultural" in c or "historical" in c or "attraction" in c or "tour" in c or "landmark" in c:
                culture.append(item)
            elif "spa" in c or "wellness" in c or "health" in c:
                wellness.append(item)
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
        if wellness:
            categorias_reales.append({"name": _("Bienestar y spa"), "icon": "bi-heart-pulse", "color": "danger", "subcategorias": wellness})
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
        # Queryset base optimizado - solo lugares con fotos, priorizando destacados
        qs = Places.objects.filter(tiene_fotos=True).prefetch_related('fotos').order_by('-es_destacado', '-rating', 'nombre')

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
        
        # Mapeo de tipos a títulos y descripciones
        tipos_info = {
            'restaurant': {
                'titulo': _('Mejores Restaurantes en Medellín'),
                'descripcion': _('Descubre los sabores más auténticos de la gastronomía paisa y mundial'),
                'icono': 'bi-cup-hot'
            },
            'bar': {
                'titulo': _('Mejores Bares y Discotecas en Medellín'), 
                'descripcion': _('Vive la mejor vida nocturna de la ciudad de la eterna primavera'),
                'icono': 'bi-cup-straw'
            },
            'cafe': {
                'titulo': _('Mejores Cafeterías en Medellín'),
                'descripcion': _('Experimenta la auténtica cultura cafetera paisa'),
                'icono': 'bi-cup'
            }
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

        # Título y descripción dinámicos
        if busqueda_actual:
            titulo_pagina = _("Resultados para \"%(query)s\"") % {"query": busqueda_actual}
            descripcion_pagina = _('Lugares que coinciden con tu búsqueda en Medellín')
        elif comuna_info and not tipo_actual and not filtros_activos:
            # Cuando viene de "Ver todos" de una comuna específica
            titulo_pagina = _('Los mejores lugares en %(comuna)s') % {'comuna': comuna_info.name}
            descripcion_pagina = _('Descubre los sitios más destacados de %(comuna)s') % {'comuna': comuna_info.name}
        elif comuna_info and tipo_actual and tipo_actual in tipos_info:
            # Comuna + tipo específico
            info = tipos_info[tipo_actual]
            titulo_pagina = _('%(titulo)s').replace(_('en Medellín'), _('en %(comuna)s') % {'comuna': comuna_info.name}) % {'titulo': info['titulo']}
            if filtros_activos:
                titulo_pagina += _(' %(filters)s') % {'filters': _(' y ').join(filtros_activos[:2])}
            descripcion_pagina = _('%(desc)s en la zona de %(comuna)s') % {'desc': info['descripcion'], 'comuna': comuna_info.name}
        elif comuna_info and filtros_activos:
            # Comuna + filtros especiales
            titulo_pagina = _('Lugares %(filters)s en %(comuna)s') % {'filters': _(' y ').join(filtros_activos[:2]), 'comuna': comuna_info.name}
            descripcion_pagina = _('Lugares especializados en %(comuna)s que cumplen tus criterios') % {'comuna': comuna_info.name}
        elif tipo_actual and tipo_actual in tipos_info:
            # Solo tipo, sin comuna
            info = tipos_info[tipo_actual]
            titulo_pagina = info['titulo']
            if filtros_activos:
                titulo_pagina += _(' %(filters)s') % {'filters': _(' y ').join(filtros_activos[:2])}
            descripcion_pagina = info['descripcion']
        elif filtros_activos:
            # Solo filtros especiales, sin comuna ni tipo
            titulo_pagina = _('Lugares %(filters)s en Medellín') % {'filters': _(' y ').join(filtros_activos[:2])}
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
            {"key": "wellness", "emoji": "🧘", "name": _("Bienestar y spa"), "items": []},
            {"key": "other", "emoji": "✨", "name": _("Otros"), "items": []},
        ]
        idx = {g["key"]: g for g in groups}

        for code, es_label in PLACE_TYPE_CHOICES:
            item = {"code": code, "label": label_for(code, es_label)}
            c = (code or "").lower()
            if "restaurant" in c or c in {"food", "food_court", "meal_delivery", "meal_takeaway", "catering_service"}:
                idx["food"]["items"].append(item)
            elif c in {"bar", "wine_bar", "pub", "night_club", "karaoke", "bar_and_grill"}:
                idx["nightlife"]["items"].append(item)
            elif "cafe" in c or c in {"cafeteria", "acai_shop", "cat_cafe", "dog_cafe", "internet_cafe"}:
                idx["cafes"]["items"].append(item)
            elif "museum" in c or "art" in c or "cultural" in c or "historical" in c or "attraction" in c or "tour" in c or "landmark" in c:
                idx["culture"]["items"].append(item)
            elif "spa" in c or "wellness" in c or "health" in c:
                idx["wellness"]["items"].append(item)
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
            Prefetch('fotos', queryset=Foto.objects.only('imagen')[:5], to_attr='cached_fotos'),
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
        if not lugar.ubicacion:
            return []
            
        cache_key = f"nearby_optimized_{lugar.id}_{distance}_{limit}"
        result = cache.get(cache_key)
        
        if result is None:
            # Optimización 1: Reducir distancia de 1000m a 500m
            # Optimización 2: Usar select_related para comuna
            # Optimización 3: Usar only() para limitar campos
            # Optimización 4: Reducir límite de 5 a 3
            result = list(Places.objects.filter(
                tiene_fotos=True,
                ubicacion__distance_lte=(lugar.ubicacion, distance)
            ).exclude(
                id=lugar.id
            ).only(
                'id', 'nombre', 'slug', 'tipo', 'rating', 'es_destacado', 'es_exclusivo', 'comuna_osm_id'
            ).prefetch_related(
                Prefetch('fotos', queryset=Foto.objects.only('imagen')[:1], to_attr='cached_fotos')
            ).order_by('-es_destacado', '-rating')[:limit])  # Priorizando destacados y rating
            
            cache.set(cache_key, result, 3600)  # 1 hora de caché
        
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
                .order_by("-es_destacado", "-rating")[:limit]
            )
            
            cache.set(cache_key, result, 3600)  # 1 hora de caché
        
        return result
    
    def _get_lugares_misma_comuna(self, lugar):
        """Obtener otros lugares de la misma comuna."""
        if not lugar.comuna_osm_id:
            return []
            
        cache_key = f"comuna_optimized_{lugar.comuna_osm_id}_{lugar.id}"
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
                Prefetch('fotos', queryset=Foto.objects.only('imagen')[:1], to_attr='cached_fotos')
            ).order_by('-es_destacado', '-rating')[:3])  # Priorizando destacados
            
            cache.set(cache_key, result, 3600)  # 1 hora de caché
        
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
            Prefetch('fotos', queryset=Foto.objects.only('imagen'), to_attr='cached_fotos')
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
            ).prefetch_related('fotos').order_by('-es_destacado', '-rating', 'nombre')
            
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
            
            # Mapeo de tipos para comuna específica
            tipos_info = {
                'restaurant': {
                    'titulo': f'Mejores Restaurantes en {region.name}',
                    'descripcion': f'Descubre los sabores más auténticos en {region.name}',
                    'icono': 'bi-cup-hot'
                },
                'bar': {
                    'titulo': f'Mejores Bares en {region.name}', 
                    'descripcion': f'Vive la mejor vida nocturna en {region.name}',
                    'icono': 'bi-cup-straw'
                },
                'cafe': {
                    'titulo': f'Mejores Cafeterías en {region.name}',
                    'descripcion': f'Experimenta la cultura cafetera en {region.name}',
                    'icono': 'bi-cup'
                }
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

            # Título dinámico para comuna específica (versión robusta por idioma)
            # Usar el prefijo de la URL para decidir el idioma, evitando inconsistencias de estado
            lang = 'en' if self.request.path.startswith('/en/') else (get_language() or 'es')
            if busqueda_actual:
                if lang.startswith('en'):
                    titulo_pagina = f'Results for "{busqueda_actual}" in {region.name}'
                    descripcion_pagina = f'Places that match your search in {region.name}'
                else:
                    titulo_pagina = _('Resultados para "%(query)s" en %(comuna)s') % {
                        'query': busqueda_actual,
                        'comuna': region.name,
                    }
                    descripcion_pagina = _('Lugares que coinciden con tu búsqueda en %(comuna)s') % {
                        'comuna': region.name,
                    }
            elif tipo_actual and tipo_actual in tipos_info:
                info = tipos_info[tipo_actual]
                titulo_pagina = info['titulo']
                if filtros_activos:
                    # Aquí info['titulo'] ya viene traducido por get_localized_place_type
                    joiner = ' and ' if lang.startswith('en') else _(' y ')
                    filtros_txt = joiner.join(filtros_activos[:2])
                    if lang.startswith('en'):
                        titulo_pagina += f' {filtros_txt}'
                    else:
                        titulo_pagina += _(' %(filters)s') % {'filters': filtros_txt}
                descripcion_pagina = info['descripcion']
            elif filtros_activos:
                joiner = ' and ' if lang.startswith('en') else _(' y ')
                filtros_txt = joiner.join(filtros_activos[:2])
                if lang.startswith('en'):
                    titulo_pagina = f'Places {filtros_txt} in {region.name}'
                    descripcion_pagina = f'Specialized places in {region.name} that match your criteria'
                else:
                    titulo_pagina = _('Lugares %(filters)s en %(comuna)s') % {
                        'filters': filtros_txt,
                        'comuna': region.name,
                    }
                    descripcion_pagina = _('Lugares especializados en %(comuna)s que cumplen tus criterios') % {
                        'comuna': region.name,
                    }
            else:
                if lang.startswith('en'):
                    titulo_pagina = f'The best places in {region.name}'
                    descripcion_pagina = f'Discover the most outstanding places in {region.name}'
                else:
                    titulo_pagina = _('Los mejores lugares en %(comuna)s') % {
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
        # Construir queryset base
        qs = Places.objects.filter(tiene_fotos=True)
        
        # Aplicar filtros
        if area_id != 'all':
            qs = qs.filter(comuna_osm_id=area_id)
            
        if categoria != 'all':
            qs = qs.filter(tipo=categoria)
            
        if caracteristica and caracteristica != 'all':
            qs = qs.filter(**{caracteristica: True})
        
        # Obtener resultados con prefetch, priorizando destacados
        lugares = qs.prefetch_related('fotos').order_by('-es_destacado', '-rating', 'nombre')[:12]
        
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
                'imagen': primera_foto.imagen if primera_foto else None,
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
        
        # Construir queryset base
        qs = Places.objects.filter(
            tiene_fotos=True,
            ubicacion__distance_lte=(user_location, D(km=radio))
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
        ).order_by('distancia_metros', '-es_destacado', '-rating')[:15]
        
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
                'imagen': primera_foto.imagen if primera_foto else None,
                'es_destacado': lugar.es_destacado,
                'es_exclusivo': lugar.es_exclusivo,
                # URL resuelta por Django según idioma actual
                'url': reverse('explorer:lugares_detail', kwargs={'slug': lugar.slug}) if lugar.slug else None,
                'distancia': round(lugar.distancia_metros.km, 2) if hasattr(lugar, 'distancia_metros') and lugar.distancia_metros else None,
                'direccion': lugar.direccion
            })
        
        count = len(resultados)
        distancia = f"{int(radio * 1000)}m" if radio < 1 else f"{radio}km"
        mensaje = ngettext(
            'Encontramos %(count)s lugar en un radio de %(dist)s',
            'Encontramos %(count)s lugares en un radio de %(dist)s',
            count
        ) % {'count': count, 'dist': distancia}

        return JsonResponse({
            'success': True,
            'total': count,
            'lugares': resultados,
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
        lugares_cercanos = view._get_lugares_cercanos(lugar) if lugar.ubicacion else []
        
        # Serializar lugares
        data = []
        for lugar_cercano in lugares_cercanos:
            data.append({
                'id': lugar_cercano.id,
                'nombre': lugar_cercano.nombre,
                'slug': lugar_cercano.slug,
                'tipo': get_localized_place_type(lugar_cercano),
                'rating': lugar_cercano.rating,
                'es_destacado': lugar_cercano.es_destacado,
                'es_exclusivo': lugar_cercano.es_exclusivo,
                'imagen': lugar_cercano.cached_fotos[0].imagen if lugar_cercano.cached_fotos else None,
                'url': reverse('explorer:lugares_detail', args=[lugar_cercano.slug]) if lugar_cercano.slug else None,
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
        lugares_similares = view._get_lugares_similares(lugar)
        
        # Serializar lugares
        data = []
        for lugar_similar in lugares_similares:
            data.append({
                'id': lugar_similar.id,
                'nombre': lugar_similar.nombre,
                'slug': lugar_similar.slug,
                'tipo': get_localized_place_type(lugar_similar),
                'rating': lugar_similar.rating,
                'es_destacado': lugar_similar.es_destacado,
                'es_exclusivo': lugar_similar.es_exclusivo,
                'imagen': lugar_similar.cached_fotos[0].imagen if lugar_similar.cached_fotos else None,
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
        lugares_comuna = view._get_lugares_misma_comuna(lugar) if lugar.comuna_osm_id else []
        
        # Serializar lugares
        data = []
        for lugar_comuna_item in lugares_comuna:
            data.append({
                'id': lugar_comuna_item.id,
                'nombre': lugar_comuna_item.nombre,
                'slug': lugar_comuna_item.slug,
                'tipo': get_localized_place_type(lugar_comuna_item),
                'rating': lugar_comuna_item.rating,
                'es_destacado': lugar_comuna_item.es_destacado,
                'es_exclusivo': lugar_comuna_item.es_exclusivo,
                'imagen': lugar_comuna_item.cached_fotos[0].imagen if lugar_comuna_item.cached_fotos else None,
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
			'imagen': foto.imagen if foto else None,
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
                        "imagen": primera_foto.imagen if primera_foto else None,
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
    if not text:
        return 'EN'
    lowered = text.lower()
    # Señales de español: tildes, eñes, signos de ¿¡, y stopwords comunes
    if re.search(r"[áéíóúñ¿¡]", lowered):
        return 'ES'
    spanish_tokens = {" el ", " la ", " de ", " y ", " en ", " los ", " las ", " una ", " un ", " que ", " con ", " para ", " por "}
    padded = f" {lowered} "
    if any(tok in padded for tok in spanish_tokens):
        return 'ES'
    return 'EN'


def _mymemory_translate(text: str, source: str, target: str) -> str | None:
    params = {
        "q": text,
        "langpair": f"{source}|{target}",
    }
    url = "https://api.mymemory.translated.net/get?" + urlencode(params)
    try:
        import json as _json
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = _json.loads(resp.read().decode("utf-8", errors="ignore"))
            status = int(data.get("responseStatus", 500))
            translated = (data.get("responseData") or {}).get("translatedText") or ""
            # Rechazar mensajes de error como "'AUTO' IS AN INVALID SOURCE LANGUAGE ..."
            if status == 200 and translated and "INVALID SOURCE LANGUAGE" not in translated and " 'AUTO' " not in translated:
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