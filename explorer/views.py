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

from .models import Places, Foto, RegionOSM, Tag, NewsletterSubscription, PLACE_TYPE_CHOICES

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
        
        # Verificar caché
        cache_key = "home_regiones_osm"
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
                ).prefetch_related('fotos').order_by('-rating')[:6]
                
                # Si no hay lugares con show_in_home en esta región, usar los mejores
                if not lugares_region.exists():
                    lugares_region = Places.objects.filter(
                        comuna_osm_id=region.osm_id,
                        tiene_fotos=True,
                        rating__gte=4.0
                    ).prefetch_related('fotos').order_by('-rating')[:6]
                
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
                            'tipo': lugar.get_tipo_display(),
                            'imagen': primera_foto.imagen if primera_foto else None,
                            'es_destacado': lugar.es_destacado,
                            'es_exclusivo': lugar.es_exclusivo
                        })
                    
                    comuna_con_lugares.append({
                        'nombre': region.name,
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
        # 1. ÁREAS - Obtener regiones principales (priorizando Poblado y Laureles)
        from django.db.models import Case, When, IntegerField
        
        regiones_areas = RegionOSM.objects.filter(
            osm_id__in=Places.objects.filter(tiene_fotos=True).values_list('comuna_osm_id', flat=True).distinct()
        ).annotate(
            orden_area=Case(
                When(name__icontains='Poblado', then=1),
                When(name__icontains='Laureles', then=2),
                default=3,
                output_field=IntegerField()
            )
        ).order_by('orden_area', 'name')[:22]
        
        # 2. CATEGORÍAS REALES - Basadas en PLACE_TYPE_CHOICES
        categorias_reales = [
            {
                'name': 'Restaurantes',
                'icon': 'bi-cup-hot',
                'color': 'success',
                'subcategorias': [
                    {'value': 'restaurant', 'name': 'Restaurante General'},
                    {'value': 'fine_dining_restaurant', 'name': 'Restaurante Gourmet'},
                    {'value': 'pizza_restaurant', 'name': 'Pizzería'},
                    {'value': 'italian_restaurant', 'name': 'Restaurante Italiano'},
                    {'value': 'mexican_restaurant', 'name': 'Restaurante Mexicano'},
                    {'value': 'chinese_restaurant', 'name': 'Restaurante Chino'},
                    {'value': 'seafood_restaurant', 'name': 'Marisquería'},
                    {'value': 'steak_house', 'name': 'Parrilla de Carnes'},
                    {'value': 'fast_food_restaurant', 'name': 'Comida Rápida'},
                ]
            },
            {
                'name': 'Bares & Vida Nocturna',
                'icon': 'bi-cup-straw',
                'color': 'warning',
                'subcategorias': [
                    {'value': 'bar', 'name': 'Bar'},
                    {'value': 'wine_bar', 'name': 'Bar de Vinos'},
                    {'value': 'pub', 'name': 'Pub'},
                    {'value': 'night_club', 'name': 'Discoteca'},
                    {'value': 'karaoke', 'name': 'Karaoke'},
                ]
            },
            {
                'name': 'Cafeterías',
                'icon': 'bi-cup',
                'color': 'info',
                'subcategorias': [
                    {'value': 'cafe', 'name': 'Cafetería'},
                    {'value': 'internet_cafe', 'name': 'Cibercafé'},
                    {'value': 'breakfast_restaurant', 'name': 'Desayunos'},
                    {'value': 'brunch_restaurant', 'name': 'Brunch'},
                ]
            }
        ]
        
        # 3. ETIQUETAS ESPECIALES - Características y servicios
        etiquetas_especiales = [
            {
                'name': 'Servicios de Entrega',
                'icon': 'bi-bicycle',
                'opciones': [
                    {'field': 'delivery', 'name': 'Delivery', 'icon': 'bi-bicycle'},
                    {'field': 'takeout', 'name': 'Para Llevar', 'icon': 'bi-bag'},
                    {'field': 'dine_in', 'name': 'Comer en Local', 'icon': 'bi-house'},
                ]
            },
            {
                'name': 'Ambiente & Experiencia',
                'icon': 'bi-stars',
                'opciones': [
                    {'field': 'outdoor_seating', 'name': 'Terraza', 'icon': 'bi-tree'},
                    {'field': 'live_music', 'name': 'Música en Vivo', 'icon': 'bi-music-note-beamed'},
                    {'field': 'good_for_groups', 'name': 'Para Grupos', 'icon': 'bi-people'},
                    {'field': 'good_for_children', 'name': 'Para Niños', 'icon': 'bi-emoji-smile'},
                ]
            },
            {
                'name': 'Especialidades',
                'icon': 'bi-cup-straw',
                'opciones': [
                    {'field': 'serves_cocktails', 'name': 'Cócteles', 'icon': 'bi-cup-straw'},
                    {'field': 'serves_wine', 'name': 'Vinos', 'icon': 'bi-cup'},
                    {'field': 'serves_coffee', 'name': 'Café Especialidad', 'icon': 'bi-cup-hot'},
                    {'field': 'serves_dessert', 'name': 'Postres', 'icon': 'bi-cake'},
                ]
            },
            {
                'name': 'Accesibilidad & Comodidades',
                'icon': 'bi-universal-access',
                'opciones': [
                    {'field': 'wheelchair_accessible_entrance', 'name': 'Acceso Accesible', 'icon': 'bi-universal-access'},
                    {'field': 'allows_dogs', 'name': 'Pet Friendly', 'icon': 'bi-heart'},
                    {'field': 'accepts_credit_cards', 'name': 'Tarjetas de Crédito', 'icon': 'bi-credit-card'},
                ]
            }
        ]
        
        return {
            'regiones_areas': regiones_areas,
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
        # Queryset base optimizado - solo lugares con fotos
        qs = Places.objects.filter(tiene_fotos=True).prefetch_related('fotos').order_by('-rating', 'nombre')

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
                'titulo': 'Mejores Restaurantes en Medellín',
                'descripcion': 'Descubre los sabores más auténticos de la gastronomía paisa y mundial',
                'icono': 'bi-cup-hot'
            },
            'bar': {
                'titulo': 'Mejores Bares y Discotecas en Medellín', 
                'descripcion': 'Vive la mejor vida nocturna de la ciudad de la eterna primavera',
                'icono': 'bi-cup-straw'
            },
            'cafe': {
                'titulo': 'Mejores Cafeterías en Medellín',
                'descripcion': 'Experimenta la auténtica cultura cafetera paisa',
                'icono': 'bi-cup'
            }
        }
        
        # Detectar filtros especiales activos
        filtros_activos = []
        filtros_especiales_map = {
            'delivery': 'con Delivery',
            'takeout': 'Para Llevar',
            'dine_in': 'Comer en Local',
            'outdoor_seating': 'con Terraza',
            'live_music': 'con Música en Vivo',
            'allows_dogs': 'Pet Friendly',
            'good_for_groups': 'Para Grupos',
            'good_for_children': 'Para Niños',
            'serves_cocktails': 'con Cócteles',
            'serves_wine': 'con Vinos',
            'serves_coffee': 'Café Especialidad',
            'serves_dessert': 'con Postres',
            'wheelchair_accessible_entrance': 'Accesibles',
            'accepts_credit_cards': 'Aceptan Tarjetas',
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
            titulo_pagina = f'Resultados para "{busqueda_actual}"'
            descripcion_pagina = f'Lugares que coinciden con tu búsqueda en Medellín'
        elif comuna_info and not tipo_actual and not filtros_activos:
            # Cuando viene de "Ver todos" de una comuna específica
            titulo_pagina = f'Los mejores lugares en {comuna_info.name}'
            descripcion_pagina = f'Descubre los sitios más destacados de {comuna_info.name}'
        elif comuna_info and tipo_actual and tipo_actual in tipos_info:
            # Comuna + tipo específico
            info = tipos_info[tipo_actual]
            titulo_pagina = f'{info["titulo"].replace("en Medellín", f"en {comuna_info.name}")}'
            if filtros_activos:
                titulo_pagina += f' {" y ".join(filtros_activos[:2])}'
            descripcion_pagina = f'{info["descripcion"]} en la zona de {comuna_info.name}'
        elif comuna_info and filtros_activos:
            # Comuna + filtros especiales
            titulo_pagina = f'Lugares {" y ".join(filtros_activos[:2])} en {comuna_info.name}'
            descripcion_pagina = f'Lugares especializados en {comuna_info.name} que cumplen tus criterios'
        elif tipo_actual and tipo_actual in tipos_info:
            # Solo tipo, sin comuna
            info = tipos_info[tipo_actual]
            titulo_pagina = info['titulo']
            if filtros_activos:
                titulo_pagina += f' {" y ".join(filtros_activos[:2])}'
            descripcion_pagina = info['descripcion']
        elif filtros_activos:
            # Solo filtros especiales, sin comuna ni tipo
            titulo_pagina = f'Lugares {" y ".join(filtros_activos[:2])} en Medellín'
            descripcion_pagina = 'Lugares especializados que cumplen tus criterios de búsqueda'
        else:
            # Vista general sin filtros
            titulo_pagina = 'Todos los Lugares en Medellín'
            descripcion_pagina = 'Descubre los mejores sitios que ofrece la ciudad'
        
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
        
        context.update({
            "busqueda_actual": busqueda_actual,
            "tipo_actual": tipo_actual,
            "titulo_pagina": titulo_pagina,
            "descripcion_pagina": descripcion_pagina,
            "tipos_info": tipos_info,
            "regiones_filtro": regiones_filtro,
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
            'lugares_cercanos': f'/api/lugares/{lugar.slug}/cercanos/',
            'lugares_similares': f'/api/lugares/{lugar.slug}/similares/',
            'lugares_comuna': f'/api/lugares/{lugar.slug}/comuna/',
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
            ).order_by('-rating')[:limit])  # Orden por rating en lugar de aleatorio
            
            cache.set(cache_key, result, 3600)  # 1 hora de caché
        
        return result
    
    def _get_lugares_similares(self, lugar, limit=3):
        """Obtener lugares relacionados por tags compartidos."""
        cache_key = f"related_tags_optimized_{lugar.id}_{limit}"
        result = cache.get(cache_key)
        
        if result is None:
            # Optimización: Usar select_related y limitar las consultas de tags
            tags = list(lugar.tags.values_list('id', flat=True)[:5])  # Máximo 5 tags
            if not tags:
                # Si no hay tags, buscar por tipo similar
                result = list(Places.objects.filter(
                    tiene_fotos=True,
                    tipo=lugar.tipo
                                 ).exclude(
                     id=lugar.id
                 ).only(
                     'id', 'nombre', 'slug', 'tipo', 'rating', 'es_destacado', 'es_exclusivo'
                 ).prefetch_related(
                     Prefetch('fotos', queryset=Foto.objects.only('imagen')[:1], to_attr='cached_fotos')
                 ).order_by('-rating')[:limit])
            else:
                result = list(Places.objects.filter(
                    tiene_fotos=True,
                    tags__id__in=tags
                ).exclude(
                    id=lugar.id
                ).only(
                    'id', 'nombre', 'slug', 'tipo', 'rating', 'es_destacado', 'es_exclusivo'
                ).prefetch_related(
                    Prefetch('fotos', queryset=Foto.objects.only('imagen')[:1], to_attr='cached_fotos')
                ).distinct().order_by('-rating')[:limit])
            
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
            ).order_by('-rating')[:3])  # Reducir de 5 a 3
            
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
        
        # Procesar reviews desde JSON
        reviews = []
        if lugar.reviews:
            try:
                for review in lugar.reviews:
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
                print(f"Error procesando reviews: {e}")
                pass
        
        context['reviews'] = reviews
        context['rating_promedio'] = lugar.rating
        context['total_reviews'] = lugar.total_reviews or len(reviews)
        
        return context


