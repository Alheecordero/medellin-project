# Generated manually for Maps scraper staging model

import django.contrib.gis.db.models.fields
import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("explorer", "0034_place_discovery"),
    ]

    operations = [
        migrations.CreateModel(
            name="GooglePlaceDetails",
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
                ("place_id", models.CharField(db_index=True, max_length=255, unique=True)),
                (
                    "cid",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="CID hex Maps (0x…:0x…) si aparece en la URL",
                        max_length=80,
                    ),
                ),
                ("display_name", models.CharField(blank=True, default="", max_length=500)),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="Etiqueta cruda del panel Maps",
                        max_length=200,
                    ),
                ),
                (
                    "primary_type",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="Código Google canónico (snake_case)",
                        max_length=100,
                    ),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("acai_shop", "Tienda de açaí"),
                            ("afghani_restaurant", "Restaurante afgano"),
                            ("african_restaurant", "Restaurante africano"),
                            ("american_restaurant", "Restaurante americano"),
                            ("amusement_center", "Centro de entretenimiento"),
                            ("art_studio", "Estudio de arte"),
                            ("asian_restaurant", "Restaurante asiático"),
                            ("auditorium", "Auditorio"),
                            ("banquet_hall", "Salón de banquetes"),
                            ("bar", "Bar"),
                            ("bar_and_grill", "Bar y parrilla"),
                            ("barbecue_area", "Área de barbacoa"),
                            ("barbecue_restaurant", "Restaurante de barbacoa"),
                            ("barber_shop", "Barbería"),
                            ("beautician", "Esteticista"),
                            ("beauty_salon", "Salón de belleza"),
                            ("breakfast_restaurant", "Restaurante de desayunos"),
                            ("brunch_restaurant", "Restaurante de brunch"),
                            ("buffet_restaurant", "Restaurante buffet"),
                            ("cafe", "Cafetería"),
                            ("cafeteria", "Comedor"),
                            ("car_wash", "Lavadero de autos"),
                            ("cat_cafe", "Cafetería de gatos"),
                            ("catering_service", "Servicio de catering"),
                            ("childrens_camp", "Campamento infantil"),
                            ("chinese_restaurant", "Restaurante chino"),
                            ("cultural_center", "Centro cultural"),
                            ("dessert_restaurant", "Restaurante de postres"),
                            ("diner", "Cafetería clásica"),
                            ("doctor", "Consultorio médico"),
                            ("dog_cafe", "Cafetería de perros"),
                            ("event_venue", "Lugar de eventos"),
                            ("fast_food_restaurant", "Restaurante de comida rápida"),
                            ("fine_dining_restaurant", "Restaurante gourmet"),
                            ("food", "Tienda de alimentos"),
                            ("food_court", "Patio de comidas"),
                            ("food_delivery", "Entrega de comida"),
                            ("french_restaurant", "Restaurante francés"),
                            ("greek_restaurant", "Restaurante griego"),
                            ("hamburger_restaurant", "Hamburguesería"),
                            ("health", "Servicio de salud"),
                            ("historical_landmark", "Monumento histórico"),
                            ("indian_restaurant", "Restaurante indio"),
                            ("internet_cafe", "Cibercafé"),
                            ("italian_restaurant", "Restaurante italiano"),
                            ("japanese_restaurant", "Restaurante japonés"),
                            ("karaoke", "Karaoke"),
                            ("korean_restaurant", "Restaurante coreano"),
                            ("laundry", "Lavandería"),
                            ("lebanese_restaurant", "Restaurante libanés"),
                            ("market", "Mercado"),
                            ("meal_delivery", "Entrega de comidas"),
                            ("meal_takeaway", "Comida para llevar"),
                            ("mediterranean_restaurant", "Restaurante mediterráneo"),
                            ("mexican_restaurant", "Restaurante mexicano"),
                            ("middle_eastern_restaurant", "Restaurante de Oriente Medio"),
                            ("night_club", "Club nocturno"),
                            ("observation_deck", "Mirador"),
                            ("parking", "Estacionamiento"),
                            ("pizza_restaurant", "Pizzería"),
                            ("playground", "Parque infantil"),
                            ("pub", "Pub"),
                            ("ramen_restaurant", "Restaurante de ramen"),
                            ("ranch", "Rancho"),
                            ("real_estate_agency", "Agencia inmobiliaria"),
                            ("restaurant", "Restaurante"),
                            ("sandwich_shop", "Sandwichería"),
                            ("school", "Escuela"),
                            ("seafood_restaurant", "Marisquería"),
                            ("spa", "Spa"),
                            ("spanish_restaurant", "Restaurante español"),
                            ("sports_club", "Club deportivo"),
                            ("sports_complex", "Complejo deportivo"),
                            ("steak_house", "Parrilla de carnes"),
                            ("sushi_restaurant", "Restaurante de sushi"),
                            ("thai_restaurant", "Restaurante tailandés"),
                            ("turkish_restaurant", "Restaurante turco"),
                            ("vegan_restaurant", "Restaurante vegano"),
                            ("vegetarian_restaurant", "Restaurante vegetariano"),
                            ("vietnamese_restaurant", "Restaurante vietnamita"),
                            ("wellness_center", "Centro de bienestar"),
                            ("wine_bar", "Bar de vinos"),
                            ("otros", "Otros"),
                        ],
                        db_index=True,
                        default="otros",
                        help_text="Tipo Vive (mismo vocabulario que Places.tipo)",
                        max_length=255,
                    ),
                ),
                (
                    "tipo_family",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="other",
                        help_text="Bucket de control: food, nightlife, lodging, …",
                        max_length=40,
                    ),
                ),
                (
                    "tipo_source",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="maps_category | scan_types | search_query | …",
                        max_length=40,
                    ),
                ),
                ("tipo_confidence", models.FloatField(blank=True, null=True)),
                (
                    "types",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=100),
                        blank=True,
                        default=list,
                        size=None,
                    ),
                ),
                (
                    "business_status",
                    models.CharField(blank=True, db_index=True, default="", max_length=40),
                ),
                ("lat", models.FloatField(blank=True, null=True)),
                ("lng", models.FloatField(blank=True, null=True)),
                (
                    "ubicacion",
                    django.contrib.gis.db.models.fields.PointField(
                        blank=True, geography=True, null=True, srid=4326
                    ),
                ),
                ("formatted_address", models.TextField(blank=True, default="")),
                ("plus_code", models.CharField(blank=True, default="", max_length=120)),
                ("rating", models.FloatField(blank=True, db_index=True, null=True)),
                ("user_rating_count", models.PositiveIntegerField(blank=True, null=True)),
                ("phone", models.CharField(blank=True, default="", max_length=80)),
                ("website_uri", models.URLField(blank=True, default="", max_length=1000)),
                (
                    "google_maps_uri",
                    models.URLField(blank=True, default="", max_length=1000),
                ),
                ("menu_uri", models.URLField(blank=True, default="", max_length=1000)),
                ("open_now", models.BooleanField(blank=True, null=True)),
                ("hours_text", models.TextField(blank=True, default="")),
                ("weekday_descriptions", models.TextField(blank=True, default="")),
                ("dine_in", models.BooleanField(blank=True, null=True)),
                ("takeout", models.BooleanField(blank=True, null=True)),
                ("delivery", models.BooleanField(blank=True, null=True)),
                (
                    "amenities",
                    models.JSONField(
                        blank=True,
                        help_text="Atributos visibles en Maps (dict flexible)",
                        null=True,
                    ),
                ),
                ("reviews", models.JSONField(blank=True, null=True)),
                (
                    "photo_urls",
                    models.JSONField(
                        blank=True,
                        help_text="URLs CDN de fotos (sin bytes). Plan 2 = descargar.",
                        null=True,
                    ),
                ),
                ("photos_meta", models.JSONField(blank=True, null=True)),
                ("fetched_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                (
                    "fetch_status",
                    models.CharField(
                        choices=[
                            ("ok", "OK"),
                            ("error", "Error"),
                            ("not_found", "No encontrado"),
                            ("blocked", "Bloqueado /sorry"),
                        ],
                        db_index=True,
                        default="ok",
                        max_length=20,
                    ),
                ),
                ("error_message", models.TextField(blank=True, default="")),
                (
                    "scraper_version",
                    models.CharField(blank=True, default="maps_v1", max_length=40),
                ),
                ("raw_json", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "catalog_entry",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="details",
                        to="explorer.googleplaceid",
                    ),
                ),
            ],
            options={
                "verbose_name": "Google Place Details (staging)",
                "verbose_name_plural": "Google Place Details (staging)",
                "ordering": ["-fetched_at"],
            },
        ),
        migrations.AddIndex(
            model_name="googleplacedetails",
            index=models.Index(
                fields=["category", "rating"], name="explorer_go_categor_0f2a1a_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="googleplacedetails",
            index=models.Index(
                fields=["fetch_status", "fetched_at"],
                name="explorer_go_fetch_s_8c3b2d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="googleplacedetails",
            index=models.Index(
                fields=["tipo_family", "tipo"],
                name="explorer_go_tipo_fa_a1b2c3_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="googleplacedetails",
            index=models.Index(
                fields=["primary_type", "tipo_family"],
                name="explorer_go_primary_d4e5f6_idx",
            ),
        ),
    ]
