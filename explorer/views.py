from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404, HttpResponse
from django.core.serializers import serialize
from django.utils.text import slugify
from django.core.cache import cache
from django.contrib.gis.db.models.functions import Transform
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q, Avg
from .models import Places, Favorito, RegionOSM, Foto
import json
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator

from django.http import JsonResponse
from django.core.serializers import serialize
from .models import ZonaCubierta
# ======================================================
# LIST VIEW CON CACHE Y PREFETCH OPTIMIZADO
# ======================================================

class LugaresListView(ListView):
    model = Places
    template_name = 'lugares/places_list.html'
    context_object_name = 'lugares'
    paginate_by = 12

    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()
        tipo = self.request.GET.get('tipo', '')
        sort = self.request.GET.get('sort', '')
        
        cache_key = f"lugares_list_modern_{query}_{tipo}_{sort}"
        
        # Intentar obtener del caché
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        # Si no está en caché, hacer la consulta optimizada
        queryset = super().get_queryset().prefetch_related('fotos')
        
        if query:
            queryset = queryset.filter(
                Q(nombre__icontains=query) | 
                Q(direccion__icontains=query) |
                Q(descripcion__icontains=query)
            )
        
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        
        # Ordenamiento
        if sort == 'rating':
            queryset = queryset.order_by('-rating', '-fecha_creacion')
        elif sort == 'recent':
            queryset = queryset.order_by('-fecha_creacion')
        elif sort == 'name':
            queryset = queryset.order_by('nombre')
        else:
            queryset = queryset.order_by('-fecha_creacion')
        
        # Cachear el resultado
        result = list(queryset)
        cache.set(cache_key, result, 300)  # 5 minutos
        
        return result
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Agregar favoritos del usuario si está autenticado
        if self.request.user.is_authenticated:
            user_favorites = Favorito.objects.filter(
                usuario=self.request.user
            ).values_list('lugar_id', flat=True)
            context['user_favorites'] = list(user_favorites)
        
        return context


class LugaresDetailView(DetailView):
    model = Places
    template_name = 'lugares/places_detail.html'
    context_object_name = 'lugar'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            lugar = self.get_object()
            context['es_favorito'] = Favorito.objects.filter(usuario=self.request.user, lugar=lugar).exists()
        else:
            context['es_favorito'] = False
        return context


class LugarReviewsView(DetailView):
    model = Places
    template_name = 'lugares/reviews_lugar.html'
    context_object_name = 'lugar'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lugar = self.get_object()
        context['reviews'] = lugar.reviews if lugar.reviews else []
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
    # Caché de 1 hora para el mapa
    cache_key = "mapa_explorar_data_v2"
    cached_data = cache.get(cache_key)
    
    if cached_data:
        return render(request, 'lugares/places_map.html', cached_data)

    # Obtener comunas
    comunas = RegionOSM.objects.filter(osm_id__in=OSM_IDS_MEDELLIN)

    # OPTIMIZACIÓN: Cargar todos los lugares con sus fotos de una vez
    todos_lugares = Places.objects.filter(
        slug__isnull=False,
        ubicacion__isnull=False
    ).exclude(
        slug=""
    ).prefetch_related(
        'fotos'
    ).select_related()  # Si hay FKs adicionales

    # Mapear lugares a comunas
    datos_lugares = []
    lugares_procesados = set()

    for comuna in comunas:
        # Obtener IDs de lugares de esta comuna (cacheado)
        cache_key_comuna = f"lugares_comuna_{comuna.osm_id}"
        lugar_ids = cache.get(cache_key_comuna)
        
        if lugar_ids is None:
            lugar_ids = list(Places.objects.filter(
                ubicacion__coveredby=comuna.geom.simplify(50)
            ).values_list('id', flat=True))
            cache.set(cache_key_comuna, lugar_ids, 3600)

        # Procesar lugares
        for lugar in todos_lugares:
            if lugar.id in lugar_ids and lugar.id not in lugares_procesados:
                lugares_procesados.add(lugar.id)
                
                imagen_url = ""
                if lugar.fotos.exists():
                    primera_foto = lugar.fotos.first()
                    if primera_foto and primera_foto.imagen:
                        try:
                            # Asumimos que la imagen ya es una URL completa
                            imagen_url = primera_foto.imagen
                        except:
                            pass

                datos_lugares.append({
                    'slug': lugar.slug,
                    'nombre': lugar.nombre,
                    'lat': lugar.ubicacion.y,
                    'lng': lugar.ubicacion.x,
                    'tipo': lugar.tipo,
                    'rating': lugar.rating,
                    'imagen': imagen_url,
                    'comuna_id': comuna.osm_id,
                    'comuna_nombre': comuna.name
                })

    # Preparar datos de comunas
    datos_comunas = [
        {
            'id': comuna.osm_id,
            'name': comuna.name,
            'geometry': json.loads(comuna.geom.transform(4326, clone=True).geojson)
        }
        for comuna in comunas if comuna.geom
    ]

    result_data = {
        'lugares_json': json.dumps(datos_lugares),
        'comunas_json': json.dumps(datos_comunas),
        'comunas_list': comunas,
    }
    
    # Cachear resultado
    cache.set(cache_key, result_data, 3600)  # 1 hora
    
    return render(request, 'lugares/places_map.html', result_data)




