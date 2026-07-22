"""
Estadísticas de lugares pendientes descartados (status=skipped).
Muestra por tipo: cuántos lugares descartados tienen ese tipo, para analizar.

Uso:
  python manage.py estadisticas_descartados                    # Resumen en consola
  python manage.py estadisticas_descartados --csv              # Salida CSV
  python manage.py estadisticas_descartados --csv -o reporte.csv
  python manage.py estadisticas_descartados --json             # Salida JSON
"""
import csv
import json
from collections import defaultdict
from io import StringIO

from django.core.management.base import BaseCommand
from django.db.models import Count

from explorer.models import PendingPlace


class Command(BaseCommand):
    help = 'Estadísticas de tipos en lugares descartados (skipped).'

    def add_arguments(self, parser):
        parser.add_argument('--csv', action='store_true', help='Exportar a CSV')
        parser.add_argument('--json', action='store_true', help='Exportar a JSON')
        parser.add_argument('-o', '--output', type=str, default='',
                            help='Archivo de salida (por defecto stdout o estadisticas_descartados.csv/.json)')

    def handle(self, *args, **options):
        use_csv = options['csv']
        use_json = options['json']
        output_path = options['output'].strip()

        descartados = PendingPlace.objects.filter(status='skipped')
        total = descartados.count()

        # Contar por tipo: tipo -> número de lugares descartados que tienen ese tipo
        tipo_counts = defaultdict(int)
        # Por cada lugar, sumar 1 por cada tipo que tenga (un lugar puede tener varios tipos)
        for p in descartados.only('tipos').iterator(chunk_size=500):
            for t in (p.tipos or []):
                if t:
                    tipo_counts[t] += 1

        # Ordenar por cantidad descendente
        tipos_ordenados = sorted(tipo_counts.items(), key=lambda x: -x[1])

        # Totales por estado (contexto)
        total_pending = PendingPlace.objects.filter(status='pending').count()
        total_processed = PendingPlace.objects.filter(status='processed').count()
        total_failed = PendingPlace.objects.filter(status='failed').count()

        if use_csv:
            self._export_csv(tipos_ordenados, total, total_pending, total_processed, total_failed, output_path)
        elif use_json:
            self._export_json(tipos_ordenados, total, total_pending, total_processed, total_failed, output_path)
        else:
            self._print_console(tipos_ordenados, total, total_pending, total_processed, total_failed)

    def _print_console(self, tipos_ordenados, total_descartados, total_pending, total_processed, total_failed):
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(self.style.SUCCESS('  ESTADÍSTICAS DE LUGARES DESCARTADOS (skipped)'))
        self.stdout.write('═' * 60)
        self.stdout.write('')
        self.stdout.write(f'  Total descartados:     {total_descartados:,}')
        self.stdout.write(f'  Pendientes:            {total_pending:,}')
        self.stdout.write(f'  Procesados:            {total_processed:,}')
        self.stdout.write(f'  Fallidos:              {total_failed:,}')
        self.stdout.write('')
        self.stdout.write('  Tipos presentes en descartados (cuántos lugares tienen ese tipo):')
        self.stdout.write('  ' + '-' * 56)
        self.stdout.write(f'  {"TIPO":<45} {"CANT":>8}')
        self.stdout.write('  ' + '-' * 56)
        for tipo, cant in tipos_ordenados:
            self.stdout.write(f'  {tipo:<45} {cant:>8,}')
        self.stdout.write('  ' + '-' * 56)
        self.stdout.write(f'  Total filas (tipos):  {len(tipos_ordenados)}')
        self.stdout.write('')

    def _export_csv(self, tipos_ordenados, total_descartados, total_pending, total_processed, total_failed, output_path):
        path = output_path or 'estadisticas_descartados.csv'
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(['resumen', 'total_descartados', total_descartados])
        w.writerow(['resumen', 'total_pending', total_pending])
        w.writerow(['resumen', 'total_processed', total_processed])
        w.writerow(['resumen', 'total_failed', total_failed])
        w.writerow([])
        w.writerow(['tipo', 'cantidad_lugares_con_este_tipo'])
        for tipo, cant in tipos_ordenados:
            w.writerow([tipo, cant])
        content = buf.getvalue()
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        self.stdout.write(self.style.SUCCESS(f'CSV guardado: {path}'))

    def _export_json(self, tipos_ordenados, total_descartados, total_pending, total_processed, total_failed, output_path):
        path = output_path or 'estadisticas_descartados.json'
        data = {
            'resumen': {
                'total_descartados': total_descartados,
                'total_pending': total_pending,
                'total_processed': total_processed,
                'total_failed': total_failed,
            },
            'tipos': [{'tipo': t, 'cantidad': c} for t, c in tipos_ordenados],
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.stdout.write(self.style.SUCCESS(f'JSON guardado: {path}'))
