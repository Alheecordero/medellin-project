import os
import sys
import django
from django.test import Client
from django.urls import reverse
from django.core.management import call_command
from django.conf import settings

# Configurar Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Medellin.settings")
django.setup()

# Añadir 'testserver' a ALLOWED_HOSTS
settings.ALLOWED_HOSTS.append('testserver')

def test_views():
    """Prueba las vistas principales para verificar que funcionan correctamente."""
    client = Client()
    
    print("\n=== INICIANDO PRUEBAS DE VISTAS ===\n")
    
    # Probar la vista home
    print("Probando vista home...")
    response = client.get(reverse('explorer:home'))
    if response.status_code == 200:
        print("✅ Vista home funciona correctamente (código 200)")
    else:
        print(f"❌ Error en vista home: código {response.status_code}")
        print(f"Error: {getattr(response, 'content', '')[:200]}")
    
    # Probar la vista de lista de lugares
    print("\nProbando vista lugares_list...")
    response = client.get(reverse('explorer:lugares_list'))
    if response.status_code == 200:
        print("✅ Vista lugares_list funciona correctamente (código 200)")
    else:
        print(f"❌ Error en vista lugares_list: código {response.status_code}")
        print(f"Error: {getattr(response, 'content', '')[:200]}")
    
    # Obtener un slug de lugar válido para probar el detalle
    from explorer.models import Places
    lugar = Places.objects.first()
    
    if lugar:
        # Probar la vista de detalle de lugar
        print(f"\nProbando vista lugares_detail con slug '{lugar.slug}'...")
        response = client.get(reverse('explorer:lugares_detail', kwargs={'slug': lugar.slug}))
        if response.status_code == 200:
            print("✅ Vista lugares_detail funciona correctamente (código 200)")
        else:
            print(f"❌ Error en vista lugares_detail: código {response.status_code}")
            print(f"Error: {getattr(response, 'content', '')[:200]}")
        
        # Probar la vista de reseñas de lugar
        print(f"\nProbando vista reviews_lugar con slug '{lugar.slug}'...")
        response = client.get(reverse('explorer:reviews_lugar', kwargs={'slug': lugar.slug}))
        if response.status_code == 200:
            print("✅ Vista reviews_lugar funciona correctamente (código 200)")
        else:
            print(f"❌ Error en vista reviews_lugar: código {response.status_code}")
            print(f"Error: {getattr(response, 'content', '')[:200]}")
    else:
        print("\n⚠️ No se encontraron lugares en la base de datos para probar las vistas de detalle y reseñas")
    
    print("\n=== PRUEBAS COMPLETADAS ===\n")

if __name__ == "__main__":
    test_views() 