@login_required
def guardar_favorito(request, pk):
    if request.method == 'POST':
        lugar = get_object_or_404(Places, pk=pk)
        favorito, created = Favorito.objects.get_or_create(
            usuario=request.user,
            lugar=lugar
        )
        if not created:
            favorito.delete()
            return JsonResponse({'status': 'removed'})
        return JsonResponse({'status': 'added'})
    return JsonResponse({'status': 'error'})

@login_required
def mis_favoritos(request):
    # Optimizado con select_related y prefetch_related
    favoritos = Favorito.objects.filter(
        usuario=request.user
    ).select_related('lugar').prefetch_related('lugar__fotos')
    
    return render(request, 'usuarios/mis_favoritos.html', {
        'favoritos': favoritos
    })


def perfil_usuario(request):
    return render(request, 'usuarios/perfil.html')

def registro_usuario(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('explorer:login')  
    else:
        form = UserCreationForm()
    
    return render(request, 'usuarios/register.html', {'form': form})

@login_required
def eliminar_favorito(request, pk):
    favorito = get_object_or_404(Favorito, pk=pk, usuario=request.user)
    favorito.delete()
    return redirect('explorer:mis_favoritos')


def mapa_zonas(request):
    return render(request, 'lugares/zonas_mapa.html')


def acerca_de_view(request):
    lugares = Places.objects.exclude(ubicacion__isnull=True).values('id', 'nombre', 'direccion', 'ubicacion', 'slug')
    datos = [
        {
            'id': lugar['id'],
            'nombre': lugar['nombre'],
            'direccion': lugar['direccion'],
            'lat': lugar['ubicacion'].y,
            'lng': lugar['ubicacion'].x,
            'slug': lugar['slug'] if lugar['slug'] else slugify(lugar['nombre'])
        }
        for lugar in lugares if lugar['ubicacion']
    ]
    return render(request, 'lugares/acerca.html', {'lugares_json': datos})





# ======================================================
# COMUNAS
# ======================================================

def lugares_por_comuna_view(request, slug):
    cache_key_comuna = f"comuna_{slug}"
    cache_key_lugares = f"lugares_comuna_{slug}"

    comuna = cache.get(cache_key_comuna)
    lugares_queryset = cache.get(cache_key_lugares)

    if comuna is None:
        comunas = RegionOSM.objects.filter(name__isnull=False).defer('geom')
        comuna = next((c for c in comunas if slugify(c.name) == slug), None)
        if not comuna:
            raise Http404("Comuna no encontrada")
        cache.set(cache_key_comuna, comuna, 300)

    if lugares_queryset is None:
        lugares_queryset = Places.objects.filter(
            ubicacion__coveredby=comuna.geom.simplify(50)
        ).prefetch_related('fotos').filter(
            slug__isnull=False
        ).exclude(slug="").order_by("nombre")
        cache.set(cache_key_lugares, list(lugares_queryset), 300)

    paginator = Paginator(lugares_queryset, 6)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    lugares_json = []
    for lugar in page_obj:
        if lugar.slug and lugar.ubicacion:
            # Construir imagen absoluta
            imagen_url = ""
            if lugar.fotos.exists():
                primera_foto = lugar.fotos.first()
                if primera_foto and primera_foto.imagen:
                    try:
                        # Asumimos que la imagen ya es una URL completa
                        imagen_url = primera_foto.imagen
                    except:
                        pass
            else:
                imagen_url = ""

            lugares_json.append({
                "nombre": lugar.nombre,
                "lat": lugar.ubicacion.y,
                "lng": lugar.ubicacion.x,
                "slug": lugar.slug,
                "tipo": lugar.tipo,
                "imagen": imagen_url,
                "url": reverse("explorer:lugares_detail", kwargs={"slug": lugar.slug}),
                "comuna_id": comuna.osm_id
            })

    return render(request, "lugares/lugares_por_comuna.html", {
        "comuna_id": comuna.osm_id,
        "comuna_name": comuna.name,
        "lugares": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "page_obj": page_obj,
        "lugares_json": lugares_json,
    })

def home_view(request):
    # Caché de 30 minutos para la página home completa
    cache_key = "home_view_data_v2"
    comuna_con_lugares = cache.get(cache_key)

    if not comuna_con_lugares:
        # Obtener todas las comunas de una vez
        comunas = RegionOSM.objects.filter(
            osm_id__in=OSM_IDS_MEDELLIN, 
            name__isnull=False
        ).order_by("name")

        # OPTIMIZACIÓN CLAVE: Obtener TODOS los lugares de Medellín de una vez
        # y filtrarlos en Python en lugar de hacer queries geográficas múltiples
        todos_lugares = list(Places.objects.filter(
            slug__isnull=False,
            ubicacion__isnull=False
        ).exclude(
            slug=""
        ).prefetch_related(
            Prefetch('fotos', queryset=Foto.objects.only('imagen'))
        ).values(
            'id', 'nombre', 'slug', 'tipo', 'rating', 
            'ubicacion', 'fotos__imagen'
        ))

        comuna_con_lugares = []

        for comuna in comunas:
            if " - " in comuna.name:
                ref, nombre = comuna.name.split(" - ", 1)
            else:
                ref = "Comuna"
                nombre = comuna.name

            # Solo hacer la query geográfica una vez por comuna y cachearla
            cache_key_comuna = f"lugares_comuna_{comuna.osm_id}"
            lugar_ids = cache.get(cache_key_comuna)
            
            if lugar_ids is None:
                # Esta es la query costosa - la cacheamos por 1 hora
                lugar_ids = list(Places.objects.filter(
                    ubicacion__coveredby=comuna.geom.simplify(50),
                    slug__isnull=False
                ).exclude(slug="").values_list('id', flat=True))
                cache.set(cache_key_comuna, lugar_ids, 3600)
            
            # Filtrar los lugares ya cargados
            lugares_json = []
            for lugar_data in todos_lugares:
                if lugar_data['id'] in lugar_ids:
                    # La imagen ahora viene directamente de la relación con Foto
                    imagen_url = lugar_data.get('fotos__imagen')

                    lugares_json.append({
                        "nombre": lugar_data['nombre'],
                        "slug": lugar_data['slug'],
                        "tipo": lugar_data['tipo'],
                        "rating": lugar_data['rating'],
                        "imagen": imagen_url,
                    })
                    
                    if len(lugares_json) >= 3:  # Solo mostrar top 3
                        break

            comuna_con_lugares.append({
                "comuna": comuna,
                "nombre": nombre,
                "ref": ref,
                "lugares": sorted(lugares_json, key=lambda x: x.get('rating') or 0, reverse=True)[:3],
            })

        # Cachear por 30 minutos
        cache.set(cache_key, comuna_con_lugares, 1800)

    return render(request, "home.html", {
        "comuna_con_lugares": comuna_con_lugares
    })


def home_modern_view(request):
    """Vista optimizada para el diseño moderno sin consultas de comunas"""
    # Caché simple para estadísticas
    cache_key = "home_stats"
    stats = cache.get(cache_key)
    
    if not stats:
        stats = {
            'total_lugares': Places.objects.count(),
            'total_comunas': 16,  # Fijo, sabemos que son 16
            'promedio_rating': Places.objects.aggregate(avg_rating=Avg('rating'))['avg_rating'] or 4.8
        }
        cache.set(cache_key, stats, 3600)  # 1 hora
    
    return render(request, "home_modern.html", stats)



def zonas_geojson(request):
    data = serialize('geojson', ZonaCubierta.objects.all(), geometry_field='poligono', fields=('nombre',))
    return HttpResponse(data, content_type='application/json')




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


