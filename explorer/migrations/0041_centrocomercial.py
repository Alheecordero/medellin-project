import django.contrib.gis.db.models.fields
import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0040_guias_por_plan_zona_escapada"),
    ]

    operations = [
        migrations.CreateModel(
            name="CentroComercial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=140, unique=True)),
                (
                    "osm_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.BigIntegerField(),
                        help_text="Polígonos de OSM que lo forman (etapas)",
                        size=None,
                    ),
                ),
                ("geom", django.contrib.gis.db.models.fields.MultiPolygonField(srid=4326)),
                ("nota", models.TextField(blank=True, default="", help_text="Texto propio (opcional), en español")),
                ("nota_en", models.TextField(blank=True, default="", help_text="Texto propio (opcional), en inglés")),
                ("portada", models.URLField(blank=True, default="", max_length=1000)),
                ("total_lugares", models.PositiveIntegerField(default=0)),
                ("lugares_indexables", models.PositiveIntegerField(default=0)),
                (
                    "publicado",
                    models.BooleanField(default=True, help_text="Desmarcar para ocultarlo aunque tenga lugares"),
                ),
                ("actualizado", models.DateTimeField(auto_now=True)),
                (
                    "zona",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="centros_comerciales",
                        to="explorer.regionosm",
                    ),
                ),
            ],
            options={
                "verbose_name": "Centro comercial",
                "verbose_name_plural": "Centros comerciales",
                "ordering": ["-lugares_indexables", "-total_lugares", "nombre"],
            },
        ),
        migrations.AddField(
            model_name="places",
            name="centro_comercial",
            field=models.ForeignKey(
                blank=True,
                help_text="Lo asigna importar_centros_comerciales por el polígono de OSM",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="lugares",
                to="explorer.centrocomercial",
            ),
        ),
    ]
