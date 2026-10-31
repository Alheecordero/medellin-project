from uuid import uuid4
import re

from django.apps import apps
from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.core.cache import cache
from django.db import models
from django.db.models import Count, Index, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.postgres.indexes import GistIndex
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
from django.utils.translation import get_language, gettext
from django.core.validators import EmailValidator
from pgvector.django import VectorField
from django.contrib.postgres.fields import ArrayField
from taggit.managers import TaggableManager
from taggit.models import TaggedItemBase, TagBase

# ────────────────────────────────────────────────────────────────
# Choices & constants
# ────────────────────────────────────────────────────────────────

# Mantengo tu lista tal cual; conviene moverla a un módulo aparte
# si crece más.
PLACE_TYPE_CHOICES = (
    ("acai_shop", "Tienda de açaí"),
    ("afghani_restaurant", "Restaurante afgano"),
    ("african_restaurant", "Restaurante africano"),
    ("american_restaurant", "Restaurante americano"),
    ("amusement_center", "Centro de entretenimiento"),
    ("art_studio", "Estudio de arte"),
    ("asian_restaurant", "Restaurante asiático"),
    ("auditorium", "Auditorio"),
    ("banquet_hall", "Salón de banquetes"),
    ("bar", "Bar"),
    ("bar_and_grill", "Bar y parrilla"),
    ("barbecue_area", "Área de barbacoa"),
    ("barbecue_restaurant", "Restaurante de barbacoa"),
    ("barber_shop", "Barbería"),
    ("beautician", "Esteticista"),
    ("beauty_salon", "Salón de belleza"),
    ("breakfast_restaurant", "Restaurante de desayunos"),
    ("brunch_restaurant", "Restaurante de brunch"),
    ("buffet_restaurant", "Restaurante buffet"),
    ("cafe", "Cafetería"),
    ("cafeteria", "Comedor"),
    ("car_wash", "Lavadero de autos"),
    ("cat_cafe", "Cafetería de gatos"),
    ("catering_service", "Servicio de catering"),
    ("childrens_camp", "Campamento infantil"),
    ("chinese_restaurant", "Restaurante chino"),
    ("cultural_center", "Centro cultural"),
    ("dessert_restaurant", "Restaurante de postres"),
    ("diner", "Cafetería clásica"),
    ("doctor", "Consultorio médico"),
    ("dog_cafe", "Cafetería de perros"),
    ("event_venue", "Lugar de eventos"),
    ("fast_food_restaurant", "Restaurante de comida rápida"),
    ("fine_dining_restaurant", "Restaurante gourmet"),
    ("food", "Tienda de alimentos"),
    ("food_court", "Patio de comidas"),
    ("food_delivery", "Entrega de comida"),
    ("french_restaurant", "Restaurante francés"),
    ("greek_restaurant", "Restaurante griego"),
    ("hamburger_restaurant", "Hamburguesería"),
    ("health", "Servicio de salud"),
    ("historical_landmark", "Monumento histórico"),
    ("indian_restaurant", "Restaurante indio"),
    ("internet_cafe", "Cibercafé"),
    ("italian_restaurant", "Restaurante italiano"),
    ("japanese_restaurant", "Restaurante japonés"),
    ("karaoke", "Karaoke"),
    ("korean_restaurant", "Restaurante coreano"),
    ("laundry", "Lavandería"),
    ("lebanese_restaurant", "Restaurante libanés"),
    ("market", "Mercado"),
    ("meal_delivery", "Entrega de comidas"),
    ("meal_takeaway", "Comida para llevar"),
    ("mediterranean_restaurant", "Restaurante mediterráneo"),
    ("mexican_restaurant", "Restaurante mexicano"),
    ("middle_eastern_restaurant", "Restaurante de Oriente Medio"),
    ("night_club", "Club nocturno"),
    ("observation_deck", "Mirador"),
    ("parking", "Estacionamiento"),
    ("pizza_restaurant", "Pizzería"),
    ("playground", "Parque infantil"),
    ("pub", "Pub"),
    ("ramen_restaurant", "Restaurante de ramen"),
    ("ranch", "Rancho"),
    ("real_estate_agency", "Agencia inmobiliaria"),
    ("restaurant", "Restaurante"),
    ("sandwich_shop", "Sandwichería"),
    ("school", "Escuela"),
    ("seafood_restaurant", "Marisquería"),
    ("spa", "Spa"),
    ("spanish_restaurant", "Restaurante español"),
    ("sports_club", "Club deportivo"),
    ("sports_complex", "Complejo deportivo"),
    ("steak_house", "Parrilla de carnes"),
    ("sushi_restaurant", "Restaurante de sushi"),
    ("thai_restaurant", "Restaurante tailandés"),
    ("turkish_restaurant", "Restaurante turco"),
    ("vegan_restaurant", "Restaurante vegano"),
    ("vegetarian_restaurant", "Restaurante vegetariano"),
    ("vietnamese_restaurant", "Restaurante vietnamita"),
    ("wellness_center", "Centro de bienestar"),
    ("wine_bar", "Bar de vinos"),
    # Qué hacer (ver QUE_HACER)
    ("amusement_park", "Parque de diversiones"),
    ("art_gallery", "Galería de arte"),
    ("botanical_garden", "Jardín botánico"),
    ("church", "Iglesia"),
    ("hiking_area", "Sendero"),
    ("museum", "Museo"),
    ("park", "Parque"),
    ("performing_arts_theater", "Teatro"),
    ("stadium", "Estadio"),
    ("tourist_attraction", "Atracción turística"),
    ("otros", "Otros"),
)
# ────────────────────────────────────────────────────────────────
# QuerySets & Managers
# ────────────────────────────────────────────────────────────────

# Sección "Qué hacer": categoría (slug de la URL) → tipos de Places. El orden es el de la página.
QUE_HACER = {
    "lugares-emblematicos": ("tourist_attraction", "historical_landmark", "stadium", "church"),
    "museos-y-cultura": ("museum", "art_gallery", "cultural_center", "performing_arts_theater"),
    "parques-y-naturaleza": ("park", "hiking_area", "botanical_garden", "amusement_park"),
    "miradores": ("observation_deck",),
}
TIPOS_QUE_HACER = tuple(t for tipos in QUE_HACER.values() for t in tipos)

# Paradas de guía que no son un restaurante. No entran al buscador (Qué hacer tiene el suyo).
TIPOS_FUERA_DEL_BUSCADOR = TIPOS_QUE_HACER + (
    "shopping_mall",
    "park",
    "city_park",
    "national_park",
    "dog_park",
    "plaza",
    "botanical_garden",
    "community_center",
    "hiking_area",
    "amusement_park",
)


def _fuera_del_buscador():
    """Malls, UVAs y fichas que solo viven en una guía."""
    from explorer.utils.place_classify import _CAFE, _FOOD, _NIGHT

    # El nombre delata al mall ("Centro Comercial Oviedo"), pero también lo llevan los
    # restaurantes de dentro ("Crepes & Waffles Centro Comercial Oviedo"): esos sí entran.
    nombre_de_mall = (
        Q(nombre__icontains="Centro Comercial") | Q(nombre__icontains="Parque Comercial")
    ) & ~Q(tipo__in=_FOOD | _CAFE | _NIGHT)
    return (
        Q(solo_en_guia=True)
        | Q(tipo__in=TIPOS_FUERA_DEL_BUSCADOR)
        | Q(nombre__istartswith="UVA ")
        | Q(nombre__istartswith="UVA de")
        | nombre_de_mall
    )


