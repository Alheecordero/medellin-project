from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0036_googleplacedetails_price_description"),
    ]

    operations = [
        migrations.AddField(
            model_name="curatedguide",
            name="como_recorrer",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Cómo hacer el recorrido, en español",
            ),
        ),
        migrations.AddField(
            model_name="curatedguideitem",
            name="como_llegar",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Cómo llegar a esta parada",
                max_length=300,
            ),
        ),
        migrations.AddField(
            model_name="curatedguideitem",
            name="advertencia",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Aviso corto: horario, seguridad, día de visita",
                max_length=300,
            ),
        ),
        migrations.CreateModel(
            name="PlacePartnerMenu",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "platform",
                    models.CharField(
                        choices=[
                            ("rappi", "Rappi"),
                            ("didi", "DiDi Food"),
                            ("ifood", "iFood"),
                            ("ubereats", "Uber Eats"),
                        ],
                        max_length=20,
                    ),
                ),
                ("source_url", models.URLField(blank=True, default="", max_length=1000)),
                ("external_id", models.CharField(blank=True, default="", max_length=80)),
                ("store_name", models.CharField(blank=True, default="", max_length=300)),
                ("address", models.TextField(blank=True, default="")),
                (
                    "partner_urls",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Todas las URLs de pedido, incluida la que no se escogió",
                    ),
                ),
                ("item_count", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "lugar",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="carta",
                        to="explorer.places",
                    ),
                ),
            ],
            options={
                "verbose_name": "Carta de partner",
                "verbose_name_plural": "Cartas de partner",
            },
        ),
        migrations.CreateModel(
            name="PlacePartnerDish",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("external_id", models.CharField(blank=True, default="", max_length=80)),
                ("name", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True, default="")),
                ("price", models.PositiveIntegerField(blank=True, null=True)),
                ("price_text", models.CharField(blank=True, default="", max_length=40)),
                (
                    "original_price_text",
                    models.CharField(blank=True, default="", max_length=40),
                ),
                ("image_url", models.URLField(blank=True, default="", max_length=1000)),
                ("section", models.CharField(blank=True, default="", max_length=200)),
                ("is_available", models.BooleanField(default=True)),
                ("position", models.PositiveIntegerField(default=0)),
                (
                    "carta",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="platos",
                        to="explorer.placepartnermenu",
                    ),
                ),
            ],
            options={
                "verbose_name": "Plato",
                "verbose_name_plural": "Platos",
                "ordering": ["position"],
            },
        ),
        migrations.AddIndex(
            model_name="placepartnerdish",
            index=models.Index(
                fields=["carta", "position"], name="explorer_partnerdish_pos"
            ),
        ),
    ]
