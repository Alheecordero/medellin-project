from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0021_alter_places_embedding"),
    ]

    operations = [
        migrations.AddField(
            model_name="foto",
            name="imagen_mediana",
            field=models.URLField(max_length=1000, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="foto",
            name="imagen_miniatura",
            field=models.URLField(max_length=1000, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="places",
            name="imagenes_optimizadas",
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text="Indica si ya se generaron variantes optimizadas de imágenes para este lugar",
            ),
        ),
    ]