class PlacesQuerySet(models.QuerySet):
    """QuerySet con extensiones comunes para Places."""

    def with_fotos(self):
        return self.prefetch_related("fotos")

    def para_buscador(self):
        """El buscador principal: sin malls, UVAs ni fichas que solo viven en una guía."""
        return self.exclude(_fuera_del_buscador())

    def indexables(self):
        """Fichas que mandamos a Google (sitemap).

        Con fotos y algo que Maps no tiene: carta (solo comida, café o noche y sin
        rating malo), rating ≥ 4 con ≥ 50 reseñas, o un lugar en una guía publicada
        (malls y UVAs entran solo por la guía). Los de Qué hacer, con rating ≥ 4 y
        ≥ 50 reseñas. Nunca los cerrados para siempre.
        """
        from explorer.utils.place_classify import _CAFE, _FOOD, _NIGHT

        con_carta = Q(carta__isnull=False, tipo__in=_FOOD | _CAFE | _NIGHT) & (
            Q(rating__isnull=True) | Q(rating__gte=3.5)
        )
        calidad = con_carta | Q(rating__gte=4.0, total_reviews__gte=50)
        en_guia = Q(en_guias__guia__publicado=True)
        que_hacer = Q(tipo__in=TIPOS_QUE_HACER, rating__gte=4.0, total_reviews__gte=50)
        # Maps no rellena business_status en el scrape: el cierre viene en la categoría.
        cerrado = GooglePlaceDetails.objects.filter(place_id=models.OuterRef("place_id")).filter(
            Q(category__istartswith="Cerrado") | Q(business_status="CLOSED_PERMANENTLY")
        )
        return self.filter(
            tiene_fotos=True, slug__isnull=False
        ).exclude(slug="").exclude(
            slug__regex=r'^-?\d+$'  # slugs basura: -1, 1, 338, etc.
        ).exclude(tipo="otros").exclude(
            models.Exists(cerrado)
        ).filter(
            (~_fuera_del_buscador() & calidad) | en_guia | que_hacer
        ).distinct()


class PlacesManager(models.Manager):
    """Fichas vivas: sin duplicados fusionados ni cerrados para siempre.

    Para verlas todas (admin, importadores que deciden si crear): Places._base_manager.
    """

    def get_queryset(self):
        return (
            PlacesQuerySet(self.model, using=self._db)
            .filter(fusionado_en__isnull=True, cerrado_permanente=False)
            .with_fotos()
        )

    def indexables(self):
        return self.get_queryset().indexables()


# ────────────────────────────────────────────────────────────────
# Modelos principales
# ────────────────────────────────────────────────────────────────

# Tipos de Google Places → schema.org. Los *_restaurant que no estén aquí son Restaurant.
SCHEMA_ORG_TYPES = {
    "fast_food_restaurant": "FastFoodRestaurant",
    "bar": "BarOrPub",
    "pub": "BarOrPub",
    "sports_bar": "BarOrPub",
    "bar_and_grill": "BarOrPub",
    "wine_bar": "BarOrPub",
    "cocktail_bar": "BarOrPub",
    "night_club": "NightClub",
    "cafe": "CafeOrCoffeeShop",
    "coffee_shop": "CafeOrCoffeeShop",
    "cafeteria": "CafeOrCoffeeShop",
    "cat_cafe": "CafeOrCoffeeShop",
    "dog_cafe": "CafeOrCoffeeShop",
    "bakery": "Bakery",
    "ice_cream_shop": "IceCreamShop",
    "meal_takeaway": "FoodEstablishment",
    "meal_delivery": "FoodEstablishment",
    "food_court": "FoodEstablishment",
    "sandwich_shop": "FoodEstablishment",
    "dessert_shop": "FoodEstablishment",
    "acai_shop": "FoodEstablishment",
    "museum": "Museum",
    "art_gallery": "ArtGallery",
    "tourist_attraction": "TouristAttraction",
    "observation_deck": "TouristAttraction",
    "historical_landmark": "LandmarksOrHistoricalBuildings",
    "event_venue": "EventVenue",
    "karaoke": "EntertainmentBusiness",
    "amusement_center": "EntertainmentBusiness",
    "amusement_park": "AmusementPark",
    "park": "Park",
    "hiking_area": "Park",
    "botanical_garden": "Park",
    "church": "Church",
    "stadium": "StadiumOrArena",
    "performing_arts_theater": "PerformingArtsTheater",
}


class Tag(TagBase):
    """Modelo personalizado para las etiquetas."""
    class Meta:
        verbose_name = "Etiqueta"
        verbose_name_plural = "Etiquetas"

