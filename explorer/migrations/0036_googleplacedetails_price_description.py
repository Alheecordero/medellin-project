from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0035_googleplacedetails"),
    ]

    operations = [
        migrations.AddField(
            model_name="googleplacedetails",
            name="price_level",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Nivel de precio Maps ($, $$, …)",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="googleplacedetails",
            name="description",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Descripción / texto del negocio si aparece en Acerca de",
            ),
        ),
    ]
