from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import logging

import requests
from PIL import Image

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from explorer.models import Places, Foto


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Genera variantes optimizadas para las fotos de los lugares.

    - No altera el campo `imagen` original.
    - Crea y guarda URLs en `imagen_mediana` (≈800px ancho) y
      `imagen_miniatura` (≈200px ancho) usando el backend de storage
      configurado (GCS en producción, FileSystemStorage en local).
    - Puede trabajar por slug, place_id o en modo batch.
    """

    help = "Optimiza imágenes de lugares generando variantes mediana y miniatura."

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            type=str,
            help="Procesar solo un lugar por slug SEO (Places.slug)",
        )
        parser.add_argument(
            "--place-id",
            type=str,
            help="Procesar solo un lugar por place_id (Places.place_id)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Número máximo de lugares a procesar en modo batch (por defecto: 50)",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="Offset inicial para modo batch (paginación manual, por defecto: 0)",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=4,
            help="Número de workers paralelos (por defecto: 4)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reprocesar fotos aunque ya tengan imagen_mediana/imagen_miniatura y el lugar esté marcado como optimizado.",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            default=True,
            help="(Por defecto) Solo procesar fotos que no tengan variantes generadas.",
        )
        parser.add_argument(
            "--no-only-missing",
            action="store_false",
            dest="only_missing",
            help="Desactivar el filtro de only-missing (útil combinado con --force).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simular el proceso sin guardar archivos ni modificar la base de datos.",
        )

    def handle(self, *args, **options):
        slug = options.get("slug")
        place_id = options.get("place_id")
        batch_size = options.get("batch_size", 50)
        offset = options.get("offset", 0)
        workers = options.get("workers", 4)
        force = options.get("force", False)
        only_missing = options.get("only_missing", True)
        dry_run = options.get("dry_run", False)

        if batch_size <= 0:
            raise CommandError("--batch-size debe ser > 0")
        if workers <= 0:
            raise CommandError("--workers debe ser > 0")
        if slug and place_id:
            raise CommandError("Usa solo uno de --slug o --place-id, no ambos.")

        if slug or place_id:
            place = self._get_single_place(slug=slug, place_id=place_id)
            if not place:
                raise CommandError("Lugar no encontrado.")

            self.stdout.write(
                self.style.SUCCESS(
                    f"Procesando lugar único: {place.nombre} "
                    f"(id={place.id}, slug={place.slug}, place_id={place.place_id})"
                )
            )
            ok = self._process_place(
                place,
                force=force,
                only_missing=only_missing,
                dry_run=dry_run,
            )
            if ok:
                self.stdout.write(
                    self.style.SUCCESS(
                        "✓ Variantes generadas correctamente"
                        if not dry_run
                        else "✓ Simulación completada (dry-run)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "No se generaron variantes (puede que ya estuvieran todas creadas)."
                    )
                )
            return

        # Modo batch
        qs = self._get_places_queryset(force=force, only_missing=only_missing)
        qs = qs.order_by("id")[offset : offset + batch_size]
        places = list(qs)

        if not places:
            self.stdout.write(
                self.style.WARNING(
                    "No se encontraron lugares candidatos para optimización."
                )
            )
            return

        total = len(places)
        self.stdout.write(
            self.style.SUCCESS(
                f"Iniciando optimización batch: {total} lugares, workers={workers}, "
                f"offset={offset}, only_missing={only_missing}, force={force}, dry_run={dry_run}"
            )
        )

        total_ok = 0
        total_fail = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self._process_place,
                    place,
                    force=force,
                    only_missing=only_missing,
                    dry_run=dry_run,
                ): place
                for place in places
            }

            for idx, future in enumerate(as_completed(futures), start=1):
                place = futures[future]
                try:
                    ok = future.result()
                except Exception as e:  # noqa: BLE001
                    logger.exception("Error procesando lugar %s: %s", place.id, e)
                    ok = False

                if ok:
                    total_ok += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ [{idx}/{total}] {place.nombre} (id={place.id})"
                        )
                    )
                else:
                    total_fail += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ [{idx}/{total}] {place.nombre} (id={place.id})"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nOptimización completa. Lugares OK: {total_ok}, con errores: {total_fail}"
            )
        )

    # ──────────────────────────────────────────────────────────────
    # Helpers de selección
    # ──────────────────────────────────────────────────────────────

    def _get_single_place(self, slug: str | None, place_id: str | None) -> Places | None:
        qs = Places.objects.all()
        if slug:
            qs = qs.filter(slug=slug)
        if place_id:
            qs = qs.filter(place_id=place_id)
        return qs.first()

    def _get_places_queryset(self, force: bool, only_missing: bool):
        """
        Devuelve los lugares candidatos a optimizar.

        - Tiene fotos.
        - Si only_missing=True: prioriza lugares donde haya al menos una Foto sin variantes.
        - Si force=True: no se tienen en cuenta flags, se devolverá cualquier lugar con fotos.
        """
        qs = Places.objects.filter(tiene_fotos=True)

        if not force:
            try:
                # Evitar reprocesar en masa cuando ya marcaste como optimizado
                qs = qs.filter(Q(imagenes_optimizadas=False) | Q(imagenes_optimizadas__isnull=True))
            except Exception:
                # Si la columna aún no existe en la BD, ignoramos este filtro
                pass

        # Prefetch básico de fotos para evitar N+1
        qs = qs.prefetch_related("fotos")

        if only_missing:
            # Filtrar a nivel de Python cuando ya tenemos los lugares prefetcheados:
            # nos quedamos con lugares donde exista al menos una Foto sin variantes.
            ids = []
            for place in qs:
                if any(
                    (not f.imagen_mediana or not f.imagen_miniatura)
                    for f in place.fotos.all()
                ):
                    ids.append(place.id)
            qs = Places.objects.filter(id__in=ids).prefetch_related("fotos")

        return qs

    # ──────────────────────────────────────────────────────────────
    # Procesamiento principal por lugar/foto
    # ──────────────────────────────────────────────────────────────

    def _process_place(
        self,
        place: Places,
        force: bool,
        only_missing: bool,
        dry_run: bool,
    ) -> bool:
        fotos = list(Foto.objects.filter(lugar=place))
        if not fotos:
            logger.info("Lugar %s no tiene fotos, se omite.", place.id)
            return False

        processed = 0
        errors = 0

        for foto in fotos:
            try:
                if not foto.imagen:
                    continue

                if only_missing and not force:
                    if foto.imagen_mediana and foto.imagen_miniatura:
                        # Ya tiene ambas variantes; saltar
                        continue

                img_url = str(foto.imagen).strip()
                if not img_url:
                    continue

                # Si la URL no es absoluta, intentar construirla usando el bucket (caso legado)
                if not img_url.startswith("http"):
                    bucket = getattr(settings, "GS_BUCKET_NAME", "").strip()
                    if bucket:
                        img_url = f"https://storage.googleapis.com/{bucket}/{img_url.lstrip('/')}"

                # Descargar la imagen original
                resp = requests.get(img_url, timeout=30)
                resp.raise_for_status()

                original = Image.open(BytesIO(resp.content))
                img = self._ensure_rgb(original)

                # Generar variantes
                medium_bytes = self._resize_and_serialize(img, target_width=800)
                thumb_bytes = self._resize_and_serialize(img, target_width=220)

                # Guardar en storage y actualizar URLs
                self._save_variants_for_foto(
                    place,
                    foto,
                    medium_bytes,
                    thumb_bytes,
                    dry_run=dry_run,
                )
                processed += 1

            except Exception as e:  # noqa: BLE001
                errors += 1
                logger.warning(
                    "Error procesando foto id=%s de lugar id=%s: %s",
                    getattr(foto, "id", None),
                    place.id,
                    e,
                )
                continue

        if processed == 0:
            if errors:
                self.stdout.write(
                    self.style.WARNING(
                        f"Lugar {place.id}: no se pudieron procesar fotos "
                        f"({errors} errores)."
                    )
                )
            return False

        # Marcar lugar como optimizado si no es dry-run y la columna existe
        if not dry_run:
            try:
                with transaction.atomic():
                    place.refresh_from_db()
                    place.imagenes_optimizadas = True
                    place.save(update_fields=["imagenes_optimizadas"])
            except Exception:
                # Si la columna no existe o hay problema, simplemente continuamos
                logger.warning(
                    "No se pudo marcar imagenes_optimizadas para lugar id=%s", place.id
                )

        if errors:
            self.stdout.write(
                self.style.WARNING(
                    f"Lugar {place.id}: {processed} fotos procesadas, "
                    f"{errors} con error."
                )
            )

        return True

    # ──────────────────────────────────────────────────────────────
    # Helpers de imagen / storage
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_rgb(img: Image.Image) -> Image.Image:
        """Convierte la imagen a RGB manejando transparencia correctamente."""
        if img.mode in ("RGBA", "LA", "P"):
            base = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            alpha = img.split()[-1] if img.mode in ("RGBA", "LA") else None
            base.paste(img, mask=alpha)
            return base
        if img.mode != "RGB":
            return img.convert("RGB")
        return img

    @staticmethod
    def _resize_to_width(img: Image.Image, target_width: int) -> Image.Image:
        """Redimensiona manteniendo relación de aspecto."""
        if img.width <= target_width:
            return img.copy()
        ratio = target_width / float(img.width)
        new_height = int(img.height * ratio)
        return img.resize(
            (target_width, new_height),
            Image.Resampling.LANCZOS,
        )

    def _resize_and_serialize(
        self,
        img: Image.Image,
        target_width: int,
        quality: int = 85,
    ) -> BytesIO:
        """Redimensiona y serializa a JPEG optimizado, devolviendo un BytesIO listo para guardar."""
        resized = self._resize_to_width(img, target_width=target_width)
        buffer = BytesIO()
        resized.save(buffer, format="JPEG", quality=quality, optimize=True)
        buffer.seek(0)
        return buffer

    def _save_variants_for_foto(
        self,
        place: Places,
        foto: Foto,
        medium_bytes: BytesIO,
        thumb_bytes: BytesIO,
        dry_run: bool,
    ) -> None:
        """
        Guarda las variantes de una foto en el storage por defecto y
        actualiza los campos URL correspondientes.

        No altera la URL original `imagen`.
        """
        base_dir = "tourism/images"

        # Construir rutas relativamente estables.
        place_part = place.slug or place.place_id or str(place.id)
        foto_id = getattr(foto, "id", None) or "unknown"

        medium_path = f"{base_dir}/medium/{place_part}/{foto_id}.jpg"
        thumb_path = f"{base_dir}/thumb/{place_part}/{foto_id}.jpg"

        # Guardar en el backend configurado (GCS en prod, FS en local)
        if dry_run:
            # No escribir ni en storage ni en DB
            logger.info(
                "[dry-run] Generadas variantes para foto id=%s de lugar id=%s -> %s, %s",
                getattr(foto, "id", None),
                place.id,
                medium_path,
                thumb_path,
            )
            return

        medium_name = default_storage.save(
            medium_path,
            ContentFile(medium_bytes.getvalue()),
        )
        thumb_name = default_storage.save(
            thumb_path,
            ContentFile(thumb_bytes.getvalue()),
        )

        # Obtener URLs públicas
        medium_url = default_storage.url(medium_name)
        thumb_url = default_storage.url(thumb_name)

        # Actualizar solo esta foto en BD
        Foto.objects.filter(pk=foto.pk).update(
            imagen_mediana=medium_url,
            imagen_miniatura=thumb_url,
        )