class TaggedPlace(TaggedItemBase):
    """Modelo intermedio para manejar las etiquetas de Places."""
    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_items",
    )
    content_object = models.ForeignKey('Places', on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Etiqueta de lugar"
        verbose_name_plural = "Etiquetas de lugares"

class Places(models.Model):
    """Lugar extraído de Google Places API con metadata enriquecida."""

    GOOGLE_MATCH_STATUS_CHOICES = (
        ("pending", "Pendiente"),
        ("matched", "Encontrado"),
        ("ambiguous", "Ambiguo"),
        ("not_found", "No encontrado"),
        ("review", "Revisar"),
    )

    id = models.AutoField(primary_key=True)
    place_id = models.CharField(max_length=255, unique=True, db_index=True)
    google_match_status = models.CharField(
        max_length=20,
        choices=GOOGLE_MATCH_STATUS_CHOICES,
        default="pending",
        db_index=True,
        help_text="Estado de verificación del place_id contra Google Text Search (IDs Only)",
    )
    google_match_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Confianza de la coincidencia (0–1)",
    )
    google_match_checked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Última verificación gratuita vía Text Search IDs Only",
    )
    nombre = models.CharField(max_length=255, db_index=True)
    tipo = models.CharField(
        max_length=255, choices=PLACE_TYPE_CHOICES, default="otros", db_index=True
    )
    direccion = models.TextField(null=True, blank=True)  # Mantenemos nullable para compatibilidad

    # SRID 4326 + geography=True nos permite usar distancia en metros
    ubicacion = gis_models.PointField(srid=4326, geography=True, null=True, blank=True)

    rating = models.FloatField(null=True, blank=True)
    total_reviews = models.IntegerField(null=True, blank=True)
    weighted_rating = models.FloatField(
        null=True, 
        blank=True, 
        db_index=True,
        help_text="Rating ponderado usando Bayesian Average (considera cantidad de reviews)"
    )

    # Campos de organización y filtrado
    tiene_fotos = models.BooleanField(default=False, help_text="Indica si el lugar tiene fotos asociadas")
    solo_en_guia = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Parada de guía (mall, UVA, parque). No sale en el buscador. Un restaurante dentro de una guía sigue buscable.",
    )
    es_destacado = models.BooleanField(default=False, help_text="Lugares con mejor rating y más reviews")
    es_exclusivo = models.BooleanField(default=False, help_text="Lugares especiales o VIP")
    show_in_home = models.BooleanField(default=False, db_index=True, help_text="Mostrar en página de inicio para máximo rendimiento")
    imagenes_optimizadas = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Indica si ya se generaron variantes optimizadas de imágenes para este lugar",
    )

    # Sistema de etiquetas
    tags = TaggableManager(
        through=TaggedPlace,
        blank=True,
        help_text="Lista de etiquetas separadas por comas",
        verbose_name="Etiquetas"
    )

    comuna_osm_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    centro_comercial = models.ForeignKey(
        'CentroComercial', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lugares', help_text="Lo asigna importar_centros_comerciales por el polígono de OSM",
    )
    fusionado_en = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='fusionados',
        help_text="Duplicado de otra ficha: su URL redirige (301) a esa. Lo pone limpiar_fichas",
    )
    cerrado_permanente = models.BooleanField(
        default=False, db_index=True,
        help_text="Cerrado para siempre según Maps: sale del sitio y su URL da 410. Lo pone limpiar_fichas",
    )

    # Horarios y estado operativo
    abierto_ahora = models.BooleanField(null=True, blank=True)
    horario_texto = models.TextField(null=True, blank=True)
    horario_json = models.JSONField(null=True, blank=True, help_text="Horario completo del lugar")

    # Contacto y enlaces
    sitio_web = models.URLField(max_length=1000, null=True, blank=True)
    telefono = models.CharField(max_length=50, null=True, blank=True)
    google_maps_uri = models.URLField(max_length=1000, null=True, blank=True)
    directions_uri = models.URLField(max_length=1000, null=True, blank=True)

    # Información adicional
    precio = models.CharField(max_length=50, null=True, blank=True)
    descripcion = models.TextField(null=True, blank=True)
    reviews = models.JSONField(null=True, blank=True)

    types = ArrayField(models.CharField(max_length=100), blank=True, null=True)
    areas_google_api = ArrayField(models.CharField(max_length=255), blank=True, null=True)

    # Servicios y amenidades (sin cambios)
    takeout = models.BooleanField(null=True, blank=True)
    dine_in = models.BooleanField(null=True, blank=True)
    delivery = models.BooleanField(null=True, blank=True)

    accepts_credit_cards = models.BooleanField(null=True, blank=True)
    accepts_debit_cards = models.BooleanField(null=True, blank=True)
    accepts_cash_only = models.BooleanField(null=True, blank=True)
    accepts_nfc = models.BooleanField(null=True, blank=True)

    wheelchair_accessible_entrance = models.BooleanField(null=True, blank=True)
    wheelchair_accessible_parking = models.BooleanField(null=True, blank=True)
    wheelchair_accessible_restroom = models.BooleanField(null=True, blank=True)
    wheelchair_accessible_seating = models.BooleanField(null=True, blank=True)

    serves_breakfast = models.BooleanField(null=True, blank=True)
    serves_lunch = models.BooleanField(null=True, blank=True)
    serves_dinner = models.BooleanField(null=True, blank=True)
    serves_beer = models.BooleanField(null=True, blank=True)
    serves_wine = models.BooleanField(null=True, blank=True)
    serves_brunch = models.BooleanField(null=True, blank=True)
    serves_cocktails = models.BooleanField(null=True, blank=True)
    serves_dessert = models.BooleanField(null=True, blank=True)
    serves_coffee = models.BooleanField(null=True, blank=True)
    good_for_groups = models.BooleanField(null=True, blank=True)
    good_for_children = models.BooleanField(null=True, blank=True)
    outdoor_seating = models.BooleanField(null=True, blank=True)
    menu_for_children = models.BooleanField(null=True, blank=True)
    live_music = models.BooleanField(null=True, blank=True)
    allows_dogs = models.BooleanField(null=True, blank=True)

    google_api_json = models.FileField(upload_to="api_json/", null=True, blank=True)

    # Campos semánticos
    summary = models.TextField(null=True, blank=True)
    embedding = VectorField(dimensions=768, null=True, blank=True)

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    contenido_actualizado = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Último cambio visible en la ficha (lastmod del sitemap). Rating y reseñas no lo mueven.",
    )

    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True, db_index=True)

    objects = PlacesManager()

    # Rating, número de reseñas y textos de reseñas cambian casi a diario y no cuentan como contenido.
    CAMPOS_CONTENIDO = (
        "nombre", "tipo", "direccion", "descripcion", "horario_texto", "horario_json",
        "sitio_web", "telefono", "precio", "tiene_fotos",
    )

    class Meta:
        ordering = ["-weighted_rating", "-rating", "nombre"]
        indexes = [
            Index(fields=["nombre"], name="nombre_idx"),
            Index(fields=["tipo"], name="tipo_idx"),
            GistIndex(fields=["ubicacion"], name="ubicacion_gist_idx")
        ]

    # ───────────────────────────────────────────────
    # Métodos utilitarios
    # ───────────────────────────────────────────────

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._contenido_cargado = instance._firma_contenido()
        return instance

    def _firma_contenido(self):
        # Solo campos ya cargados: leer uno diferido aquí dispararía una consulta por fila.
        return {f: self.__dict__[f] for f in self.CAMPOS_CONTENIDO if f in self.__dict__}

    def _contenido_cambio(self, campos):
        cargado = getattr(self, "_contenido_cargado", None)
        if cargado is None:
            return True
        actual = self._firma_contenido()
        return any(f in actual and actual[f] != cargado.get(f, actual[f]) for f in campos)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        campos = self.CAMPOS_CONTENIDO if update_fields is None else [
            f for f in self.CAMPOS_CONTENIDO if f in update_fields
        ]
        if self._contenido_cambio(campos):
            self.contenido_actualizado = timezone.now()
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "contenido_actualizado"}

        # Generar slug único si no existe
        if not self.slug:
            base = slugify(self.nombre) or uuid4().hex[:8]
            slug_candidate = base
            counter = 1
            qs = Places.objects.exclude(pk=self.pk) if self.pk else Places.objects.all()
            while qs.filter(slug=slug_candidate).exists():
                slug_candidate = f"{base}-{counter}"
                counter += 1
            self.slug = slug_candidate

        super().save(*args, **kwargs)
        self._contenido_cargado = self._firma_contenido()

        # Invalidar caché relacionado (solo si el backend lo soporta)
        try:
            cache.delete_pattern("lugares_*")
        except AttributeError:
            # LocMemCache no soporta delete_pattern
            pass

    # Representación
    def __str__(self):
        return self.nombre

    # URL canónico
    def get_absolute_url(self):
        return reverse("explorer:lugares_detail", kwargs={"slug": self.slug})

    @property
    def schema_org_type(self):
        """Tipo de schema.org para el JSON-LD de la ficha."""
        tipo = self.tipo or ""
        if tipo in SCHEMA_ORG_TYPES:
            return SCHEMA_ORG_TYPES[tipo]
        if tipo == "restaurant" or tipo.endswith("_restaurant") or tipo == "steak_house":
            return "Restaurant"
        return "LocalBusiness"

    # Propiedades dinámicas
    @property
    def comuna(self):
        if not self.comuna_osm_id:
            return None
        cache_key = f"comuna_{self.comuna_osm_id}"
        comuna_obj = cache.get(cache_key)
        if not comuna_obj:
            RegionOSM = apps.get_model("explorer", "RegionOSM")
            try:
                comuna_obj = RegionOSM.objects.get(osm_id=self.comuna_osm_id)
                cache.set(cache_key, comuna_obj, 3600)
            except RegionOSM.DoesNotExist:
                return None
        return comuna_obj

    def get_fotos(self):
        if hasattr(self, 'cached_fotos'):
            return self.cached_fotos
        return self.fotos.all()

    def get_primera_foto(self):
        if hasattr(self, 'cached_fotos') and self.cached_fotos:
            return self.cached_fotos[0]
        return self.fotos.first()

    @property
    def is_sensitive_for_ads(self):
        """
        Detecta contenido sensible (adult/sexual) para desactivar AdSense en la página.
        Evita restricciones de demanda por preferencia de anunciantes.
        """
        default_keywords = [
            "swinger",
            "strip club",
            "stripclub",
            "sex",
            "sexual",
            "adult",
            "erot",
            "xxx",
            "brothel",
            "prostibulo",
            "prostitucion",
            "cabaret",
            "table dance",
        ]
        configured_keywords = getattr(settings, "ADSENSE_SENSITIVE_KEYWORDS", default_keywords) or default_keywords
        configured_slugs = set(getattr(settings, "ADSENSE_SENSITIVE_SLUGS", []) or [])

        slug = (self.slug or "").strip().lower()
        if slug and slug in {s.lower() for s in configured_slugs}:
            return True

        # Detección más estricta para evitar falsos positivos:
        # solo evalúa nombre/slug con coincidencia por palabra o frase.
        haystack = f"{self.nombre or ''} {self.slug or ''}".lower()
        for keyword in configured_keywords:
            kw = (keyword or "").strip().lower()
            if not kw:
                continue
            pattern = r"(?<!\w)" + re.escape(kw).replace(r"\ ", r"[\s\-_]+") + r"(?!\w)"
            if re.search(pattern, haystack):
                return True
        return False


