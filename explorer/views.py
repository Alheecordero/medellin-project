from django.views.generic import ListView, DetailView, TemplateView

from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404, HttpResponse
from django.core.serializers import serialize
from django.utils.text import slugify
from django.core.cache import cache
from django.contrib.gis.db.models.functions import Transform, Distance
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Prefetch, Q, Avg, Count
from .models import Places, Foto, ZonaCubierta, RegionOSM, Initialgrid
import json
import math
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator

from django.http import JsonResponse
from django.templatetags.static import static
from django.conf import settings
import os
import time

# ======================================================
# LIST VIEW CON CACHE Y PREFETCH OPTIMIZADO
# ======================================================

class LugaresListView(ListView):
    model = Places
    template_name = 'lugares/places_list.html'
    context_object_name = 'lugares'
    paginate_by = 12

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related(
            Prefetch('fotos', queryset=Foto.objects.only('imagen'), to_attr='cached_fotos')
        ).order_by('-fecha_actualizacion')

        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(nombre__icontains=query) | 
                Q(tipo__icontains=query) |
                Q(direccion__icontains=query)
            )
        
        comuna_slug = self.kwargs.get('slug')
        if comuna_slug:
            queryset = queryset.filter(comuna__slug=comuna_slug)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        context['comuna_slug'] = self.kwargs.get('slug', '')
        return context


class LugaresDetailView(DetailView):
    model = Places
    template_name = 'lugares/places_detail.html'
    context_object_name = 'lugar'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lugar = self.get_object()

        # Usar la consulta explícita para fotos
        context['fotos_lugar'] = Foto.objects.filter(lugar=lugar)
        
        # Obtener la primera foto para la imagen principal
        primera_foto = context['fotos_lugar'].first()
        context['primera_foto_url'] = primera_foto.imagen if primera_foto and primera_foto.imagen else None

        if lugar.ubicacion:
            # Obtener 5 lugares cercanos
            context['lugares_cercanos'] = Places.objects.exclude(id=lugar.id).filter(
                ubicacion__distance_lt=(lugar.ubicacion, 1000)
            ).annotate(
                distance=Distance('ubicacion', lugar.ubicacion)
            ).order_by('distance')[:5]

        return context






# ======================================================
# VISTAS PERSONALIZADAS OPTIMIZADAS
# ======================================================

OSM_IDS_MEDELLIN = [
    -7680678, -7680807, -7680859, -11937925,
    -7676068, -7676069, -7680798, -7680904, -7680903,
    -7673972, -7673973, -7680403, -7673971, -7677386,
    -7680799, -7680490
]

def mapa_explorar(request):
    """
    Vista mejorada del mapa con soporte para comunas y lugares
    """
    # Obtener comunas (admin_level='8') y municipios (admin_level='6')
    comunas = RegionOSM.objects.filter(
        admin_level__in=['6', '8']
    ).annotate(
        geom_transformed=Transform('geom_4326', 3857)
    )

    # Preparar datos de comunas para el mapa
    comunas_json = []
    for c in comunas:
        if c.geom_4326:  # Asegurarse de que tiene geometría
            comunas_json.append({
                "id": c.osm_id,
                "name": c.name,
                "geometry": json.loads(c.geom_4326.geojson),
                "admin_level": c.admin_level,
                "ciudad": c.ciudad
            })

    # Obtener lugares destacados
    lugares = Places.objects.filter(
        rating__gte=4.0,
        total_reviews__gte=5
    ).select_related().prefetch_related(
        Prefetch('fotos', queryset=Foto.objects.only('imagen'), to_attr='cached_fotos')
    ).order_by('-rating', '-total_reviews')[:100]

    # Preparar datos de lugares para el mapa
    lugares_json = []
    for lugar in lugares:
        primera_foto = lugar.cached_fotos[0] if lugar.cached_fotos else None
        image_url = primera_foto.imagen if primera_foto and primera_foto.imagen else static('img/placeholder.jpg')

        lugares_json.append({
            "id": lugar.id,
            "nombre": lugar.nombre,
            "lat": lugar.ubicacion.y if lugar.ubicacion else None,
            "lng": lugar.ubicacion.x if lugar.ubicacion else None,
            "slug": lugar.slug,
            "tipo": lugar.tipo,
            "rating": float(lugar.rating) if lugar.rating else None,
            "total_reviews": lugar.total_reviews,
            "direccion": lugar.direccion,
            "imagen": image_url,
            "comuna_id": lugar.comuna_osm_id
        })

    context = {
        'comunas_json': json.dumps(comunas_json),
        'lugares_json': json.dumps(lugares_json),
    }
    
    return render(request, "lugares/places_map.html", context)


