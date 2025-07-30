from django.core.management.base import BaseCommand
from django.utils.text import slugify
from explorer.models import RegionOSM


class Command(BaseCommand):
    help = 'Genera slugs únicos para todas las regiones OSM'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué slugs se generarían sin actualizar la base de datos',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.SUCCESS('Generando slugs para regiones OSM...')
        )
        
        regiones = RegionOSM.objects.all().order_by('name')
        slugs_generados = {}
        contador_duplicados = {}
        
        for region in regiones:
            if not region.name:
                self.stdout.write(
                    self.style.WARNING(f'Región {region.osm_id} sin nombre, omitiendo...')
                )
                continue
            
            # Generar slug base
            slug_base = slugify(region.name)
            slug_final = slug_base
            
            # Manejar duplicados
            if slug_base in contador_duplicados:
                contador_duplicados[slug_base] += 1
                slug_final = f"{slug_base}-{contador_duplicados[slug_base]}"
            else:
                contador_duplicados[slug_base] = 0
            
            slugs_generados[region.osm_id] = {
                'region': region,
                'slug': slug_final,
                'nombre': region.name
            }
            
            self.stdout.write(
                f'  {region.name} -> {slug_final}'
            )
        
        if not dry_run:
            # Actualizar las regiones con slugs únicos
            actualizadas = 0
            for osm_id, info in slugs_generados.items():
                region = info['region']
                slug_final = info['slug']
                
                # Solo actualizar si no tiene slug o es diferente
                if not region.slug or region.slug != slug_final:
                    region.slug = slug_final
                    region.save()
                    actualizadas += 1
            
            self.stdout.write(
                self.style.SUCCESS(f'\n✅ Slugs actualizados para {actualizadas} regiones de {len(slugs_generados)} totales.')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'\nModo dry-run: Se actualizarían slugs para {len(slugs_generados)} regiones.')
            )
        
        # Verificar duplicados potenciales
        slugs_duplicados = {}
        for info in slugs_generados.values():
            slug = info['slug']
            if slug in slugs_duplicados:
                slugs_duplicados[slug].append(info['nombre'])
            else:
                slugs_duplicados[slug] = [info['nombre']]
        
        duplicados_encontrados = {k: v for k, v in slugs_duplicados.items() if len(v) > 1}
        
        if duplicados_encontrados:
            self.stdout.write(
                self.style.WARNING('\nADVERTENCIA: Se encontraron nombres que generarían slugs duplicados:')
            )
            for slug, nombres in duplicados_encontrados.items():
                self.stdout.write(f'  {slug}: {", ".join(nombres)}')
                
            self.stdout.write(
                '\nEsto se maneja automáticamente agregando números al final del slug.'
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('\nNo se encontraron conflictos de slugs.')
            ) 