# ────────────────────────────────────────────────────────────────
# Fotos
# ────────────────────────────────────────────────────────────────

class Foto(models.Model):
    lugar = models.ForeignKey(
        Places, on_delete=models.CASCADE, related_name="fotos", db_index=True
    )
    imagen = models.URLField(max_length=1000)
    # Variantes optimizadas (URLs generadas en batch, no obligatorias)
    imagen_mediana = models.URLField(max_length=1000, null=True, blank=True)
    imagen_miniatura = models.URLField(max_length=1000, null=True, blank=True)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.imagen


# ────────────────────────────────────────────────────────────────
# Zonas y regiones
# ────────────────────────────────────────────────────────────────

class ZonaCubierta(models.Model):
    nombre = models.CharField(max_length=100)
    poligono = gis_models.PolygonField(srid=4326, geography=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class RegionOSM(models.Model):
    osm_id = models.BigIntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True, db_index=True, help_text="URL amigable generada automáticamente")
    admin_level = models.CharField(max_length=10, blank=True, null=True)
    way_area = models.FloatField(blank=True, null=True)

    # Mantener los campos existentes
    geom_4326 = gis_models.PolygonField(srid=4326, null=True, blank=True, help_text="Geometría en WGS84 (lat/lng)")
    geom_3857 = gis_models.PolygonField(srid=3857, null=True, blank=True, help_text="Geometría en Web Mercator")

    fecha_importacion = models.DateTimeField(auto_now_add=True)
    ciudad = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    class Meta:
        verbose_name = "Región OSM"
        verbose_name_plural = "Regiones OSM"
        ordering = ["name"]
        indexes = [
            GistIndex(fields=["geom_4326"], name="region_geom_4326_gist"),
            GistIndex(fields=["geom_3857"], name="region_geom_3857_gist")
        ]

    def __str__(self):
        return f"{self.name} (OSM: {self.osm_id})"

    def generate_unique_slug(self):
        """Genera un slug único para esta región."""
        if not self.name:
            return None
            
        base_slug = slugify(self.name)
        unique_slug = base_slug
        counter = 1
        
        # Verificar que el slug sea único
        while RegionOSM.objects.filter(slug=unique_slug).exclude(pk=self.pk).exists():
            unique_slug = f"{base_slug}-{counter}"
            counter += 1
            
        return unique_slug
    
    def save(self, *args, **kwargs):
        """Generar slug automáticamente al guardar."""
        if not self.slug and self.name:
            self.slug = self.generate_unique_slug()
        super().save(*args, **kwargs)

    @property
    def geom(self):
        """Propiedad para mantener compatibilidad - devuelve geom_4326 por defecto"""
        return self.geom_4326
    
    def get_geom_by_srid(self, srid):
        """Obtiene la geometría en el SRID especificado"""
        if srid == 4326:
            return self.geom_4326
        elif srid == 3857:
            return self.geom_3857
        else:
            raise ValueError(f"SRID {srid} no disponible. Use 4326 o 3857.")


# ────────────────────────────────────────────────────────────────
# Grid inicial para cobertura
# ────────────────────────────────────────────────────────────────

class Initialgrid(models.Model):
    points = gis_models.PointField(srid=4326, geography=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    is_processed = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Escaneado con Nearby Search (scan_nuevos_lugares, de pago)",
    )
    is_text_scan_processed = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Escaneado con Text Search IDs Only (scan_place_ids_gratis, gratis)",
    )
    google_ids_places = ArrayField(
        models.CharField(max_length=255),
        blank=True,
        default=list,
        help_text="Google Place IDs descubiertos en este punto de grilla (scan gratis)",
    )
    text_scan_passes = ArrayField(
        models.CharField(max_length=30),
        blank=True,
        default=list,
        help_text="Pasadas gratis completadas: bias, restriction, generico",
    )

    def __str__(self):
        flags = []
        if self.is_text_scan_processed:
            flags.append("text")
        if self.is_processed:
            flags.append("nearby")
        status = ",".join(flags) if flags else "pendiente"
        return f"Initialgrid {self.pk} — {status}"


# ────────────────────────────────────────────────────────────────
# Catálogo independiente de Google Place IDs (barrido de grilla)
# ────────────────────────────────────────────────────────────────

