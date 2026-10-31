from django.db import migrations, models
from django.db.models import F


def copiar_fecha_actualizacion(apps, schema_editor):
    Places = apps.get_model("explorer", "Places")
    Places.objects.filter(contenido_actualizado__isnull=True).update(
        contenido_actualizado=F("fecha_actualizacion")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0038_places_solo_en_guia"),
    ]

    operations = [
        migrations.AddField(
            model_name="places",
            name="contenido_actualizado",
            field=models.DateTimeField(
                blank=True,
                help_text="Último cambio visible en la ficha (lastmod del sitemap). Rating y reseñas no lo mueven.",
                null=True,
            ),
        ),
        migrations.RunPython(copiar_fecha_actualizacion, migrations.RunPython.noop),
    ]
