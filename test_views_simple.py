import os
import django
from django.test.client import RequestFactory
from django.urls import reverse
from django.conf import settings

# Configurar Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Medellin.settings_test")
django.setup()

# Importar vistas
from explorer.views_new import home, lugares_list, lugares_detail, reviews_lugar

def test_views_simple():
    """Prueba las vistas principales directamente sin renderizar las plantillas."""
    factory = RequestFactory()
    
    print("\n=== INICIANDO PRUEBAS DE VISTAS (MODO SIMPLE) ===\n")
    
    # Probar la vista home
    print("Probando vista home...")
    request = factory.get('/')
    try:
        response = home(request)
        print("✅ Vista home funciona sin errores")
    except Exception as e:
        print(f"❌ Error en vista home: {str(e)}")
    
    # Probar la vista lugares_list
    print("\nProbando vista lugares_list...")
    request = factory.get('/lugares/')
    try:
        response = lugares_list(request)
        print("✅ Vista lugares_list funciona sin errores")
    except Exception as e:
        print(f"❌ Error en vista lugares_list: {str(e)}")
    
    # Obtener un slug de lugar válido para probar el detalle
    from explorer.models import Places
    lugar = Places.objects.first()
    
    if lugar:
        # Probar la vista de detalle de lugar
        print(f"\nProbando vista lugares_detail con slug '{lugar.slug}'...")
        request = factory.get(f'/lugar/{lugar.slug}/')
        try:
            response = lugares_detail(request, slug=lugar.slug)
            print("✅ Vista lugares_detail funciona sin errores")
        except Exception as e:
            print(f"❌ Error en vista lugares_detail: {str(e)}")
        
        # Probar la vista de reseñas de lugar
        print(f"\nProbando vista reviews_lugar con slug '{lugar.slug}'...")
        request = factory.get(f'/lugar/{lugar.slug}/reviews/')
        try:
            response = reviews_lugar(request, slug=lugar.slug)
            print("✅ Vista reviews_lugar funciona sin errores")
        except Exception as e:
            print(f"❌ Error en vista reviews_lugar: {str(e)}")
    else:
        print("\n⚠️ No se encontraron lugares en la base de datos para probar las vistas de detalle y reseñas")
    
    print("\n=== PRUEBAS COMPLETADAS ===\n")

if __name__ == "__main__":
    test_views_simple() 