class GooglePlaceIdQuerySet(models.QuerySet):
    def con_ficha(self):
        """IDs que ya tienen fila en Places (ficha publicada/importada)."""
        from django.db.models import Exists, OuterRef

        return self.filter(
            Exists(Places.objects.filter(place_id=OuterRef("place_id")))
        )

    def sin_ficha(self):
        """IDs descubiertos que aún no tienen ficha en Places."""
        from django.db.models import Exists, OuterRef

        return self.filter(
            ~Exists(Places.objects.filter(place_id=OuterRef("place_id")))
        )

    def con_details(self):
        """IDs con snapshot scrapeado en GooglePlaceDetails (status ok)."""
        from django.db.models import Exists, OuterRef

        return self.filter(
            Exists(
                GooglePlaceDetails.objects.filter(
                    place_id=OuterRef("place_id"), fetch_status="ok"
                )
            )
        )

    def sin_details(self):
        """IDs sin snapshot ok en GooglePlaceDetails (cola del scraper Maps)."""
        from django.db.models import Exists, OuterRef

        return self.filter(
            ~Exists(
                GooglePlaceDetails.objects.filter(
                    place_id=OuterRef("place_id"), fetch_status="ok"
                )
            )
        )


class GooglePlaceId(models.Model):
    """
    Registro maestro de Google Place IDs descubiertos por barrido.

    Independiente de Places y PendingPlace: sirve para mapear Medellín,
    Envigado, Rionegro, Guatapé, etc. antes de scrape o importación.
    """

    SOURCE_CHOICES = (
        ("text_search_ids", "Text Search IDs Only"),
        ("text_search_restriction", "Text Search restriction (IDs Only)"),
        ("text_search_generico", "Text Search genérico (IDs Only)"),
        ("text_search_relevance", "Text Search RELEVANCE (IDs Only)"),
        ("text_search_distance", "Text Search DISTANCE (IDs Only)"),
        ("nearby_search_popularity", "Nearby Search POPULARITY (Pro)"),
        ("nearby_search_distance", "Nearby Search DISTANCE (Pro)"),
        ("places_import", "Importado desde Places"),
        ("pending_import", "Importado desde PendingPlace"),
        ("nearby_search", "Nearby Search"),
        ("manual", "Manual"),
    )

    place_id = models.CharField(max_length=255, unique=True, db_index=True)
    source = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES,
        default="text_search_ids",
        db_index=True,
    )
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    discovery_count = models.PositiveIntegerField(default=1)
    scan_types = ArrayField(
        models.CharField(max_length=100),
        blank=True,
        default=list,
        help_text="Tipos Google con los que se descubrió (includedType)",
    )
    area_names = ArrayField(
        models.CharField(max_length=100),
        blank=True,
        default=list,
        help_text="Zonas SCAN_AREAS donde cayó el punto de grilla",
    )
    first_grid_point = models.ForeignKey(
        Initialgrid,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="google_place_ids",
    )
    scan_lat = models.FloatField(null=True, blank=True)
    scan_lng = models.FloatField(null=True, blank=True)
    first_query = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Consulta (textQuery) con la que se detectó por primera vez",
    )
    search_queries = ArrayField(
        models.CharField(max_length=200),
        blank=True,
        default=list,
        help_text="Consultas distintas que devolvieron este place_id",
    )

    objects = GooglePlaceIdQuerySet.as_manager()

    class Meta:
        verbose_name = "Google Place ID (catálogo)"
        verbose_name_plural = "Google Place IDs (catálogo)"
        ordering = ["-first_seen_at"]
        indexes = [
            models.Index(fields=["source", "first_seen_at"]),
        ]

    def __str__(self):
        return self.place_id

    @property
    def tiene_ficha(self) -> bool:
        return Places.objects.filter(place_id=self.place_id).exists()


class GooglePlaceDetails(models.Model):
    """
    Snapshot de ficha desde Google Maps (Playwright), sin Places API de pago.

    Staging: no publica a Places. Guarda tipado + raw_json + photo_urls
    (sin descargar bytes; Plan 2 = media).
    """

    FETCH_STATUS_CHOICES = (
        ("ok", "OK"),
        ("error", "Error"),
        ("not_found", "No encontrado"),
        ("blocked", "Bloqueado /sorry"),
    )

    catalog_entry = models.OneToOneField(
        GooglePlaceId,
        on_delete=models.CASCADE,
        related_name="details",
        null=True,
        blank=True,
    )
    place_id = models.CharField(max_length=255, unique=True, db_index=True)
    cid = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="CID hex Maps (0x…:0x…) si aparece en la URL",
    )

    display_name = models.CharField(max_length=500, blank=True, default="")
    category = models.CharField(
        max_length=200,
        blank=True,
        default="",
        db_index=True,
        help_text="Etiqueta cruda del panel Maps",
    )
    primary_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Código Google canónico (snake_case)",
    )
    tipo = models.CharField(
        max_length=255,
        choices=PLACE_TYPE_CHOICES,
        default="otros",
        db_index=True,
        help_text="Tipo Vive (mismo vocabulario que Places.tipo)",
    )
    tipo_family = models.CharField(
        max_length=40,
        blank=True,
        default="other",
        db_index=True,
        help_text="Bucket de control: food, nightlife, lodging, …",
    )
    tipo_source = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text="maps_category | scan_types | search_query | …",
    )
    tipo_confidence = models.FloatField(null=True, blank=True)
    types = ArrayField(models.CharField(max_length=100), blank=True, default=list)
    business_status = models.CharField(max_length=40, blank=True, default="", db_index=True)

    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    ubicacion = gis_models.PointField(srid=4326, geography=True, null=True, blank=True)
    formatted_address = models.TextField(blank=True, default="")
    plus_code = models.CharField(max_length=120, blank=True, default="")

    rating = models.FloatField(null=True, blank=True, db_index=True)
    user_rating_count = models.PositiveIntegerField(null=True, blank=True)

    phone = models.CharField(max_length=80, blank=True, default="")
    website_uri = models.URLField(max_length=1000, blank=True, default="")
    google_maps_uri = models.URLField(max_length=1000, blank=True, default="")
    menu_uri = models.URLField(max_length=1000, blank=True, default="")

    price_level = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="Nivel de precio Maps ($, $$, …)",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Descripción / texto del negocio si aparece en Acerca de",
    )

    open_now = models.BooleanField(null=True, blank=True)
    hours_text = models.TextField(blank=True, default="")
    weekday_descriptions = models.TextField(blank=True, default="")

    dine_in = models.BooleanField(null=True, blank=True)
    takeout = models.BooleanField(null=True, blank=True)
    delivery = models.BooleanField(null=True, blank=True)
    amenities = models.JSONField(
        null=True,
        blank=True,
        help_text="Atributos visibles en Maps (dict flexible)",
    )

    reviews = models.JSONField(null=True, blank=True)
    photo_urls = models.JSONField(
        null=True,
        blank=True,
        help_text="URLs CDN de fotos (sin bytes). Plan 2 = descargar.",
    )
    photos_meta = models.JSONField(null=True, blank=True)

    fetched_at = models.DateTimeField(null=True, blank=True, db_index=True)
    fetch_status = models.CharField(
        max_length=20, choices=FETCH_STATUS_CHOICES, default="ok", db_index=True
    )
    error_message = models.TextField(blank=True, default="")
    scraper_version = models.CharField(max_length=40, blank=True, default="maps_v1")
    raw_json = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Google Place Details (staging)"
        verbose_name_plural = "Google Place Details (staging)"
        ordering = ["-fetched_at"]
        indexes = [
            models.Index(fields=["category", "rating"]),
            models.Index(fields=["fetch_status", "fetched_at"]),
            models.Index(fields=["tipo_family", "tipo"]),
            models.Index(fields=["primary_type", "tipo_family"]),
        ]

    def __str__(self):
        return self.display_name or self.place_id


