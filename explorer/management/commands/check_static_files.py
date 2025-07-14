from django.core.management.base import BaseCommand
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Verifica la configuración de archivos estáticos'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== CONFIGURACIÓN DE ARCHIVOS ESTÁTICOS ==='))
        
        # Configuración básica
        self.stdout.write(f'DEBUG: {settings.DEBUG}')
        self.stdout.write(f'STATIC_URL: {settings.STATIC_URL}')
        self.stdout.write(f'STATIC_ROOT: {settings.STATIC_ROOT}')
        
        # STATICFILES_DIRS
        if hasattr(settings, 'STATICFILES_DIRS'):
            self.stdout.write(f'STATICFILES_DIRS:')
            for dir in settings.STATICFILES_DIRS:
                exists = os.path.exists(dir)
                status = self.style.SUCCESS('✓') if exists else self.style.ERROR('✗')
                self.stdout.write(f'  {status} {dir}')
        else:
            self.stdout.write(self.style.WARNING('STATICFILES_DIRS no está configurado'))
        
        # Storage backend
        self.stdout.write(f'\nSTATICFILES_STORAGE: {settings.STATICFILES_STORAGE}')
        self.stdout.write(f'USE_GCS: {getattr(settings, "USE_GCS", False)}')
        
        # Verificar archivos estáticos específicos
        self.stdout.write('\n=== ARCHIVOS ESTÁTICOS CLAVE ===')
        test_files = [
            'css/style.css',
            'css/modern-style.css',
            'js/optimizations.js',
        ]
        
        for file in test_files:
            # Buscar en STATICFILES_DIRS
            found = False
            if hasattr(settings, 'STATICFILES_DIRS'):
                for static_dir in settings.STATICFILES_DIRS:
                    file_path = os.path.join(static_dir, file)
                    if os.path.exists(file_path):
                        found = True
                        self.stdout.write(f'{self.style.SUCCESS("✓")} {file} encontrado en {static_dir}')
                        break
            
            # Buscar en STATIC_ROOT
            if not found and settings.STATIC_ROOT:
                file_path = os.path.join(settings.STATIC_ROOT, file)
                if os.path.exists(file_path):
                    found = True
                    self.stdout.write(f'{self.style.SUCCESS("✓")} {file} encontrado en STATIC_ROOT')
            
            if not found:
                self.stdout.write(f'{self.style.ERROR("✗")} {file} NO ENCONTRADO')
        
        # Verificar si se ejecutó collectstatic
        if settings.STATIC_ROOT and os.path.exists(settings.STATIC_ROOT):
            file_count = sum(len(files) for _, _, files in os.walk(settings.STATIC_ROOT))
            self.stdout.write(f'\nArchivos en STATIC_ROOT: {file_count}')
        else:
            self.stdout.write(self.style.WARNING('\nSTATIC_ROOT no existe o está vacío'))
        
        self.stdout.write(self.style.SUCCESS('\n=== FIN DEL DIAGNÓSTICO ===')) 