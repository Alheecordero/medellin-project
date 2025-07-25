# Generated by Django 5.2.4 on 2025-07-14 22:00

import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RegionOSM',
            fields=[
                ('osm_id', models.BigIntegerField(primary_key=True, serialize=False)),
                ('name', models.CharField(blank=True, max_length=255, null=True)),
                ('admin_level', models.CharField(blank=True, max_length=10, null=True)),
                ('way_area', models.FloatField(blank=True, null=True)),
                ('geom', django.contrib.gis.db.models.fields.MultiPolygonField(db_column='way', srid=4326)),
            ],
            options={
                'db_table': 'planet_osm_polygon',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Places',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('place_id', models.CharField(db_index=True, max_length=255, unique=True)),
                ('nombre', models.CharField(db_index=True, max_length=255)),
                ('tipo', models.CharField(max_length=255)),
                ('direccion', models.TextField(blank=True, null=True)),
                ('ubicacion', django.contrib.gis.db.models.fields.PointField(blank=True, null=True, srid=4326)),
                ('rating', models.FloatField(blank=True, null=True)),
                ('total_reviews', models.IntegerField(blank=True, null=True)),
                ('comuna_osm_id', models.BigIntegerField(blank=True, db_index=True, null=True)),
                ('abierto_ahora', models.BooleanField(blank=True, null=True)),
                ('horario_texto', models.TextField(blank=True, null=True)),
                ('sitio_web', models.URLField(blank=True, max_length=500, null=True)),
                ('telefono', models.CharField(blank=True, max_length=50, null=True)),
                ('precio', models.CharField(blank=True, max_length=50, null=True)),
                ('descripcion', models.TextField(blank=True, null=True)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('reviews', models.JSONField(blank=True, null=True)),
                ('slug', models.SlugField(blank=True, max_length=255, null=True, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='ZonaCubierta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('poligono', django.contrib.gis.db.models.fields.PolygonField(srid=4326)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='Foto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imagen', models.ImageField(max_length=500, upload_to='lugares/')),
                ('descripcion', models.CharField(blank=True, max_length=255, null=True)),
                ('fecha_subida', models.DateTimeField(auto_now_add=True, null=True)),
                ('lugar', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fotos', to='explorer.places')),
            ],
        ),
        migrations.CreateModel(
            name='Favorito',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_agregado', models.DateTimeField(auto_now_add=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('lugar', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='explorer.places')),
            ],
            options={
                'unique_together': {('usuario', 'lugar')},
            },
        ),
    ]