# ────────────────────────────────────────────────────────────────
# Barrido de descubrimiento (comuna × categoría × malla)
# ────────────────────────────────────────────────────────────────

class PlaceDiscoveryRun(models.Model):
    """Una ejecución de discover_medellin_places. Permite auditar y reanudar."""

    STATUS_CHOICES = (
        ("running", "En curso"),
        ("done", "Terminada"),
        ("interrupted", "Interrumpida"),
        ("error", "Con error fatal"),
    )

    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="running", db_index=True
    )
    params = models.JSONField(default=dict, blank=True)

    tasks_done = models.PositiveIntegerField(default=0)
    tasks_error = models.PositiveIntegerField(default=0)
    api_calls = models.PositiveIntegerField(default=0)
    pages = models.PositiveIntegerField(default=0)
    ids_seen = models.PositiveIntegerField(default=0, help_text="place_id únicos devueltos")
    ids_new = models.PositiveIntegerField(default=0, help_text="Nuevos en GooglePlaceId")
    errors = models.PositiveIntegerField(default=0)
    rate_limited = models.PositiveIntegerField(default=0, help_text="Respuestas HTTP 429")

    class Meta:
        verbose_name = "Barrido de descubrimiento"
        verbose_name_plural = "Barridos de descubrimiento"
        ordering = ["-started_at"]

    def __str__(self):
        return f"Run {self.pk} ({self.status})"

    @property
    def duration_s(self) -> float:
        end = self.finished_at or timezone.now()
        return (end - self.started_at).total_seconds()


class PlaceDiscoveryTask(models.Model):
    """
    Unidad de trabajo idempotente del barrido: una consulta sobre un rectángulo.

    `signature` la hace única, de modo que replanificar no duplica trabajo y un
    proceso interrumpido se reanuda tomando las tareas que siguen pendientes.
    """

    KIND_CHOICES = (
        ("text", "Text Search (IDs Only, gratis)"),
        ("nearby", "Nearby Search (Pro, de pago)"),
    )
    STATUS_CHOICES = (
        ("pending", "Pendiente"),
        ("running", "En curso"),
        ("done", "Terminada"),
        ("error", "Error"),
    )

    signature = models.CharField(max_length=64, unique=True, db_index=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, db_index=True)

    area_name = models.CharField(max_length=120)
    area_slug = models.SlugField(max_length=140, db_index=True)
    area_kind = models.CharField(max_length=20, blank=True, default="")

    category = models.CharField(max_length=80, blank=True, default="")
    included_type = models.CharField(max_length=80, blank=True, default="")
    query = models.CharField(max_length=200, blank=True, default="")
    rank_preference = models.CharField(max_length=20, blank=True, default="")

    lat_min = models.FloatField()
    lat_max = models.FloatField()
    lng_min = models.FloatField()
    lng_max = models.FloatField()
    radius_m = models.FloatField(default=0.0)

    depth = models.PositiveSmallIntegerField(default=0, db_index=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    ids_found = models.PositiveIntegerField(default=0)
    ids_new = models.PositiveIntegerField(default=0)
    api_calls = models.PositiveIntegerField(default=0)
    pages = models.PositiveIntegerField(default=0)
    saturated = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Google devolvió el máximo: la zona se subdividió",
    )
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Tarea de descubrimiento"
        verbose_name_plural = "Tareas de descubrimiento"
        ordering = ["depth", "area_slug", "category", "id"]
        indexes = [
            models.Index(fields=["status", "kind", "depth"]),
            models.Index(fields=["area_slug", "category"]),
        ]

    def __str__(self):
        return f"{self.kind}:{self.area_slug}/{self.category or 'generico'} d{self.depth}"

    @property
    def center(self) -> tuple[float, float]:
        return ((self.lat_min + self.lat_max) / 2, (self.lng_min + self.lng_max) / 2)


# ────────────────────────────────────────────────────────────────
# Newsletter subscription model
# ────────────────────────────────────────────────────────────────

class NewsletterSubscription(models.Model):
    """Modelo para gestionar suscripciones al newsletter"""
    
    email = models.EmailField(
        unique=True, 
        validators=[EmailValidator()],
        help_text="Dirección de correo electrónico del suscriptor"
    )
    nombre = models.CharField(
        max_length=100, 
        blank=True, 
        help_text="Nombre del suscriptor (opcional)"
    )
    fecha_suscripcion = models.DateTimeField(
        auto_now_add=True,
        help_text="Fecha y hora de suscripción"
    )
    activo = models.BooleanField(
        default=True,
        help_text="Indica si la suscripción está activa"
    )
    ip_address = models.GenericIPAddressField(
        null=True, 
        blank=True,
        help_text="Dirección IP desde donde se suscribió"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent del navegador"
    )
    confirmado = models.BooleanField(
        default=False,
        help_text="Indica si el email ha sido confirmado"
    )
    fecha_confirmacion = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Fecha y hora de confirmación del email"
    )
    token_confirmacion = models.CharField(
        max_length=64,
        blank=True,
        help_text="Token para confirmar la suscripción"
    )
    fuente = models.CharField(
        max_length=50,
        default='website',
        help_text="Origen de la suscripción (website, landing, etc.)"
    )
    
    class Meta:
        verbose_name = "Suscripción Newsletter"
        verbose_name_plural = "Suscripciones Newsletter"
        ordering = ['-fecha_suscripcion']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['activo', 'confirmado']),
            models.Index(fields=['fecha_suscripcion']),
        ]
    
    def __str__(self):
        estado = "✅" if self.confirmado else "⏳" 
        activo_str = "🟢" if self.activo else "🔴"
        return f"{estado} {activo_str} {self.email}"
    
    def save(self, *args, **kwargs):
        """Generar token de confirmación si no existe"""
        if not self.token_confirmacion:
            import secrets
            self.token_confirmacion = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)
    
    def confirmar_suscripcion(self):
        """Confirma la suscripción del usuario"""
        self.confirmado = True
        self.fecha_confirmacion = timezone.now()
        self.save(update_fields=['confirmado', 'fecha_confirmacion'])
    
    def desactivar(self):
        """Desactiva la suscripción"""
        self.activo = False
        self.save(update_fields=['activo'])
    
    def reactivar(self):
        """Reactiva la suscripción"""
        self.activo = True
        self.save(update_fields=['activo'])
    
    @classmethod
    def suscriptores_activos(cls):
        """Devuelve queryset de suscriptores activos y confirmados"""
        return cls.objects.filter(activo=True, confirmado=True)
    
    @classmethod
    def total_suscriptores(cls):
        """Cuenta total de suscriptores activos"""
        return cls.suscriptores_activos().count()
    
    @classmethod
    def suscripciones_por_mes(cls):
        """Estadísticas de suscripciones por mes"""
        from django.db.models import Count
        from django.db.models.functions import TruncMonth
        
        return cls.objects.annotate(
            mes=TruncMonth('fecha_suscripcion')
        ).values('mes').annotate(
            total=Count('id')
        ).order_by('mes')


