from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0032_googleplaceid"),
    ]

    operations = [
        migrations.AddField(
            model_name="initialgrid",
            name="text_scan_passes",
            field=ArrayField(
                base_field=models.CharField(max_length=30),
                blank=True,
                default=list,
                help_text="Pasadas gratis completadas: bias, restriction, generico",
                size=None,
            ),
        ),
        migrations.AlterField(
            model_name="googleplaceid",
            name="source",
            field=models.CharField(
                choices=[
                    ("text_search_ids", "Text Search IDs Only"),
                    ("text_search_restriction", "Text Search restriction (IDs Only)"),
                    ("text_search_generico", "Text Search genérico (IDs Only)"),
                    ("places_import", "Importado desde Places"),
                    ("pending_import", "Importado desde PendingPlace"),
                    ("nearby_search", "Nearby Search"),
                    ("manual", "Manual"),
                ],
                db_index=True,
                default="text_search_ids",
                max_length=30,
            ),
        ),
    ]
