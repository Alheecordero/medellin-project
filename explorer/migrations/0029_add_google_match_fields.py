from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0028_enable_unaccent"),
    ]

    operations = [
        migrations.AddField(
            model_name="places",
            name="google_match_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pendiente"),
                    ("matched", "Encontrado"),
                    ("ambiguous", "Ambiguo"),
                    ("not_found", "No encontrado"),
                    ("review", "Revisar"),
                ],
                db_index=True,
                default="pending",
                help_text="Estado de verificación del place_id contra Google Text Search (IDs Only)",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="places",
            name="google_match_confidence",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Confianza de la coincidencia (0–1)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="places",
            name="google_match_checked_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Última verificación gratuita vía Text Search IDs Only",
                null=True,
            ),
        ),
    ]
