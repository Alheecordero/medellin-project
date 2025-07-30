from django.core.management.base import BaseCommand
from storages.backends.gcloud import GoogleCloudStorage
from google.cloud import storage
from django.conf import settings


class Command(BaseCommand):
    help = 'Configura el bucket de Google Cloud Storage para permitir acceso público a imágenes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--bucket-name',
            type=str,
            default='vivemedellin-bucket',
            help='Nombre del bucket a configurar',
        )

    def handle(self, *args, **options):
        bucket_name = options['bucket_name']
        
        self.stdout.write(f"🚀 Configurando bucket: {bucket_name}")
        
        try:
            # Inicializar cliente de Google Cloud Storage
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            
            # Verificar que el bucket existe
            if not bucket.exists():
                self.stdout.write(self.style.ERROR(f"❌ El bucket {bucket_name} no existe"))
                return
            
            self.stdout.write(f"✅ Bucket encontrado: {bucket_name}")
            
            # Configurar política de acceso público para imágenes
            self.configurar_acceso_publico(bucket)
            
            # Configurar CORS si es necesario
            self.configurar_cors(bucket)
            
            self.stdout.write(self.style.SUCCESS("🎉 Configuración completada exitosamente"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error configurando bucket: {e}"))

    def configurar_acceso_publico(self, bucket):
        """Configura el bucket para permitir acceso público a las imágenes"""
        self.stdout.write("🔓 Configurando acceso público...")
        
        try:
            # Obtener política actual
            policy = bucket.get_iam_policy(requested_policy_version=3)
            
            # Agregar rol de lector público para el folder de imágenes
            policy.bindings.append({
                "role": "roles/storage.objectViewer",
                "members": {"allUsers"},
                "condition": {
                    "title": "Public access to images",
                    "description": "Allow public access to images folder",
                    "expression": "resource.name.startsWith('projects/_/buckets/{}/objects/images/')".format(bucket.name)
                }
            })
            
            # Aplicar la nueva política
            bucket.set_iam_policy(policy)
            
            self.stdout.write("✅ Acceso público configurado para la carpeta 'images/'")
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️  Error configurando acceso público: {e}"))
            self.stdout.write("💡 Puedes configurarlo manualmente desde la consola de Google Cloud")

    def configurar_cors(self, bucket):
        """Configura CORS para permitir acceso desde tu aplicación web"""
        self.stdout.write("🌐 Configurando CORS...")
        
        try:
            cors_configuration = [
                {
                    "origin": ["*"],
                    "method": ["GET"],
                    "responseHeader": ["Content-Type"],
                    "maxAgeSeconds": 3600
                }
            ]
            
            bucket.cors = cors_configuration
            bucket.patch()
            
            self.stdout.write("✅ CORS configurado correctamente")
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️  Error configurando CORS: {e}"))

    def mostrar_ejemplo_configuracion_manual(self):
        """Muestra instrucciones para configuración manual"""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("📋 CONFIGURACIÓN MANUAL (si es necesario):")
        self.stdout.write("="*60)
        self.stdout.write("1. Ve a Google Cloud Console")
        self.stdout.write("2. Navega a Storage > Browser")
        self.stdout.write("3. Selecciona tu bucket: vivemedellin-bucket")
        self.stdout.write("4. Ve a la pestaña 'Permissions'")
        self.stdout.write("5. Haz clic en 'Add members'")
        self.stdout.write("6. En 'New members' escribe: allUsers")
        self.stdout.write("7. En 'Role' selecciona: Storage Object Viewer")
        self.stdout.write("8. Agrega condición:")
        self.stdout.write("   - Tipo: resource.name")
        self.stdout.write("   - Operador: startsWith")
        self.stdout.write("   - Valor: projects/_/buckets/vivemedellin-bucket/objects/images/")
        self.stdout.write("9. Haz clic en 'Save'")
        self.stdout.write("="*60) 