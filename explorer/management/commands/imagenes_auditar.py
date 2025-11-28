from django.core.management.base import BaseCommand

from explorer.models import Places, Foto


class Command(BaseCommand):
    help = "Muestra métricas de estado sobre imágenes y variantes optimizadas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            type=str,
            help="Auditar solo un lugar por slug SEO (Places.slug)",
        )
        parser.add_argument(
            "--place-id",
            type=str,
            help="Auditar solo un lugar por place_id (Places.place_id)",
        )

    def handle(self, *args, **options):
        slug = options.get("slug")
        place_id = options.get("place_id")

        if slug and place_id:
            self.stderr.write(
                self.style.ERROR("Usa solo uno de --slug o --place-id, no ambos.")
            )
            return

        if slug or place_id:
            self._audit_single(slug=slug, place_id=place_id)
        else:
            self._audit_global()

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    def _audit_global(self):
        total_places = Places.objects.count()
        lugares_con_fotos = Places.objects.filter(tiene_fotos=True).count()

        total_fotos = Foto.objects.count()
        fotos_con_mediana = Foto.objects.exclude(imagen_mediana__isnull=True).exclude(
            imagen_mediana=""
        ).count()
        fotos_con_miniatura = Foto.objects.exclude(
            imagen_miniatura__isnull=True
        ).exclude(imagen_miniatura="").count()

        try:
            lugares_optimizados = Places.objects.filter(
                imagenes_optimizadas=True
            ).count()
        except Exception:
            lugares_optimizados = None

        self.stdout.write(self.style.SUCCESS("Resumen global de imágenes"))
        self.stdout.write("-" * 50)
        self.stdout.write(f"Lugares totales           : {total_places}")
        self.stdout.write(f"Lugares con fotos         : {lugares_con_fotos}")
        self.stdout.write("")
        self.stdout.write(f"Fotos totales             : {total_fotos}")
        self.stdout.write(f"Fotos con imagen_mediana  : {fotos_con_mediana}")
        self.stdout.write(f"Fotos con imagen_miniatura: {fotos_con_miniatura}")
        if lugares_optimizados is not None:
            self.stdout.write(f"Lugares optimizados       : {lugares_optimizados}")

    def _audit_single(self, slug: str | None, place_id: str | None):
        qs = Places.objects.all()
        if slug:
            qs = qs.filter(slug=slug)
        if place_id:
            qs = qs.filter(place_id=place_id)

        place = qs.first()
        if not place:
            self.stderr.write(self.style.ERROR("Lugar no encontrado."))
            return

        fotos = list(Foto.objects.filter(lugar=place))
        total_fotos = len(fotos)
        fotos_mediana = sum(
            1 for f in fotos if f.imagen_mediana is not None and f.imagen_mediana != ""
        )
        fotos_miniatura = sum(
            1
            for f in fotos
            if f.imagen_miniatura is not None and f.imagen_miniatura != ""
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Resumen para lugar: {place.nombre} "
                f"(id={place.id}, slug={place.slug}, place_id={place.place_id})"
            )
        )
        self.stdout.write("-" * 50)
        self.stdout.write(f"Total fotos               : {total_fotos}")
        self.stdout.write(f"Con imagen_mediana        : {fotos_mediana}")
        self.stdout.write(f"Con imagen_miniatura      : {fotos_miniatura}")

        try:
            optimizado = getattr(place, "imagenes_optimizadas", None)
        except Exception:
            optimizado = None

        if optimizado is not None:
            self.stdout.write(f"imagenes_optimizadas      : {optimizado}")


