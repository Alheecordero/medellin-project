"""
Pipeline ordenado para agregar nuevos lugares: descarte → scan → descarte → procesar.
Opcionalmente añade lugares por nombre (Text Search) antes de procesar.

Evita ejecutar comandos en desorden y muestra costos estimados.
Ver STRATEGIA_NUEVOS_LUGARES.md para la estrategia completa.

Uso:
  python manage.py pipeline_nuevos_lugares --dry-run
  python manage.py pipeline_nuevos_lugares
  python manage.py pipeline_nuevos_lugares --solo-descarte
  python manage.py pipeline_nuevos_lugares --solo-scan
  python manage.py pipeline_nuevos_lugares --solo-procesar --limit 50
  python manage.py pipeline_nuevos_lugares --nombres "Moresko,Purple Club Medellin"
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Ejecuta el pipeline: descarte → scan → descarte → procesar (o solo los pasos indicados).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Solo mostrar qué se haría')
        parser.add_argument('--solo-descarte', action='store_true', help='Solo limpiar cola (excluir ya en Places, descartar inútiles)')
        parser.add_argument('--solo-scan', action='store_true', help='Solo Fase 1: escanear grilla y descubrir place_id')
        parser.add_argument('--solo-procesar', action='store_true', help='Solo Fase 2: procesar pendientes (Place Details)')
        parser.add_argument('--limit', type=int, default=0, help='Si se procesa, máximo de lugares a procesar (0 = todos)')
        parser.add_argument('--nombres', type=str, default='', help='Añadir lugares por nombre (Text Search). Ej: "Moresko,Purple Club"')
        parser.add_argument('--from-file', type=str, default='', help='Archivo con un nombre por línea (lugares a añadir por Text Search)')
        parser.add_argument('--skip-scan', action='store_true', help='En pipeline completo: no ejecutar scan (solo descarte + procesar)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        solo_descarte = options['solo_descarte']
        solo_scan = options['solo_scan']
        solo_procesar = options['solo_procesar']
        limit = options['limit']
        nombres_str = (options['nombres'] or '').strip()
        from_file = (options['from_file'] or '').strip()
        skip_scan = options['skip_scan']

        # Lista de nombres a añadir (por argumento o por archivo)
        nombres_a_anadir = [n.strip() for n in nombres_str.split(',') if n.strip()]
        if from_file:
            path = from_file if os.path.isabs(from_file) else os.path.join(settings.BASE_DIR, from_file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        name = line.strip()
                        if name and not name.startswith('#'):
                            nombres_a_anadir.append(name)
            except FileNotFoundError:
                self.stdout.write(self.style.ERROR(f"Archivo no encontrado: {path}"))
                return

        if dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN (no se ejecuta nada) ===\n'))

        # ─── Solo un paso ───
        if solo_descarte:
            self._run_descarte(dry_run)
            return
        if solo_scan:
            self._run_scan(dry_run)
            return
        if solo_procesar:
            self._run_procesar(dry_run, limit)
            return

        # ─── Añadir por nombres (Text Search) ───
        if nombres_a_anadir:
            for nombre in nombres_a_anadir:
                self.stdout.write(self.style.SUCCESS(f"\n📍 Añadiendo por nombre: \"{nombre}\""))
                if not dry_run:
                    call_command('agregar_lugar_por_nombre', nombre)
                else:
                    self.stdout.write(f"   (dry-run: se llamaría agregar_lugar_por_nombre \"{nombre}\")")

        # ─── Pipeline completo ───
        self.stdout.write(self.style.SUCCESS('\n=== Pipeline nuevos lugares ===\n'))

        # 1) Descarte: limpiar cola (ya en Places + tipos inútiles)
        self._run_descarte(dry_run)

        # 2) Scan: descubrir nuevos place_id desde la grilla
        if not skip_scan:
            self._run_scan(dry_run)
            # 3) Descarte de nuevo (los recién descubiertos)
            self._run_descarte(dry_run)
        else:
            self.stdout.write(self.style.WARNING('   (skip-scan: no se ejecuta escaneo de grilla)'))

        # 4) Estado y procesar
        if not dry_run:
            call_command('procesar_pendientes', '--status')
        self._run_procesar(dry_run, limit)

        self.stdout.write(self.style.SUCCESS('\n=== Fin pipeline ==='))
        if not dry_run and limit == 0:
            self.stdout.write('   Siguiente: python manage.py asignar_regiones && python manage.py calcular_weighted_rating')

    def _run_descarte(self, dry_run):
        self.stdout.write('1. Descarte (excluir ya en Places, marcar inútiles como skipped)...')
        if dry_run:
            call_command('descartar_pendientes_inutiles', '--dry-run')
        else:
            call_command('descartar_pendientes_inutiles')

    def _run_scan(self, dry_run):
        self.stdout.write('\n2. Scan (Nearby Search en puntos de grilla pendientes)...')
        if dry_run:
            call_command('scan_nuevos_lugares', '--dry-run')
        else:
            call_command('scan_nuevos_lugares')

    def _run_procesar(self, dry_run, limit):
        self.stdout.write('\n3. Procesar (Place Details → Places + Foto)...')
        if dry_run:
            self.stdout.write(f'   (dry-run: se llamaría procesar_pendientes{" --limit " + str(limit) if limit else ""})')
            call_command('procesar_pendientes', '--status')
        else:
            args = []
            if limit:
                args.extend(['--limit', str(limit)])
            call_command('procesar_pendientes', *args)
