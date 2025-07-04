from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.conf import settings





class Places(models.Model):
    place_id = models.CharField(max_length=255, unique=True)
    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=255)
    direccion = models.TextField(null=True, blank=True)
    telefono = models.CharField(max_length=50, null=True, blank=True)
    sitio_web = models.URLField(null=True, blank=True)
    rating = models.FloatField(null=True, blank=True)
    total_reviews = models.IntegerField(null=True, blank=True)
    precio = models.CharField(max_length=50, blank=True, null=True)
    
    ubicacion = models.PointField(geography=True)
    horario_texto = models.TextField(null=True, blank=True)
    abierto_ahora = models.BooleanField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    # Campo para guardar la referencia a la foto de Google Places
    photo_reference = models.CharField(max_length=1000, blank=True, null=True)
    imagen = models.ImageField(upload_to="portadas_lugares/", null=True, blank=True, max_length=500)
    # Campo para guardar las reseñas de Google Places
    reviews = models.JSONField(null=True, blank=True)
    slug = models.SlugField(max_length=150, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.nombre)
            slug = base_slug
            num = 1
            while Places.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{num}"
                num += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre
    
class Foto(models.Model):
    lugar = models.ForeignKey(Places, on_delete=models.CASCADE, related_name="fotos")
    imagen = models.ImageField(upload_to="imagenes_medellin/")
    descripcion = models.CharField(max_length=255, blank=True)



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