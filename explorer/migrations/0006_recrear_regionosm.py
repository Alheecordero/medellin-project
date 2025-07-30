# Generated manually
from django.db import migrations
import django.contrib.gis.db.models as gis_models
import django.db.models


class Migration(migrations.Migration):

    dependencies = [
        ('explorer', '0005_eliminar_favorito'),
    ]

    operations = [
        # Eliminar el modelo viejo
        migrations.DeleteModel(
            name='RegionOSM',
        ),
        
        # Crear el nuevo modelo manejado
        migrations.CreateModel(
            name='RegionOSM',
            fields=[
                ('id', django.db.models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('osm_id', django.db.models.BigIntegerField(db_index=True, unique=True)),
                ('name', django.db.models.CharField(blank=True, db_index=True, max_length=255, null=True)),
                ('admin_level', django.db.models.CharField(blank=True, max_length=10, null=True)),
                ('way_area', django.db.models.FloatField(blank=True, null=True)),
                ('geom', gis_models.MultiPolygonField(srid=4326)),
                ('fecha_importacion', django.db.models.DateTimeField(auto_now_add=True)),
                ('ciudad', django.db.models.CharField(blank=True, db_index=True, max_length=100, null=True)),
            ],
            options={
                'verbose_name': 'Región OSM',
                'verbose_name_plural': 'Regiones OSM',
                'ordering': ['name'],
            },
        ),
    ] 