# ────────────────────────────────────────────────────────────────
# Guías Curadas ("Top 10" por el local)
# ────────────────────────────────────────────────────────────────

# Bloques del índice /guias/: un plan en toda la ciudad, una zona concreta o una salida fuera.
GUIDE_CATEGORY_CHOICES = (
    ('plan', 'Por plan'),
    ('zona', 'Por zona'),
    ('escapada', 'Escapada'),
)
GUIDE_THEME_CHOICES = (
    ('comer', 'Comer'),
    ('noche', 'Salir de noche'),
    ('dia', 'De día'),
)
# Con menos lugares la guía sale del índice, de la home y del sitemap, y lleva noindex.
# Las escapadas no: son el recorrido de un día y 4 paradas ya lo cubren.
GUIA_MIN_LUGARES = 5


class CuratedGuideQuerySet(models.QuerySet):
    def indexables(self):
        return (
            self.filter(publicado=True)
            .annotate(n_lugares=Count('items', filter=Q(items__lugar__cerrado_permanente=False, items__lugar__fusionado_en__isnull=True)))
            .filter(Q(n_lugares__gte=GUIA_MIN_LUGARES) | Q(categoria='escapada'))
        )


class CuratedGuide(models.Model):
    """Guía curada con ranking personal de lugares."""

    titulo = models.CharField(max_length=200, help_text="Título en español")
    titulo_en = models.CharField(max_length=200, blank=True, help_text="Title in English (dejar vacío = usa español)")
    slug = models.SlugField(max_length=220, unique=True, blank=True, help_text="Se genera automáticamente del título")
    descripcion = models.TextField(help_text="Descripción en español")
    descripcion_en = models.TextField(blank=True, help_text="Description in English (dejar vacío = usa español)")
    como_recorrer = models.TextField(
        blank=True,
        default="",
        help_text="Cómo hacer el recorrido, en español",
    )
    imagen_cover = models.URLField(
        max_length=500, blank=True,
        help_text="URL de imagen de portada (opcional). Si vacío, usa la foto del lugar #1"
    )
    categoria = models.CharField(
        max_length=30, choices=GUIDE_CATEGORY_CHOICES, default='plan', db_index=True
    )
    tema = models.CharField(
        max_length=20, choices=GUIDE_THEME_CHOICES, blank=True, default='',
        help_text="Qué plan cubre (opcional). Ordena y rotula las guías dentro de su zona",
    )
    zona = models.ForeignKey(
        RegionOSM, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='guias', help_text="Zona específica (opcional). Dejar vacío = Medellín en general"
    )
    publicado = models.BooleanField(default=False, db_index=True, help_text="Solo las guías publicadas aparecen en el sitio")
    orden = models.IntegerField(default=0, help_text="Orden en el índice de guías (menor = primero)")
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    objects = CuratedGuideQuerySet.as_manager()

    class Meta:
        verbose_name = "Guía Curada"
        verbose_name_plural = "Guías Curadas"
        ordering = ['orden', '-fecha_creacion']

    def __str__(self):
        estado = "✅" if self.publicado else "📝"
        return f"{estado} {self.titulo}"

    def _get_translated(self, field_es, field_en):
        """Retorna el campo traducido según el idioma activo."""
        lang = get_language() or 'es'
        if lang.startswith('en') and field_en:
            return field_en
        return field_es

    @property
    def titulo_i18n(self):
        return self._get_translated(self.titulo, self.titulo_en)

    @property
    def descripcion_i18n(self):
        return self._get_translated(self.descripcion, self.descripcion_en)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.titulo)
            # Asegurar unicidad
            base_slug = self.slug
            counter = 1
            while CuratedGuide.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('explorer:guia_detail', args=[self.slug])

    def get_cover_image(self):
        """Retorna imagen de cover, o la foto del lugar #1 como fallback."""
        if self.imagen_cover:
            return self.imagen_cover
        first_item = self.items.select_related('lugar').first()
        if first_item and first_item.lugar:
            foto = first_item.lugar.get_primera_foto()
            if foto:
                return getattr(foto, 'imagen_mediana', None) or foto.imagen
        return None

    @property
    def zona_display(self):
        """Retorna nombre de zona o 'Medellín' si es general."""
        return self.zona.name if self.zona else "Medellín"

    @property
    def total_items(self):
        n_lugares = getattr(self, 'n_lugares', None)
        return n_lugares if n_lugares is not None else self.items.count()

    @property
    def es_indexable(self):
        return self.publicado and (self.categoria == 'escapada' or self.total_items >= GUIA_MIN_LUGARES)


class CuratedGuideItem(models.Model):
    """Un lugar dentro de una guía curada, con comentario personal."""

    guia = models.ForeignKey(
        CuratedGuide, on_delete=models.CASCADE, related_name='items'
    )
    lugar = models.ForeignKey(
        Places, on_delete=models.CASCADE, related_name='en_guias',
        help_text="Busca el lugar por nombre"
    )
    posicion = models.PositiveIntegerField(
        default=1, help_text="Posición en el ranking (1 = el mejor)"
    )
    comentario = models.TextField(
        blank=True,
        help_text="Tu recomendación en español"
    )
    comentario_en = models.TextField(
        blank=True,
        help_text="Your recommendation in English (dejar vacío = usa español)"
    )
    como_llegar = models.CharField(
        max_length=300,
        blank=True,
        default="",
        help_text="Cómo llegar a esta parada",
    )
    advertencia = models.CharField(
        max_length=300,
        blank=True,
        default="",
        help_text="Aviso corto: horario, seguridad, día de visita",
    )
    destacado = models.CharField(
        max_length=50, blank=True,
        help_text="Badge en español: 'Mi favorito', 'Mejor terraza'"
    )
    destacado_en = models.CharField(
        max_length=50, blank=True,
        help_text="Badge in English: 'My favorite', 'Best terrace'"
    )

    class Meta:
        verbose_name = "Lugar en Guía"
        verbose_name_plural = "Lugares en Guía"
        ordering = ['posicion']
        unique_together = [('guia', 'lugar'), ('guia', 'posicion')]

    def __str__(self):
        return f"#{self.posicion} {self.lugar.nombre}"

    def _get_translated(self, field_es, field_en):
        lang = get_language() or 'es'
        if lang.startswith('en') and field_en:
            return field_en
        return field_es

    @property
    def comentario_i18n(self):
        return self._get_translated(self.comentario, self.comentario_en)

    @property
    def destacado_i18n(self):
        return self._get_translated(self.destacado, self.destacado_en)


# ────────────────────────────────────────────────────────────────
# Centros comerciales: contenedores de lugares, no recomendaciones
# ────────────────────────────────────────────────────────────────

# Con menos lugares con foto no se publica la página del centro comercial.
CC_MIN_LUGARES = 8
# Con menos fichas indexables la página existe pero lleva noindex y no va al sitemap.
CC_MIN_INDEXABLES = 8


