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
from .models import Places, Favorito, RegionOSM
import json
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator

from django.http import JsonResponse
from django.core.serializers import serialize
from .models import ZonaCubierta
# ======================================================
# LIST VIEW CON CACHE SOLO DEL QUERYSET
# ======================================================

class LugaresListView(ListView):
    model = Places
    template_name = 'lugares/places_list.html'
    context_object_name = 'lugares'
    ordering = ['-fecha_creacion']
    paginate_by = 9

    def get_queryset(self):
        query = self.request.GET.get('q') or ''
        cache_key = f"lugares_list_{query}"

        queryset = cache.get(cache_key)
        if queryset is None:
            queryset = super().get_queryset()
            if query:
                queryset = queryset.filter(
                    nombre__icontains=query
                ) | queryset.filter(
                    direccion__icontains=query
                )
            cache.set(cache_key, list(queryset), 300)  # Cacheamos la lista para que sea serializable

        return queryset


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
    template_name = "lugares/reviews_lugar.html"
    context_object_name = "lugar"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lugar = self.get_object()

        # Limpia los textos de las reseñas si existen
        cleaned_reviews = []
        for r in lugar.reviews:
            text = r.get("text", "")
            cleaned = text.lstrip() if text else ""
            r["text"] = cleaned
            cleaned_reviews.append(r)

        context["reviews"] = cleaned_reviews
        return context

# ======================================================
# VISTAS PERSONALIZADAS
# ======================================================

OSM_IDS_MEDELLIN = [
    -7680678, -7680807, -7680859, -11937925,
    -7676068, -7676069, -7680798, -7680904, -7680903,
    -7673972, -7673973, -7680403, -7673971, -7677386,
    -7680799, -7680490
]

def mapa_explorar(request):
    comunas = RegionOSM.objects.filter(osm_id__in=OSM_IDS_MEDELLIN)

    datos_lugares = []
    for comuna in comunas:
        lugares_de_comuna = Places.objects.filter(
            ubicacion__coveredby=comuna.geom.simplify(50),
            slug__isnull=False
        ).exclude(slug="")

        for lugar in lugares_de_comuna:
            # Prioridad: lugar.imagen > lugar.fotos.first
            imagen_url = ""
            if lugar.imagen and hasattr(lugar.imagen, "url"):
                try:
                    imagen_url = request.build_absolute_uri(lugar.imagen.url)
                except:
                    pass
            elif lugar.fotos.exists():
                primera_foto = lugar.fotos.first()
                if primera_foto.imagen and hasattr(primera_foto.imagen, "url"):
                    try:
                        imagen_url = request.build_absolute_uri(primera_foto.imagen.url)
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

    datos_comunas = [
        {
            'id': comuna.osm_id,
            'name': comuna.name,
            'geometry': json.loads(comuna.geom.transform(4326, clone=True).geojson)
        }
        for comuna in comunas if comuna.geom
    ]

    return render(request, 'lugares/places_map.html', {
        'lugares_json': json.dumps(datos_lugares),
        'comunas_json': json.dumps(datos_comunas),
        'comunas_list': comunas,
    })



def registro_usuario(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'usuarios/registro.html', {'form': form})

@login_required
def guardar_favorito(request, pk):
    lugar = get_object_or_404(Places, pk=pk)
    Favorito.objects.get_or_create(usuario=request.user, lugar=lugar)
    return redirect('explorer:lugares_detail', slug=lugar.slug)


@login_required
def mis_favoritos(request):
    favoritos = Favorito.objects.filter(usuario=request.user)
    return render(request, 'usuarios/mis_favoritos.html', {'favoritos': favoritos})

@login_required
def eliminar_favorito(request, pk):
    favorito = get_object_or_404(Favorito, pk=pk, usuario=request.user)
    favorito.delete()
    return redirect('explorer:mis_favoritos')

@login_required
def perfil_usuario(request):
    favoritos = Favorito.objects.filter(usuario=request.user).select_related('lugar')
    return render(request, 'usuarios/perfil.html', {'favoritos': favoritos})


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

OSM_IDS_MEDELLIN = [
    -7680678, -7680807, -7680859, -11937925,
    -7676068, -7676069, -7680798, -7680904, -7680903,
    -7673972, -7673973, -7680403, -7673971, -7677386,
    -7680799, -7680490
]


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
        ).filter(slug__isnull=False).exclude(slug="").order_by("nombre")
        cache.set(cache_key_lugares, list(lugares_queryset), 300)

    paginator = Paginator(lugares_queryset, 6)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    lugares_json = []
    for lugar in page_obj:
        if lugar.slug and lugar.ubicacion:
            # Construir imagen absoluta
            if lugar.imagen and hasattr(lugar.imagen, "url"):
                imagen_url = request.build_absolute_uri(lugar.imagen.url)
            elif lugar.fotos.exists() and lugar.fotos.first().imagen and hasattr(lugar.fotos.first().imagen, "url"):
                imagen_url = request.build_absolute_uri(lugar.fotos.first().imagen.url)
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
    comuna_con_lugares = cache.get("comunas_y_lugares")

    if not comuna_con_lugares:
        comunas = RegionOSM.objects.filter(
            osm_id__in=OSM_IDS_MEDELLIN, name__isnull=False
        ).order_by("name")

        comuna_con_lugares = []

        for comuna in comunas:
            if " - " in comuna.name:
                ref, nombre = comuna.name.split(" - ", 1)
            else:
                ref = "Comuna"
                nombre = comuna.name

            # Solo lugares válidos con slug e imagen
            lugares_qs = (
                Places.objects.filter(
                    ubicacion__coveredby=comuna.geom.simplify(50),
                    slug__isnull=False
                )
                .exclude(slug="")
                .order_by("-rating")[:3]
            )

            lugares_json = []
            for lugar in lugares_qs:
                imagen_url = None
                if hasattr(lugar, "fotos") and lugar.fotos.exists():
                    imagen_url = lugar.fotos.first().imagen.url
                elif lugar.imagen and hasattr(lugar.imagen, "url"):
                    imagen_url = lugar.imagen.url

                lugares_json.append({
                    "nombre": lugar.nombre,
                    "slug": lugar.slug,
                    "tipo": lugar.tipo,
                    "rating": lugar.rating,
                    "imagen": imagen_url,
                })

            comuna_con_lugares.append({
                "comuna": comuna,
                "nombre": nombre,
                "ref": ref,
                "lugares": lugares_json,
            })

        cache.set("comunas_y_lugares", comuna_con_lugares, 600)

    return render(request, "home.html", {
        "comuna_con_lugares": comuna_con_lugares
    })



def zonas_geojson(request):
    data = serialize('geojson', ZonaCubierta.objects.all(), geometry_field='poligono', fields=('nombre',))
    return HttpResponse(data, content_type='application/json')

def mapa_zonas(request):
    return render(request, "lugares/zonas_mapa.html")



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


