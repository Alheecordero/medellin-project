from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0037_partner_menus_and_guide_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="places",
            name="solo_en_guia",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Parada de guía (mall, UVA, parque). No sale en el buscador. Un restaurante dentro de una guía sigue buscable.",
            ),
        ),
    ]
