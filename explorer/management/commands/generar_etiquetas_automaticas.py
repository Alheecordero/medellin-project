from django.core.management.base import BaseCommand
from explorer.models import Places
from django.db.models import Q, Count
from django.core.cache import cache

class Command(BaseCommand):
    help = 'Genera etiquetas automáticas para los lugares basadas en sus características'

    def add_arguments(self, parser):
        parser.add_argument(
            '--borrar',
            action='store_true',
            help='Borra todas las etiquetas existentes antes de generar nuevas',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra las etiquetas que se generarían sin aplicar los cambios',
        )
        parser.add_argument(
            '--id',
            type=int,
            help='ID del lugar específico para generar etiquetas',
        )
        parser.add_argument(
            '--nombre',
            type=str,
            help='Nombre del lugar para generar etiquetas',
        )
        parser.add_argument(
            '--desde-id',
            type=int,
            help='Continuar procesando desde este ID',
        )
        parser.add_argument(
            '--solo-sin-tags',
            action='store_true',
            help='Procesar solo lugares que no tienen etiquetas',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Número de lugares a procesar por lote (default: 100)',
        )
        parser.add_argument(
            '--destacados',
            action='store_true',
            help='Procesar solo lugares destacados',
        )

    def _traducir_tipo(self, tipo):
        """Traduce tipos comunes a español y elimina redundancias."""
        traducciones = {
            'restaurant': 'restaurante',
            'pizza_restaurant': 'pizzería',
            'bar_and_grill': 'bar y parrilla',
            'fast_food_restaurant': 'comida rápida',
            'cafe': 'café',
            'night_club': 'discoteca',
            'bar': 'bar',
            'food': None,  # ignorar
            'point_of_interest': None,  # ignorar
            'establishment': None,  # ignorar
            'meal_takeaway': None,  # ignorar
            'meal_delivery': None,  # ignorar
            'food_delivery': None,  # ignorar
        }
        
        # Eliminar sufijo '_restaurant' si existe
        base_tipo = tipo.replace('_restaurant', '')
        
        # Si hay una traducción específica, usarla
        if tipo in traducciones:
            return traducciones[tipo]
        
        # Si no, convertir de snake_case a palabras en español
        return base_tipo.replace('_', ' ')

    def handle(self, *args, **options):
        if options['borrar'] and not options['dry_run']:
            self.stdout.write('Borrando etiquetas existentes...')
            Places.objects.all().update(tags=[])

        # Construir el queryset base
        qs = Places.objects.all()

        # Filtrar por ID específico o nombre si se proporciona
        if options['id']:
            qs = qs.filter(id=options['id'])
        elif options['nombre']:
            qs = qs.filter(nombre__icontains=options['nombre'])
        else:
            # Aplicar filtros adicionales solo si no se busca un lugar específico
            if options['desde_id']:
                qs = qs.filter(id__gte=options['desde_id'])
            
            if options['solo_sin_tags']:
                # Obtener lugares sin etiquetas
                qs = qs.annotate(num_tags=Count('tags')).filter(num_tags=0)
            
            if options['destacados']:
                # Filtrar solo lugares destacados
                qs = qs.filter(es_destacado=True)

        # Guardar el total antes de empezar
        total = qs.count()
        if total == 0:
            if options['id']:
                self.stdout.write(self.style.ERROR(f'No se encontró lugar con ID {options["id"]}'))
            elif options['nombre']:
                self.stdout.write(self.style.ERROR(f'No se encontró lugar con nombre que contenga "{options["nombre"]}"'))
            else:
                self.stdout.write(self.style.ERROR('No se encontraron lugares que cumplan los criterios'))
            return

        self.stdout.write(f'Se procesarán {total} lugares')
        
        # Procesar en lotes para mejor rendimiento
        batch_size = options['batch_size']
        procesados = 0
        
        # Guardar el último ID procesado en caché
        cache_key = 'ultimo_id_etiquetas'
        if options['destacados']:
            cache_key = 'ultimo_id_etiquetas_destacados'
            
        ultimo_id_procesado = cache.get(cache_key)
        if ultimo_id_procesado and not any([options['id'], options['nombre'], options['desde_id']]):
            self.stdout.write(f'Continuando desde el último ID procesado: {ultimo_id_procesado}')
            qs = qs.filter(id__gt=ultimo_id_procesado)

        for lugar in qs.iterator(chunk_size=batch_size):
            etiquetas = set()  # Usamos un set para evitar duplicados

            # Etiquetas basadas en accesibilidad
            if lugar.wheelchair_accessible_entrance:
                etiquetas.add('accesible en silla de ruedas')
            if lugar.wheelchair_accessible_parking:
                etiquetas.add('estacionamiento accesible')
            if lugar.wheelchair_accessible_restroom:
                etiquetas.add('baño accesible')

            # Etiquetas basadas en métodos de pago
            if lugar.accepts_credit_cards:
                etiquetas.add('acepta tarjetas de crédito')
            if lugar.accepts_debit_cards:
                etiquetas.add('acepta tarjetas de débito')
            if lugar.accepts_cash_only:
                etiquetas.add('solo efectivo')
            if lugar.accepts_nfc:
                etiquetas.add('pago sin contacto')

            # Etiquetas basadas en servicios de comida
            if lugar.takeout:
                etiquetas.add('para llevar')
            if lugar.dine_in:
                etiquetas.add('servicio en mesa')
            if lugar.delivery:
                etiquetas.add('delivery')

            # Etiquetas basadas en horarios de servicio
            if lugar.serves_breakfast:
                etiquetas.add('desayunos')
            if lugar.serves_lunch:
                etiquetas.add('almuerzos')
            if lugar.serves_dinner:
                etiquetas.add('cenas')
            if lugar.serves_brunch:
                etiquetas.add('brunch')

            # Etiquetas basadas en bebidas
            if lugar.serves_beer:
                etiquetas.add('cerveza')
            if lugar.serves_wine:
                etiquetas.add('vino')
            if lugar.serves_cocktails:
                etiquetas.add('cócteles')
            if lugar.serves_coffee:
                etiquetas.add('café')

            # Etiquetas basadas en características especiales
            if lugar.good_for_groups:
                etiquetas.add('bueno para grupos')
            if lugar.good_for_children:
                etiquetas.add('familiar')
            if lugar.outdoor_seating:
                etiquetas.add('terraza')
            if lugar.menu_for_children:
                etiquetas.add('menú infantil')
            if lugar.live_music:
                etiquetas.add('música en vivo')
            if lugar.allows_dogs:
                etiquetas.add('pet friendly')

            # Etiquetas basadas en el tipo de lugar
            if lugar.tipo:
                # Eliminar el sufijo '_restaurant' si existe
                tipo_base = lugar.tipo.replace('_restaurant', '')
                # Convertir snake_case a palabras
                tipo_palabras = tipo_base.replace('_', ' ')
                etiquetas.add(tipo_palabras)

            # Etiquetas basadas en precio
            if lugar.precio:
                niveles_precio = {
                    'PRICE_LEVEL_INEXPENSIVE': 'económico',
                    'PRICE_LEVEL_MODERATE': 'precio moderado',
                    'PRICE_LEVEL_EXPENSIVE': 'precio alto',
                    'PRICE_LEVEL_VERY_EXPENSIVE': 'precio muy alto'
                }
                precio_traducido = niveles_precio.get(lugar.precio)
                if precio_traducido:
                    etiquetas.add(precio_traducido)

            # Etiquetas basadas en rating
            if lugar.rating is not None:
                if lugar.rating >= 4.5:
                    etiquetas.add('excelente calificación')
                elif lugar.rating >= 4.0:
                    etiquetas.add('muy bien calificado')

            # Etiquetas basadas en estado destacado/exclusivo
            if lugar.es_destacado:
                etiquetas.add('destacado')
            if lugar.es_exclusivo:
                etiquetas.add('exclusivo')

            # Añadir etiquetas de Google Places API
            if lugar.types:
                for tipo in lugar.types:
                    tipo_traducido = self._traducir_tipo(tipo)
                    if tipo_traducido:
                        etiquetas.add(tipo_traducido)

            # En modo dry-run, solo mostrar las etiquetas
            if options['dry_run']:
                self.stdout.write(f'\nLugar: {lugar.nombre} (ID: {lugar.id})')
                self.stdout.write('Etiquetas que se generarían:')
                for etiqueta in sorted(etiquetas):
                    self.stdout.write(f'  - {etiqueta}')
            else:
                # Aplicar las etiquetas al lugar
                lugar.tags.set(etiquetas)
                self.stdout.write(f'Etiquetas aplicadas a: {lugar.nombre} (ID: {lugar.id})')
            
            procesados += 1
            if procesados % 50 == 0:
                self.stdout.write(f'Procesados {procesados} de {total} lugares...')
                # Guardar el progreso
                cache.set(cache_key, lugar.id, timeout=86400)  # 24 horas

        # Limpiar caché si se completó todo
        if not options['dry_run'] and procesados == total:
            cache.delete(cache_key)

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(
                f'\n¡Simulación completada! Se procesarían {total} lugares.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'¡Etiquetas generadas exitosamente para {total} lugares!'
            )) 