from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.core.cache import cache
from django.db import models
from django.db.models import Index
from django.contrib.postgres.indexes import GistIndex
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
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
    ("otros", "Otros"),
)
# ────────────────────────────────────────────────────────────────
# QuerySets & Managers
# ────────────────────────────────────────────────────────────────

class PlacesQuerySet(models.QuerySet):
    """QuerySet con extensiones comunes para Places."""

    def with_fotos(self):
        return self.prefetch_related("fotos")


class PlacesManager(models.Manager):
    def get_queryset(self):
        return PlacesQuerySet(self.model, using=self._db).with_fotos()


# ────────────────────────────────────────────────────────────────
# Modelos principales
# ────────────────────────────────────────────────────────────────

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

    id = models.AutoField(primary_key=True)
    place_id = models.CharField(max_length=255, unique=True, db_index=True)
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

    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True, db_index=True)

    objects = PlacesManager()

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

    def save(self, *args, **kwargs):
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
    is_processed = models.BooleanField(default=False, db_index=True)

    def __str__(self):
        return f"Initialgrid {self.pk} - Processed: {self.is_processed}"


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
