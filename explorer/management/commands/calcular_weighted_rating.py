"""
Management command para calcular el weighted_rating usando Bayesian Average.

Fórmula: WR = (v / (v + m)) × R + (m / (v + m)) × C

Donde:
- v = total_reviews del lugar
- R = rating del lugar
- m = número mínimo de reviews para ser considerado (umbral)
- C = rating promedio global

Esto hace que lugares con pocas reviews converjan hacia el promedio,
mientras que lugares con muchas reviews mantienen su rating real.
"""
import time
from django.core.management.base import BaseCommand
from django.db.models import Avg
from explorer.models import Places


class Command(BaseCommand):
    help = 'Calcula el weighted_rating para todos los lugares usando Bayesian Average'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-reviews',
            type=int,
            default=25,
            help='Número mínimo de reviews para considerar (m). Default: 25'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar cálculos sin guardar en BD'
        )
        parser.add_argument(
            '--show-all',
            action='store_true',
            help='Mostrar TODOS los lugares procesados (muy verbose)'
        )
        parser.add_argument(
            '--only-missing',
            action='store_true',
            help='Solo procesar lugares SIN weighted_rating (más rápido)'
        )

    def handle(self, *args, **options):
        min_reviews = options['min_reviews']
        dry_run = options['dry_run']
        show_all = options['show_all']
        only_missing = options['only_missing']

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 60))
        self.stdout.write(self.style.MIGRATE_HEADING('   CALCULANDO WEIGHTED RATING (Bayesian Average)'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 60))
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # PASO 1: Calcular estadísticas globales
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.WARNING('📊 PASO 1: Calculando estadísticas globales...'))
        
        stats = Places.objects.filter(
            rating__isnull=False,
            total_reviews__isnull=False,
            total_reviews__gt=0
        ).aggregate(avg_rating=Avg('rating'))
        
        C = stats['avg_rating'] or 4.36
        m = min_reviews
        
        self.stdout.write(f'   Rating promedio global (C): {self.style.SUCCESS(f"{C:.4f}")}')
        self.stdout.write(f'   Umbral mínimo de reviews (m): {self.style.SUCCESS(str(m))}')
        self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # PASO 2: Obtener lugares a procesar
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.WARNING('📋 PASO 2: Obteniendo lugares a procesar...'))
        
        lugares = Places.objects.filter(rating__isnull=False)
        
        if only_missing:
            lugares = lugares.filter(weighted_rating__isnull=True)
            self.stdout.write(f'   Modo: {self.style.SUCCESS("--only-missing")} (solo lugares sin weighted_rating)')
        
        lugares = lugares.only('id', 'nombre', 'rating', 'total_reviews', 'weighted_rating')
        
        total = lugares.count()
        total_con_rating = Places.objects.filter(rating__isnull=False).count()
        ya_procesados = Places.objects.filter(rating__isnull=False, weighted_rating__isnull=False).count()
        
        self.stdout.write(f'   Total lugares con rating: {total_con_rating}')
        self.stdout.write(f'   Ya procesados: {self.style.SUCCESS(str(ya_procesados))}')
        self.stdout.write(f'   Pendientes: {self.style.WARNING(str(total))}')
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  MODO DRY-RUN: No se guardarán cambios en la BD'))
            self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # PASO 3: Procesar lugares
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.WARNING('⚙️  PASO 3: Procesando lugares...'))
        self.stdout.write('')
        self.stdout.write(f"{'#':>6} | {'Nombre':<35} | {'Rating':>6} | {'Reviews':>7} | {'Weighted':>8} | {'Cambio':>8}")
        self.stdout.write('-' * 85)

        # Estadísticas
        updated = 0
        unchanged = 0
        start_time = time.time()
        
        # Ejemplos para el resumen
        ejemplos_bajaron = []  # Lugares que bajaron (pocas reviews)
        ejemplos_subieron = []  # Lugares que subieron o mantuvieron
        ejemplos_extremos = []  # 5.0 con pocas reviews

        for i, lugar in enumerate(lugares.iterator(chunk_size=500), 1):
            v = lugar.total_reviews or 0
            R = lugar.rating
            old_weighted = lugar.weighted_rating

            # Calcular weighted rating
            if v == 0:
                weighted = C
            else:
                weighted = (v / (v + m)) * R + (m / (v + m)) * C

            weighted = round(weighted, 4)
            
            # Calcular diferencia
            diff = weighted - R
            if diff < -0.01:
                direction = self.style.ERROR(f'↓{abs(diff):.3f}')
            elif diff > 0.01:
                direction = self.style.SUCCESS(f'↑{abs(diff):.3f}')
            else:
                direction = f'={abs(diff):.3f}'

            # Guardar ejemplos interesantes
            if R == 5.0 and v <= 5 and len(ejemplos_extremos) < 5:
                ejemplos_extremos.append({'nombre': lugar.nombre[:30], 'rating': R, 'reviews': v, 'weighted': weighted})
            if diff < -0.3 and len(ejemplos_bajaron) < 5:
                ejemplos_bajaron.append({'nombre': lugar.nombre[:30], 'rating': R, 'reviews': v, 'weighted': weighted, 'diff': diff})
            if diff >= 0 and v >= 100 and len(ejemplos_subieron) < 5:
                ejemplos_subieron.append({'nombre': lugar.nombre[:30], 'rating': R, 'reviews': v, 'weighted': weighted, 'diff': diff})

            # Log cada 500 lugares o si show_all está activado
            if show_all or i % 500 == 0 or i == total:
                nombre_truncado = lugar.nombre[:35] if len(lugar.nombre) <= 35 else lugar.nombre[:32] + '...'
                self.stdout.write(
                    f'{i:>6} | {nombre_truncado:<35} | {R:>6.2f} | {v:>7} | {weighted:>8.4f} | {direction}'
                )

            # Guardar en BD
            if not dry_run:
                if lugar.weighted_rating != weighted:
                    lugar.weighted_rating = weighted
                    lugar.save(update_fields=['weighted_rating'])
                    updated += 1
                else:
                    unchanged += 1
            else:
                updated += 1

        elapsed = time.time() - start_time
        
        # ═══════════════════════════════════════════════════════════════
        # PASO 4: Resumen
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 60))
        self.stdout.write(self.style.MIGRATE_HEADING('   RESUMEN'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 60))
        self.stdout.write('')
        
        self.stdout.write(f'   ✅ Lugares procesados: {self.style.SUCCESS(str(total))}')
        if not dry_run:
            self.stdout.write(f'   📝 Actualizados: {self.style.SUCCESS(str(updated))}')
            self.stdout.write(f'   ⏭️  Sin cambios: {unchanged}')
        self.stdout.write(f'   ⏱️  Tiempo: {elapsed:.2f} segundos')
        self.stdout.write('')

        # Mostrar ejemplos interesantes
        if ejemplos_extremos:
            self.stdout.write(self.style.WARNING('🔻 Lugares con 5.0⭐ pero POCAS reviews (bajan más):'))
            for ex in ejemplos_extremos:
                self.stdout.write(f"   • {ex['nombre']}: {ex['rating']}⭐ ({ex['reviews']} reviews) → WR: {ex['weighted']:.2f}")
            self.stdout.write('')

        if ejemplos_bajaron:
            self.stdout.write(self.style.WARNING('📉 Ejemplos que BAJAN significativamente:'))
            for ex in ejemplos_bajaron:
                self.stdout.write(f"   • {ex['nombre']}: {ex['rating']}⭐ ({ex['reviews']} reviews) → WR: {ex['weighted']:.2f} ({ex['diff']:.2f})")
            self.stdout.write('')

        if ejemplos_subieron:
            self.stdout.write(self.style.SUCCESS('📈 Ejemplos con MUCHAS reviews (mantienen rating):'))
            for ex in ejemplos_subieron:
                self.stdout.write(f"   • {ex['nombre']}: {ex['rating']}⭐ ({ex['reviews']} reviews) → WR: {ex['weighted']:.2f}")
            self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # PASO 5: Top 10 nuevo ranking
        # ═══════════════════════════════════════════════════════════════
        if not dry_run:
            self.stdout.write(self.style.MIGRATE_HEADING('🏆 TOP 10 POR WEIGHTED RATING:'))
            self.stdout.write('')
            
            top_10 = Places.objects.filter(
                weighted_rating__isnull=False,
                tiene_fotos=True
            ).order_by('-weighted_rating')[:10]
            
            for i, p in enumerate(top_10, 1):
                self.stdout.write(
                    f'   {i:>2}. {p.nombre[:40]:<40} | '
                    f'WR: {self.style.SUCCESS(f"{p.weighted_rating:.4f}")} | '
                    f'Rating: {p.rating:.1f}⭐ | '
                    f'Reviews: {p.total_reviews or 0}'
                )
            self.stdout.write('')

        # ═══════════════════════════════════════════════════════════════
        # Mensaje final
        # ═══════════════════════════════════════════════════════════════
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('   ✓ PROCESO COMPLETADO EXITOSAMENTE'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write('')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('💡 Para aplicar los cambios, ejecuta sin --dry-run:'))
            self.stdout.write('   python manage.py calcular_weighted_rating')
        else:
            self.stdout.write(self.style.SUCCESS('💡 Los lugares ahora se ordenan por weighted_rating'))
            self.stdout.write('   Esto prioriza lugares con MÁS reviews sobre los de pocas.')
