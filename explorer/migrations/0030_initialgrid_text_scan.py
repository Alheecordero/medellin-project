from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0029_add_google_match_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="initialgrid",
            name="is_text_scan_processed",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Escaneado con Text Search IDs Only (scan_place_ids_gratis, gratis)",
            ),
        ),
        migrations.AlterField(
            model_name="initialgrid",
            name="is_processed",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Escaneado con Nearby Search (scan_nuevos_lugares, de pago)",
            ),
        ),
    ]
