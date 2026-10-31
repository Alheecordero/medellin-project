"""Categorías de guía por bloque del índice (plan, zona, escapada) y tema dentro de la zona."""

from django.db import migrations, models

# Guías de una zona que se crearon sin zona.
ZONAS_POR_SLUG = {
    "bares-en-el-poblado": "El Poblado",
    "noche-en-laureles-y-la-70": "Laureles-Estadio",
}
TEMAS = (
    ("comer", ("comer", "comida", "gastronom")),
    ("noche", ("noche", "bares", "rooftop", "lgbt")),
    ("dia", ("de-dia", "de día")),
)


def _tema(guia):
    texto = f"{guia.slug} {guia.titulo}".lower()
    for tema, claves in TEMAS:
        if any(clave in texto for clave in claves):
            return tema
    return ""


def adelante(apps, schema_editor):
    Guia = apps.get_model("explorer", "CuratedGuide")
    Region = apps.get_model("explorer", "RegionOSM")
    for guia in Guia.objects.all():
        if guia.zona_id is None and guia.slug in ZONAS_POR_SLUG:
            region = Region.objects.filter(name=ZONAS_POR_SLUG[guia.slug]).order_by("-way_area").first()
            guia.zona_id = region.pk if region else None
        if guia.categoria == "daytrip":
            guia.categoria = "escapada"
        elif guia.categoria == "sector" or guia.zona_id is not None:
            guia.categoria = "zona"
        else:
            guia.categoria = "plan"
        guia.tema = _tema(guia)
        guia.save(update_fields=["categoria", "zona", "tema"])


def atras(apps, schema_editor):
    Guia = apps.get_model("explorer", "CuratedGuide")
    Guia.objects.filter(categoria="escapada").update(categoria="daytrip")
    Guia.objects.filter(categoria="zona", tema="").update(categoria="sector")
    Guia.objects.filter(categoria="zona", tema="comer").update(categoria="gastronomia")
    Guia.objects.filter(categoria__in=["zona", "plan"]).update(categoria="actividad")


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0039_places_contenido_actualizado"),
    ]

    operations = [
        migrations.AddField(
            model_name="curatedguide",
            name="tema",
            field=models.CharField(
                blank=True,
                choices=[("comer", "Comer"), ("noche", "Salir de noche"), ("dia", "De día")],
                default="",
                help_text="Qué plan cubre (opcional). Ordena y rotula las guías dentro de su zona",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="curatedguide",
            name="categoria",
            field=models.CharField(
                choices=[("plan", "Por plan"), ("zona", "Por zona"), ("escapada", "Escapada")],
                db_index=True,
                default="plan",
                max_length=30,
            ),
        ),
        migrations.RunPython(adelante, atras),
    ]
