from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0031_initialgrid_google_ids_places"),
    ]

    operations = [
        migrations.CreateModel(
            name="GooglePlaceId",
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
                    "place_id",
                    models.CharField(db_index=True, max_length=255, unique=True),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("text_search_ids", "Text Search IDs Only"),
                            ("nearby_search", "Nearby Search"),
                            ("manual", "Manual"),
                        ],
                        db_index=True,
                        default="text_search_ids",
                        max_length=30,
                    ),
                ),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("discovery_count", models.PositiveIntegerField(default=1)),
                (
                    "scan_types",
                    ArrayField(
                        base_field=models.CharField(max_length=100),
                        blank=True,
                        default=list,
                        help_text="Tipos Google con los que se descubrió (includedType)",
                        size=None,
                    ),
                ),
                (
                    "area_names",
                    ArrayField(
                        base_field=models.CharField(max_length=100),
                        blank=True,
                        default=list,
                        help_text="Zonas SCAN_AREAS donde cayó el punto de grilla",
                        size=None,
                    ),
                ),
                ("scan_lat", models.FloatField(blank=True, null=True)),
                ("scan_lng", models.FloatField(blank=True, null=True)),
                (
                    "first_grid_point",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="google_place_ids",
                        to="explorer.initialgrid",
                    ),
                ),
            ],
            options={
                "verbose_name": "Google Place ID (catálogo)",
                "verbose_name_plural": "Google Place IDs (catálogo)",
                "ordering": ["-first_seen_at"],
                "indexes": [
                    models.Index(
                        fields=["source", "first_seen_at"],
                        name="explorer_go_source__a8f3b1_idx",
                    )
                ],
            },
        ),
    ]
