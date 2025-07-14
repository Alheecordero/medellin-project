from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.conf import settings
from django.db import models
from django.contrib.gis.db import models as gis_models
from django.utils.text import slugify
from django.urls import reverse
from django.core.cache import cache





class PlacesManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().prefetch_related('fotos')

class Places(models.Model):
    place_id = models.CharField(max_length=255, unique=True, db_index=True)
    nombre = models.CharField(max_length=255, db_index=True)
    tipo = models.CharField(max_length=255)
    direccion = models.TextField(null=True, blank=True)
    ubicacion = gis_models.PointField(null=True, blank=True, srid=4326)
    rating = models.FloatField(null=True, blank=True)
    total_reviews = models.IntegerField(null=True, blank=True)
    
    # Cambiamos ForeignKey por un campo de ID para evitar problemas con la clave primaria de la tabla GIS.
    comuna_osm_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    
    # El modelo 'Zona' no existe, comentamos este campo para arreglar el error de SystemCheckError.
    # zona = models.ForeignKey('Zona', on_delete=models.SET_NULL, null=True, blank=True)
    abierto_ahora = models.BooleanField(null=True, blank=True)
    horario_texto = models.TextField(null=True, blank=True)
    sitio_web = models.URLField(max_length=500, null=True, blank=True)
    telefono = models.CharField(max_length=50, null=True, blank=True)
    precio = models.CharField(max_length=50, null=True, blank=True)
    descripcion = models.TextField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    reviews = models.JSONField(null=True, blank=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True, db_index=True)

    objects = PlacesManager() # Asignamos el manager personalizado

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

    def get_absolute_url(self):
        return reverse('explorer:lugares_detail', kwargs={'slug': self.slug})

    # Propiedad para obtener la comuna dinámicamente
    @property
    def comuna(self):
        if not self.comuna_osm_id:
            return None
        try:
            # Usamos un caché simple para evitar consultas repetidas
            cache_key = f"comuna_{self.comuna_osm_id}"
            comuna_obj = cache.get(cache_key)
            if not comuna_obj:
                comuna_obj = RegionOSM.objects.get(osm_id=self.comuna_osm_id)
                cache.set(cache_key, comuna_obj, 3600) # Cache de 1 hora
            return comuna_obj
        except RegionOSM.DoesNotExist:
            return None

    def get_fotos(self):
        return self.fotos.all()

    def get_primera_foto(self):
        return self.fotos.first()


class Foto(models.Model):
    lugar = models.ForeignKey(Places, on_delete=models.CASCADE, related_name='fotos')
    imagen = models.TextField()  # Cambiado de ImageField a TextField para aceptar URLs largas
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True, null=True) # Añadido null=True para la migración

    def __str__(self):
        return self.imagen


from django.contrib.gis.db import models as gis_models

class ZonaCubierta(models.Model):
    nombre = models.CharField(max_length=100)
    poligono = gis_models.PolygonField(srid=4326)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

class RegionOSM(models.Model):
    osm_id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    admin_level = models.CharField(max_length=10, blank=True, null=True)
    way_area = models.FloatField(blank=True, null=True)
    
    geom = gis_models.MultiPolygonField(srid=4326, db_column='way')  # 👈 importante: db_column='way'

    
    class Meta:
        managed = False  # Porque es una tabla existente
        db_table = 'planet_osm_polygon'

    
    @property
    def slug(self):
        return slugify(self.name)

    


class Favorito(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    lugar = models.ForeignKey('Places', on_delete=models.CASCADE)
    fecha_agregado = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('usuario', 'lugar')