class CentroComercialQuerySet(models.QuerySet):
    def publicados(self):
        return self.filter(publicado=True, total_lugares__gte=CC_MIN_LUGARES)

    def indexables(self):
        return self.publicados().filter(lugares_indexables__gte=CC_MIN_INDEXABLES)


class CentroComercial(models.Model):
    """Centro comercial con los lugares que caen dentro de su polígono de OSM.

    Lo crea y actualiza importar_centros_comerciales; los contadores y la portada también.
    """

    nombre = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    osm_ids = ArrayField(models.BigIntegerField(), help_text="Polígonos de OSM que lo forman (etapas)")
    geom = gis_models.MultiPolygonField(srid=4326)
    zona = models.ForeignKey(
        RegionOSM, on_delete=models.SET_NULL, null=True, blank=True, related_name='centros_comerciales'
    )
    nota = models.TextField(blank=True, default='', help_text="Texto propio (opcional), en español")
    nota_en = models.TextField(blank=True, default='', help_text="Texto propio (opcional), en inglés")
    portada = models.URLField(max_length=1000, blank=True, default='')
    total_lugares = models.PositiveIntegerField(default=0)
    lugares_indexables = models.PositiveIntegerField(default=0)
    publicado = models.BooleanField(default=True, help_text="Desmarcar para ocultarlo aunque tenga lugares")
    actualizado = models.DateTimeField(auto_now=True)

    objects = CentroComercialQuerySet.as_manager()

    class Meta:
        verbose_name = "Centro comercial"
        verbose_name_plural = "Centros comerciales"
        ordering = ['-lugares_indexables', '-total_lugares', 'nombre']

    def __str__(self):
        return self.nombre

    def get_absolute_url(self):
        return reverse('explorer:centro_comercial_detail', args=[self.slug])

    @property
    def nota_i18n(self):
        lang = get_language() or 'es'
        if lang.startswith('en') and self.nota_en:
            return self.nota_en
        return self.nota

    @property
    def es_publicado(self):
        return self.publicado and self.total_lugares >= CC_MIN_LUGARES

    @property
    def es_indexable(self):
        return self.es_publicado and self.lugares_indexables >= CC_MIN_INDEXABLES


# ────────────────────────────────────────────────────────────────
# Cartas de Rappi / DiDi (un lugar, la carta más completa)
# ────────────────────────────────────────────────────────────────

# Fragmento de la URL → nombre de la app de pedidos.
APPS_PEDIDO = (("rappi", "Rappi"), ("didi", "DiDi"), ("ifood", "iFood"), ("uber", "Uber Eats"))


class PlacePartnerMenu(models.Model):
    """Carta de un partner, unida a un lugar que ya está en Places."""

    PLATFORM_CHOICES = (
        ("rappi", "Rappi"),
        ("didi", "DiDi Food"),
        ("ifood", "iFood"),
        ("ubereats", "Uber Eats"),
    )

    lugar = models.OneToOneField(
        Places, on_delete=models.CASCADE, related_name="carta"
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    source_url = models.URLField(max_length=1000, blank=True, default="")
    external_id = models.CharField(max_length=80, blank=True, default="")
    store_name = models.CharField(max_length=300, blank=True, default="")
    address = models.TextField(blank=True, default="")
    partner_urls = models.JSONField(
        default=list,
        blank=True,
        help_text="Todas las URLs de pedido, incluida la que no se escogió",
    )
    item_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Carta de partner"
        verbose_name_plural = "Cartas de partner"

    def __str__(self):
        return f"{self.get_platform_display()} · {self.lugar.nombre}"

    def enlaces_pedido(self):
        """Etiqueta y URL para cada sitio donde se puede pedir."""
        seen = set()
        links = []
        for url in list(self.partner_urls or []) + [self.source_url]:
            if not url or url in seen:
                continue
            seen.add(url)
            host = url.lower()
            app = next((nombre for clave, nombre in APPS_PEDIDO if clave in host), None)
            label = gettext("Pedir en %(app)s") % {"app": app} if app else gettext("Pedir")
            links.append({"label": label, "url": url})
        return links


class PlacePartnerDish(models.Model):
    """Un plato. La foto queda como URL del partner, sin descargarla."""

    carta = models.ForeignKey(
        PlacePartnerMenu, on_delete=models.CASCADE, related_name="platos"
    )
    external_id = models.CharField(max_length=80, blank=True, default="")
    name = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    price = models.PositiveIntegerField(null=True, blank=True)
    price_text = models.CharField(max_length=40, blank=True, default="")
    original_price_text = models.CharField(max_length=40, blank=True, default="")
    image_url = models.URLField(max_length=1000, blank=True, default="")
    section = models.CharField(max_length=200, blank=True, default="")
    is_available = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Plato"
        verbose_name_plural = "Platos"
        ordering = ["position"]
        indexes = [
            models.Index(fields=["carta", "position"], name="explorer_partnerdish_pos"),
        ]

    def __str__(self):
        return self.name


# ────────────────────────────────────────────────────────────────
# Pending Places (cola de lugares nuevos por procesar)
# ────────────────────────────────────────────────────────────────

class PendingPlace(models.Model):
    """Place ID descubierto en un barrido que aún no está en Places."""

    STATUS_CHOICES = (
        ('pending', 'Pendiente'),
        ('processed', 'Procesado'),
        ('failed', 'Falló'),
        ('skipped', 'Descartado'),
    )

    place_id = models.CharField(max_length=255, unique=True, db_index=True)
    nombre = models.CharField(max_length=255, blank=True, help_text="Nombre básico de la API")
    tipos = ArrayField(models.CharField(max_length=100), blank=True, default=list, help_text="Tipos de Google")
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    error_msg = models.TextField(blank=True)
    descubierto_en = models.DateTimeField(auto_now_add=True)
    procesado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Lugar Pendiente"
        verbose_name_plural = "Lugares Pendientes"
        ordering = ['-descubierto_en']

    def __str__(self):
        icon = {'pending': '⏳', 'processed': '✅', 'failed': '❌', 'skipped': '🚫'}.get(self.status, '?')
        return f"{icon} {self.nombre or self.place_id}"


# ────────────────────────────────────────────────────────────────
# Fotos y cartas nuevas también son contenido visible de la ficha
# ────────────────────────────────────────────────────────────────

@receiver(post_save, sender=Foto)
def _foto_nueva_actualiza_ficha(sender, instance, created, **kwargs):
    # Solo la primera foto cambia lo que se ve: el enriquecimiento añade fotos a diario
    # y movía el lastmod de miles de fichas sin cambio real.
    if created and instance.lugar_id and not Foto.objects.filter(lugar_id=instance.lugar_id).exclude(pk=instance.pk).exists():
        Places._base_manager.filter(pk=instance.lugar_id).update(contenido_actualizado=timezone.now())


@receiver(post_save, sender=PlacePartnerMenu)
def _carta_nueva_actualiza_ficha(sender, instance, created, **kwargs):
    # update_or_create guarda la carta en cada importación: solo cuenta la primera vez.
    if created:
        Places._base_manager.filter(pk=instance.lugar_id).update(contenido_actualizado=timezone.now())
