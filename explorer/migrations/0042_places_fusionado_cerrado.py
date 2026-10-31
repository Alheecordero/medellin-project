import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0041_centrocomercial"),
    ]

    operations = [
        migrations.AddField(
            model_name="places",
            name="fusionado_en",
            field=models.ForeignKey(
                blank=True,
                help_text="Duplicado de otra ficha: su URL redirige (301) a esa. Lo pone limpiar_fichas",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="fusionados",
                to="explorer.places",
            ),
        ),
        migrations.AddField(
            model_name="places",
            name="cerrado_permanente",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Cerrado para siempre según Maps: sale del sitio y su URL da 410. Lo pone limpiar_fichas",
            ),
        ),
    ]
