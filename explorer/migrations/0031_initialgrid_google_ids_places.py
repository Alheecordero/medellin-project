from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0030_initialgrid_text_scan"),
    ]

    operations = [
        migrations.AddField(
            model_name="initialgrid",
            name="google_ids_places",
            field=ArrayField(
                base_field=models.CharField(max_length=255),
                blank=True,
                default=list,
                help_text="Google Place IDs descubiertos en este punto de grilla (scan gratis)",
                size=None,
            ),
        ),
    ]