@require_GET
def buscar_lugares_cercanos(request):
    """
    API endpoint para buscar lugares en un radio de 500 metros desde un punto.
    """
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lng'))
        radio_metros = float(request.GET.get('radio', 500))  # Por defecto 500 metros
        
        # Caching por coordenada redondeada (aprox 10-20 m de precisión)
        cache_key = f"nearby_{round(lat,4)}_{round(lng,4)}_{int(radio_metros)}"
        cached = cache.get(cache_key)
        if cached:
            return JsonResponse({'success': True, 'lugares': cached})

        from django.contrib.gis.geos import Point
        punto_usuario = Point(lng, lat, srid=4326)

        # Query optimizada: seleccionar solo los campos necesarios y diferir columnas grandes
        lugares_cercanos = (
            Places.objects.only(
                'id', 'nombre', 'ubicacion', 'slug', 'tipo', 'rating', 'total_reviews', 'direccion'
            )
            .filter(ubicacion__distance_lte=(punto_usuario, radio_metros))
            .annotate(distance=Distance('ubicacion', punto_usuario))
            .order_by('distance')[:50]
            .prefetch_related(
                Prefetch('fotos', queryset=Foto.objects.only('imagen'), to_attr='cached_fotos')
            )
        )
        
        # Serializar resultados
        lugares_data = []
        for lugar in lugares_cercanos:
            primera_foto = lugar.cached_fotos[0] if lugar.cached_fotos else None
            image_url = primera_foto.imagen if primera_foto and primera_foto.imagen else static('img/placeholder.jpg')

            lugares_data.append({
                "id": lugar.id,
                "nombre": lugar.nombre,
                "lat": lugar.ubicacion.y,
                "lng": lugar.ubicacion.x,
                "slug": lugar.slug,
                "tipo": lugar.tipo,
                "rating": float(lugar.rating) if lugar.rating else None,
                "total_reviews": lugar.total_reviews,
                "direccion": lugar.direccion,
                "imagen": image_url,
                "distance": round(lugar.distance.m)
            })
        
        # Guardar en caché por 1 minuto
        cache.set(cache_key, lugares_data, 60)

        return JsonResponse({'success': True, 'lugares': lugares_data})
        
    except (ValueError, TypeError) as e:
        return JsonResponse({'success': False, 'error': 'Coordenadas inválidas', 'message': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': 'Error interno del servidor', 'message': str(e)}, status=500)













# ======================================================
# COMUNAS
# ======================================================

def lugares_por_comuna_view(request, slug):
    """
    Muestra los lugares de una comuna o municipio específico, identificado por su slug.
    """
    # El modelo RegionOSM no tiene un campo slug, por lo que no podemos filtrar directamente.
    # Obtenemos todas las regiones (comunas y municipios) y encontramos la que coincide con el slug.
    regiones = RegionOSM.objects.filter(admin_level__in=['6', '8'])
    comuna_seleccionada = None
    for region in regiones:
        if region.slug == slug:
            comuna_seleccionada = region
            break

    if not comuna_seleccionada:
        # Si no se encuentra la comuna/municipio, devolver un 404.
        raise Http404("Comuna o municipio no encontrado")

    # Obtener los lugares que pertenecen a esa comuna/municipio.
    lugares_en_comuna = Places.objects.filter(comuna_osm_id=comuna_seleccionada.osm_id).prefetch_related('fotos')

    context = {
        'comuna': comuna_seleccionada,
        'lugares': lugares_en_comuna,
        'es_municipio': comuna_seleccionada.admin_level == '6'
    }
    return render(request, 'lugares/lugares_por_comuna.html', context)

# Vista de home refactorizada
def home(request):
    """
    Vista para la página de inicio. Muestra una selección de lugares
    agrupados por comunas y categorías.
    """
    try:
        # Obtener lugares destacados - simplificado
        lugares_destacados = []
        lugares_query = Places.objects.filter(
            rating__gte=4.5,
            total_reviews__gte=10,
            fotos__isnull=False
        ).select_related().prefetch_related('fotos').order_by('-rating', '-total_reviews').distinct()[:12]
        
        for lugar in lugares_query:
            primera_foto = lugar.get_primera_foto()
            lugares_destacados.append({
                'nombre': lugar.nombre,
                'slug': lugar.slug,
                'rating': lugar.rating,
                'tipo': lugar.get_tipo_display() if hasattr(lugar, 'get_tipo_display') else lugar.tipo,  # type: ignore
                'imagen': primera_foto.imagen if primera_foto else None,
                'direccion': lugar.direccion,
                'comuna': lugar.comuna
            })

        # Obtener comunas y municipios con lugares
        comuna_con_lugares = []
        
        # Primero las comunas de Medellín (admin_level='8')
        comunas_medellin = RegionOSM.objects.filter(
            admin_level='8',
            ciudad='Medellín'
        ).order_by('name')[:6]
        
        # Luego los municipios cercanos (admin_level='6')
        municipios_cercanos = RegionOSM.objects.filter(
            admin_level='6'
        ).order_by('name')
        
        print(f"Comunas Medellín encontradas: {comunas_medellin.count()}")
        print(f"Municipios cercanos encontrados: {municipios_cercanos.count()}")

        # Procesar comunas de Medellín
        for comuna in comunas_medellin:
            lugares_comuna = Places.objects.filter(
                comuna_osm_id=comuna.osm_id,
                rating__gte=4.0,
                fotos__isnull=False
            ).select_related().prefetch_related('fotos').order_by('-rating').distinct()[:3]
            
            lugares_data = []
            for lugar in lugares_comuna:
                primera_foto = lugar.get_primera_foto()
                lugares_data.append({
                    'nombre': lugar.nombre,
                    'slug': lugar.slug,
                    'rating': lugar.rating,
                    'tipo': lugar.get_tipo_display() if hasattr(lugar, 'get_tipo_display') else lugar.tipo,  # type: ignore
                    'imagen': primera_foto.imagen if primera_foto else None
                })
            
            if lugares_data:
                comuna_con_lugares.append({
                    'comuna': comuna,
                    'nombre': comuna.name,
                    'ref': f"Comuna de Medellín",
                    'lugares': lugares_data,
                    'es_municipio': False
                })
        
        # Procesar municipios cercanos
        for municipio in municipios_cercanos:
            lugares_municipio = Places.objects.filter(
                comuna_osm_id=municipio.osm_id,
                rating__gte=4.0,
                fotos__isnull=False
            ).select_related().prefetch_related('fotos').order_by('-rating').distinct()[:3]
            
            lugares_data = []
            for lugar in lugares_municipio:
                primera_foto = lugar.get_primera_foto()
                lugares_data.append({
                    'nombre': lugar.nombre,
                    'slug': lugar.slug,
                    'rating': lugar.rating,
                    'tipo': lugar.get_tipo_display() if hasattr(lugar, 'get_tipo_display') else lugar.tipo,  # type: ignore
                    'imagen': primera_foto.imagen if primera_foto else None
                })
            
            if lugares_data:
                comuna_con_lugares.append({
                    'comuna': municipio,
                    'nombre': municipio.name,
                    'ref': f"Municipio del Valle de Aburrá",
                    'lugares': lugares_data,
                    'es_municipio': True
                })

        # Si no hay comunas con lugares, al menos mostrar lugares destacados agrupados
        if not comuna_con_lugares and lugares_destacados:
            comuna_con_lugares = [{
                'comuna': None,
                'nombre': 'Lugares Destacados',
                'ref': 'Los mejores lugares de Medellín',
                'lugares': [
                    {
                        'nombre': l['nombre'],
                        'slug': l['slug'],
                        'rating': l['rating'],
                        'tipo': l['tipo'],
                        'imagen': l['imagen']
                    }
                    for l in lugares_destacados[:9]
                ],
                'es_municipio': False
            }]

        # Estadísticas
        total_lugares = Places.objects.count()
        total_comunas = RegionOSM.objects.filter(admin_level__in=['6', '8']).count()

        print(f"Lugares destacados: {len(lugares_destacados)}")
        print(f"Comunas/Municipios con lugares: {len(comuna_con_lugares)}")
        
        context = {
            'lugares_destacados': lugares_destacados,
            'comuna_con_lugares': comuna_con_lugares,
            'total_lugares': total_lugares,
            'total_comunas': total_comunas,
        }
        
        return render(request, 'home.html', context)
        
    except Exception as e:
        print(f"Error en la vista home: {e}")
        import traceback
        traceback.print_exc()
        # En caso de error, renderiza con datos mínimos
        return render(request, 'home.html', {
            'lugares_destacados': [],
            'comuna_con_lugares': [],
            'total_lugares': 17000,
            'total_comunas': 22,
        })

def lugares_detail(request, slug):
    """
    Muestra la página de detalle de un lugar específico.
    """
    lugar = get_object_or_404(Places.objects.prefetch_related('fotos'), slug=slug)
    comuna = lugar.comuna
    
    context = {
        'lugar': lugar,
        'comuna': comuna,
    }
    return render(request, 'lugares/places_detail.html', context)


def lugares_list(request):
    """
    Vista principal que muestra la lista de lugares con búsqueda y filtros.
    """
    from .models import PLACE_TYPE_CHOICES
    
    # Obtener todos los lugares
    lugares_queryset = Places.objects.prefetch_related(
        Prefetch('fotos', queryset=Foto.objects.only('imagen'), to_attr='cached_fotos')
    ).select_related().order_by('-rating', '-total_reviews')
    
    # Filtro por búsqueda
    query = request.GET.get('q', '')
    if query:
        lugares_queryset = lugares_queryset.filter(
            Q(nombre__icontains=query) | 
            Q(direccion__icontains=query) |
            Q(tipo__icontains=query)
        )
    
    # Filtro por tipo
    tipo_filter = request.GET.get('tipo', '')
    if tipo_filter:
        lugares_queryset = lugares_queryset.filter(tipo=tipo_filter)
    
    # Paginación
    paginator = Paginator(lugares_queryset, 12)  # 12 lugares por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Agregar is_paginated para compatibilidad con template
    is_paginated = page_obj.has_other_pages()
    
    context = {
        'lugares': page_obj,  # El template espera la lista en 'lugares'
        'page_obj': page_obj,  # También proporcionar page_obj para paginación
        'is_paginated': is_paginated,
        'query': query,
        'tipo_choices': PLACE_TYPE_CHOICES,
        'tipo_filter': tipo_filter,
    }
    
    return render(request, 'lugares/places_list.html', context)











#vistas AJAX 
@require_GET
def autocomplete_places_view(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        term = request.GET.get('term', '')
        resultados = Places.objects.filter(nombre__icontains=term).order_by('nombre')[:10]
        data = [
            {'label': lugar.nombre, 'value': lugar.nombre, 'slug': lugar.slug}
            for lugar in resultados
        ]
        return JsonResponse(data, safe=False)
    return JsonResponse([], safe=False)


@require_GET
def lugares_destacados(request):
    """Obtiene los mejores lugares destacados para mostrar en el mapa inicial"""
    try:
        cache_key = "featured_places_v1"
        cached = cache.get(cache_key)
        if cached:
            return JsonResponse({'success': True, 'lugares': cached})

        lugares_destacados = (
            Places.objects.only(
                'id', 'nombre', 'ubicacion', 'slug', 'tipo', 'rating', 'total_reviews', 'direccion'
            )
            .filter(rating__gte=4.0)
            .annotate(review_count=Count('reviews'))
            .filter(review_count__gte=5)
            .order_by('-rating', '-review_count')[:15]
            .prefetch_related(
                Prefetch('fotos', queryset=Foto.objects.only('imagen'), to_attr='cached_fotos')
            )
        )
        
        lugares_data = []
        for lugar in lugares_destacados:
            cached_fotos = getattr(lugar, 'cached_fotos', [])
            primera_foto = cached_fotos[0] if cached_fotos else None
            
            image_url = static('img/placeholder.jpg')
            if primera_foto and primera_foto.imagen:
                image_url = primera_foto.imagen

            lugares_data.append({
                "id": lugar.id,
                "nombre": lugar.nombre,
                "lat": lugar.ubicacion.y,
                "lng": lugar.ubicacion.x,
                "slug": lugar.slug,
                "tipo": lugar.tipo,
                "rating": float(lugar.rating) if lugar.rating else None,
                "total_reviews": lugar.review_count,
                "direccion": lugar.direccion,
                "imagen": image_url,
                "distance": None
            })
        
        # Cachear resultado por 10 minutos
        cache.set(cache_key, lugares_data, 600)

        return JsonResponse({'success': True, 'lugares': lugares_data})
        
    except Exception as e:
        # For debugging purposes
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': 'Error al cargar lugares destacados',
            'message': str(e)
        }, status=500)


# ======================================================
# VISTA ADMINISTRATIVA DEL MAPA
# ======================================================

def admin_mapa_regiones(request):
    """Vista de mapa simple para visualización de las Zonas Cubiertas y puntos guardados."""
    zonas_cubiertas = ZonaCubierta.objects.all()
    file_path = os.path.join(settings.BASE_DIR, 'coordenadas_guardadas.json')
    
    # Preparar datos de zonas cubiertas
    zonas_data = [
        {'geometry': json.loads(z.poligono.geojson)}
        for z in zonas_cubiertas if z.poligono
    ]
    
    # Cargar los puntos guardados desde el archivo GeoJSON
    puntos_guardados_geojson = {'type': 'FeatureCollection', 'features': []}
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            try:
                puntos_guardados_geojson = json.load(f)
            except json.JSONDecodeError:
                pass  # Si el archivo está corrupto o vacío, se ignora
    
    context = {
        'zonas_cubiertas_json': json.dumps(zonas_data),
        'puntos_guardados_json': json.dumps(puntos_guardados_geojson),
    }
    
    return render(request, "lugares/admin_mapa_regiones.html", context)


@require_GET 
def ejecutar_fetch_lugares(request):
    """Vista AJAX simple para ejecutar el script fetch_nearby_places_v2.py"""
    if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'error': 'Solo requests AJAX'}, status=400)
    
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')
    
    if not lat or not lng:
        return JsonResponse({'error': 'Faltan coordenadas lat/lng'}, status=400)
    
    try:
        import subprocess
        import os
        from django.conf import settings
        
        # Imprimir en terminal del servidor al iniciar
        print(f"\n{'='*60}")
        print(f"🚀 EJECUTANDO SCRIPT EN COORDENADAS: {lat}, {lng}")
        print(f"{'='*60}")
        
        # Ejecutar el script con output en tiempo real
        process = subprocess.Popen([
            'python', 'manage.py', 'fetch_nearby_places_v2', 
            '--lat', str(lat), 
            '--lng', str(lng)
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
           text=True, cwd=settings.BASE_DIR, bufsize=1, universal_newlines=True)
        
        # Mostrar output línea por línea en tiempo real
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(line.rstrip())  # Imprimir cada línea inmediatamente
        
        # Esperar a que termine el proceso
        process.wait()
        
        # Imprimir resultado final en terminal
        print(f"{'='*60}")
        if process.returncode == 0:
            print(f"✅ SCRIPT COMPLETADO EXITOSAMENTE")
            response_data = {
                'success': True, 
                'message': f'Script ejecutado exitosamente en {lat}, {lng}',
                'note': 'Ver logs en terminal del servidor'
            }
        else:
            print(f"❌ SCRIPT TERMINÓ CON ERRORES (código: {process.returncode})")
            response_data = {
                'success': False, 
                'error': f'Script terminó con código de error: {process.returncode}',
                'note': 'Ver detalles en terminal del servidor'
            }
        
        print(f"{'='*60}\n")
        return JsonResponse(response_data)
            
    except Exception as e:
        print(f"\n❌ ERROR AL EJECUTAR SCRIPT: {str(e)}\n")
        return JsonResponse({'success': False, 'error': f'Error: {str(e)}'})

def guardar_coordenada_view(request):
    """
    Vista AJAX para guardar una coordenada clickeada en un archivo GeoJSON.
    """
    if not request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.method != 'POST':
        return JsonResponse({'error': 'Petición inválida'}, status=400)

    try:
        data = json.loads(request.body)
        lat = float(data.get('lat'))
        lng = float(data.get('lng'))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'error': 'Datos de coordenadas inválidos'}, status=400)

    file_path = os.path.join(settings.BASE_DIR, 'coordenadas_guardadas.json')
    
    try:
        # Estructura base de un GeoJSON FeatureCollection
        geojson_data = {'type': 'FeatureCollection', 'features': []}
        
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                try:
                    existing_data = json.load(f)
                    # Comprobar si es un GeoJSON válido o el formato antiguo (una lista)
                    if isinstance(existing_data, dict) and existing_data.get('type') == 'FeatureCollection':
                        geojson_data = existing_data
                    elif isinstance(existing_data, list):
                        # Convertir el formato antiguo a GeoJSON
                        for item in existing_data:
                            feature = {
                                'type': 'Feature',
                                'properties': {'timestamp': item.get('timestamp')},
                                'geometry': {
                                    'type': 'Point',
                                    'coordinates': [item.get('lng'), item.get('lat')]
                                }
                            }
                            geojson_data['features'].append(feature)
                except json.JSONDecodeError:
                    # El archivo está vacío o corrupto, se sobrescribirá
                    pass
        
        # Crear la nueva 'Feature' para la coordenada
        new_feature = {
            'type': 'Feature',
            'properties': {'timestamp': time.time()},
            'geometry': {
                'type': 'Point',
                'coordinates': [lng, lat]  # GeoJSON usa [longitud, latitud]
            }
        }
        geojson_data['features'].append(new_feature)
        
        # Guardar el archivo GeoJSON actualizado
        with open(file_path, 'w') as f:
            json.dump(geojson_data, f, indent=2)
            
        return JsonResponse({
            'success': True, 
            'message': f'Coordenada ({lat}, {lng}) guardada en GeoJSON. Total: {len(geojson_data["features"])}.'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)



# ======================================================
# VISTAS DUMMY PARA COMPATIBILIDAD CON TEMPLATES
# ======================================================

def acerca_view(request):
    """Vista dummy para la página acerca que redirige a home"""
    return redirect('explorer:home')

def perfil_dummy(request):
    """Vista dummy para perfil que redirige a home"""
    return redirect('explorer:home')

def favoritos_dummy(request):
    """Vista dummy para favoritos que redirige a home"""
    return redirect('explorer:home')

def resenas_dummy(request, slug):
    """Vista dummy para reseñas que redirige al detalle del lugar"""
    return redirect('explorer:lugares_detail', slug=slug)