# ────────────────────────────────────────────────────────────────────────
# Funciones de Vista
# ────────────────────────────────────────────────────────────────────────

@cache_page(60 * 60)  # 1 hora de caché de página completa - OPTIMIZADO
def home(request):
    """Vista de inicio que usa HomeView OPTIMIZADA."""
    view = HomeView.as_view()
    return view(request)


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
            # Queryset base filtrado por comuna
            qs = Places.objects.filter(
                tiene_fotos=True,
                comuna_osm_id=region.osm_id
            ).prefetch_related('fotos').order_by('-rating', 'nombre')
            
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
                'delivery': 'con Delivery', 'takeout': 'Para Llevar', 
                'dine_in': 'Comer en Local', 'outdoor_seating': 'con Terraza',
                'live_music': 'con Música en Vivo', 'allows_dogs': 'Pet Friendly',
                'good_for_groups': 'Para Grupos', 'good_for_children': 'Para Niños',
                'serves_cocktails': 'con Cócteles', 'serves_wine': 'con Vinos',
                'serves_coffee': 'Café Especialidad', 'serves_dessert': 'con Postres',
                'wheelchair_accessible_entrance': 'Accesibles',
                'accepts_credit_cards': 'Aceptan Tarjetas',
            }
            
            for filtro, nombre in filtros_especiales_map.items():
                if self.request.GET.get(filtro) == 'true':
                    filtros_activos.append(nombre)

            # Título dinámico para comuna específica
            if busqueda_actual:
                titulo_pagina = f'Resultados para "{busqueda_actual}" en {region.name}'
                descripcion_pagina = f'Lugares que coinciden con tu búsqueda en {region.name}'
            elif tipo_actual and tipo_actual in tipos_info:
                info = tipos_info[tipo_actual]
                titulo_pagina = info['titulo']
                if filtros_activos:
                    titulo_pagina += f' {" y ".join(filtros_activos[:2])}'
                descripcion_pagina = info['descripcion']
            elif filtros_activos:
                titulo_pagina = f'Lugares {" y ".join(filtros_activos[:2])} en {region.name}'
                descripcion_pagina = f'Lugares especializados en {region.name} que cumplen tus criterios'
            else:
                titulo_pagina = f'Los mejores lugares en {region.name}'
                descripcion_pagina = f'Descubre los sitios más destacados de {region.name}'
            
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
def autocomplete_places_view(request):
    """API para autocompletar lugares."""
    from django.http import JsonResponse
    
    term = request.GET.get('term', '')
    if not term or len(term) < 2:
        return JsonResponse([], safe=False)
    
    lugares = Places.objects.filter(
        tiene_fotos=True
    ).filter(
        Q(nombre__icontains=term) | 
        Q(direccion__icontains=term)
    ).values('nombre', 'slug', 'tipo')[:10]
    
    results = []
    for lugar in lugares:
        results.append({
            'label': f"{lugar['nombre']} ({lugar['tipo']})",
            'value': lugar['nombre'],
            'slug': lugar['slug']
        })
    
    return JsonResponse(results, safe=False) 


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
            'error': 'Se requieren área y categoría. La característica es opcional.'
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
        
        # Obtener resultados con prefetch
        lugares = qs.prefetch_related('fotos').order_by('-rating', 'nombre')[:12]
        
        # Formatear datos para JSON
        resultados = []
        for lugar in lugares:
            primera_foto = lugar.fotos.first()
            resultados.append({
                'nombre': lugar.nombre,
                'slug': lugar.slug,
                'rating': lugar.rating or 0.0,
                'total_reviews': lugar.total_reviews or 0,
                'tipo': lugar.get_tipo_display(),
                'imagen': primera_foto.imagen if primera_foto else None,
                'es_destacado': lugar.es_destacado,
                'es_exclusivo': lugar.es_exclusivo,
                'url': f"/lugares/{lugar.slug}/" if lugar.slug else None
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
            'error': f'Error en la búsqueda: {str(e)}'
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
        
        lugares_cercanos = Places.objects.filter(
            tiene_fotos=True,
            ubicacion__distance_lte=(user_location, D(km=radio))
        ).prefetch_related('fotos').annotate(
            distancia_metros=Distance('ubicacion', user_location)
        ).order_by('distancia_metros', '-rating')[:15]
        
        # Formatear resultados
        resultados = []
        for lugar in lugares_cercanos:
            primera_foto = lugar.fotos.first()
            resultados.append({
                'nombre': lugar.nombre,
                'slug': lugar.slug,
                'rating': lugar.rating or 0.0,
                'total_reviews': lugar.total_reviews or 0,
                'tipo': lugar.get_tipo_display(),
                'imagen': primera_foto.imagen if primera_foto else None,
                'es_destacado': lugar.es_destacado,
                'es_exclusivo': lugar.es_exclusivo,
                'url': f"/lugares/{lugar.slug}/" if lugar.slug else None,
                'distancia': round(lugar.distancia_metros.km, 2) if hasattr(lugar, 'distancia_metros') and lugar.distancia_metros else None,
                'direccion': lugar.direccion
            })
        
        return JsonResponse({
            'success': True,
            'total': len(resultados),
            'lugares': resultados,
            'ubicacion_usuario': {
                'lat': lat,
                'lng': lng,
                'radio': radio
            },
            'mensaje': f'Encontramos {len(resultados)} lugares en un radio de {int(radio * 1000)}m' if radio < 1 else f'Encontramos {len(resultados)} lugares en un radio de {radio}km'
        })
        
    except ValueError:
        return JsonResponse({
            'error': 'Las coordenadas proporcionadas no son válidas'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': f'Error al buscar lugares cercanos: {str(e)}'
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

@require_POST
def newsletter_subscribe(request):
    """Vista para manejar suscripciones al newsletter."""
    try:
        # Obtener datos del POST
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        email = data.get('email', '').strip().lower()
        nombre = data.get('nombre', '').strip()

        # Validar email
        if not email:
            return JsonResponse({
                'success': False,
                'error': 'El email es requerido'
            }, status=400)

        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({
                'success': False,
                'error': 'El formato del email no es válido'
            }, status=400)

        # Obtener información adicional
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]  # Limitar tamaño

        # Verificar si ya existe
        existing_subscription = NewsletterSubscription.objects.filter(email=email).first()
        
        if existing_subscription:
            if existing_subscription.activo:
                return JsonResponse({
                    'success': True,
                    'message': '¡Ya estás suscrito! Gracias por tu interés en Medellín Explorer.',
                    'status': 'already_subscribed'
                })
            else:
                # Reactivar suscripción
                existing_subscription.reactivar()
                return JsonResponse({
                    'success': True,
                    'message': '¡Hemos reactivado tu suscripción! Pronto recibirás nuestras recomendaciones.',
                    'status': 'reactivated'
                })

        # Crear nueva suscripción
        subscription = NewsletterSubscription.objects.create(
            email=email,
            nombre=nombre,
            ip_address=ip_address,
            user_agent=user_agent,
            fuente='website_footer'
        )

        # En un entorno de producción, aquí enviarías un email de confirmación
        # send_confirmation_email(subscription)

        return JsonResponse({
            'success': True,
            'message': '¡Gracias por suscribirte! Te mantendremos informado sobre los mejores lugares de Medellín.',
            'status': 'new_subscription',
            'subscription_id': subscription.id
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Datos JSON inválidos'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error interno del servidor: {str(e)}'
        }, status=500)

@require_GET
def newsletter_confirm(request, token):
    """Vista para confirmar suscripción via email."""
    try:
        subscription = get_object_or_404(
            NewsletterSubscription, 
            token_confirmacion=token,
            activo=True
        )
        
        if subscription.confirmado:
            return render(request, 'newsletter/already_confirmed.html', {
                'subscription': subscription
            })
        
        subscription.confirmar_suscripcion()
        
        return render(request, 'newsletter/confirmation_success.html', {
            'subscription': subscription
        })
        
    except Exception as e:
        return render(request, 'newsletter/confirmation_error.html', {
            'error': str(e)
        })

@require_GET
def newsletter_unsubscribe(request, token):
    """Vista para dar de baja del newsletter."""
    try:
        subscription = get_object_or_404(
            NewsletterSubscription, 
            token_confirmacion=token
        )
        
        subscription.desactivar()
        
        return render(request, 'newsletter/unsubscribe_success.html', {
            'subscription': subscription
        })
        
    except Exception as e:
        return render(request, 'newsletter/unsubscribe_error.html', {
            'error': str(e)
        })

@require_GET
def newsletter_stats(request):
    """Vista para estadísticas del newsletter (solo para staff)."""
    if not request.user.is_staff:
        return JsonResponse({
            'error': 'Acceso denegado'
        }, status=403)
    
    stats = {
        'total_suscriptores': NewsletterSubscription.total_suscriptores(),
        'suscriptores_activos': NewsletterSubscription.objects.filter(activo=True).count(),
        'suscriptores_confirmados': NewsletterSubscription.objects.filter(confirmado=True).count(),
        'suscriptores_pendientes': NewsletterSubscription.objects.filter(
            activo=True, 
            confirmado=False
        ).count(),
        'suscripciones_hoy': NewsletterSubscription.objects.filter(
            fecha_suscripcion__date=timezone.now().date()
        ).count(),
    }
    
    return JsonResponse(stats)


# ────────────────────────────────────────────────────────────────────────
# AJAX Views para Progressive Loading de Lugares Relacionados
# ────────────────────────────────────────────────────────────────────────

@require_GET
def lugares_cercanos_ajax(request, slug):
    """AJAX endpoint para cargar lugares cercanos."""
    try:
        lugar = Places.objects.filter(tiene_fotos=True, slug=slug).first()
        if not lugar:
            return JsonResponse({'error': 'Lugar no encontrado'}, status=404)
        
        view = PlaceDetailView()
        lugares_cercanos = view._get_lugares_cercanos(lugar) if lugar.ubicacion else []
        
        # Serializar lugares
        data = []
        for lugar_cercano in lugares_cercanos:
            data.append({
                'id': lugar_cercano.id,
                'nombre': lugar_cercano.nombre,
                'slug': lugar_cercano.slug,
                'tipo': lugar_cercano.get_tipo_display(),
                'rating': lugar_cercano.rating,
                'es_destacado': lugar_cercano.es_destacado,
                'es_exclusivo': lugar_cercano.es_exclusivo,
                'imagen': lugar_cercano.cached_fotos[0].imagen if lugar_cercano.cached_fotos else None,
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
            return JsonResponse({'error': 'Lugar no encontrado'}, status=404)
        
        view = PlaceDetailView()
        lugares_similares = view._get_lugares_similares(lugar)
        
        # Serializar lugares
        data = []
        for lugar_similar in lugares_similares:
            data.append({
                'id': lugar_similar.id,
                'nombre': lugar_similar.nombre,
                'slug': lugar_similar.slug,
                'tipo': lugar_similar.get_tipo_display(),
                'rating': lugar_similar.rating,
                'es_destacado': lugar_similar.es_destacado,
                'es_exclusivo': lugar_similar.es_exclusivo,
                'imagen': lugar_similar.cached_fotos[0].imagen if lugar_similar.cached_fotos else None,
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
            return JsonResponse({'error': 'Lugar no encontrado'}, status=404)
        
        view = PlaceDetailView()
        lugares_comuna = view._get_lugares_misma_comuna(lugar) if lugar.comuna_osm_id else []
        
        # Serializar lugares
        data = []
        for lugar_comuna_item in lugares_comuna:
            data.append({
                'id': lugar_comuna_item.id,
                'nombre': lugar_comuna_item.nombre,
                'slug': lugar_comuna_item.slug,
                'tipo': lugar_comuna_item.get_tipo_display(),
                'rating': lugar_comuna_item.rating,
                'es_destacado': lugar_comuna_item.es_destacado,
                'es_exclusivo': lugar_comuna_item.es_exclusivo,
                'imagen': lugar_comuna_item.cached_fotos[0].imagen if lugar_comuna_item.cached_fotos else None,
            })
        
        return JsonResponse({'lugares': data, 'comuna_nombre': lugar.comuna.name if hasattr(lugar, 'comuna') and lugar.comuna else 'esta zona'})
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500) 