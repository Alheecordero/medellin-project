import os
import sys
import django

# Configurar Django antes de importar cualquier modelo
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Medellin.settings_test")
django.setup()

import unittest
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser

# Importar modelos y vistas
from explorer.models import Places
from explorer.views_new import (
    home, lugares_list, lugares_detail, reviews_lugar,
    HomeView, PlacesListView, PlaceDetailView, PlaceReviewsView,
    BasePlacesMixin, SearchMixin, CacheMixin
)

class ViewsTestCase(TestCase):
    """Pruebas para las vistas y su lógica básica."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        
        # Verificar si hay lugares en la base de datos
        cls.has_places = Places.objects.exists()
        if cls.has_places:
            cls.test_place = Places.objects.first()
            print(f"Usando lugar existente para pruebas: {cls.test_place.nombre} (slug: {cls.test_place.slug})")
        else:
            print("ADVERTENCIA: No hay lugares en la base de datos. Algunas pruebas serán omitidas.")

    def test_home_view(self):
        """Prueba la vista home."""
        print("\n--- Probando vista home ---")
        
        # Prueba con función basada en vistas
        request = self.factory.get('/')
        request.user = AnonymousUser()
        response_func = home(request)
        self.assertEqual(response_func.status_code, 200)
        print("✅ Vista home (función) devuelve código 200")
        
        # Prueba con vista basada en clases
        response_class = HomeView.as_view()(request)
        self.assertEqual(response_class.status_code, 200)
        print("✅ Vista home (clase) devuelve código 200")

    def test_lugares_list_view(self):
        """Prueba la vista lugares_list."""
        print("\n--- Probando vista lugares_list ---")
        
        # Prueba con función basada en vistas
        request = self.factory.get('/lugares/')
        request.user = AnonymousUser()
        response_func = lugares_list(request)
        self.assertEqual(response_func.status_code, 200)
        print("✅ Vista lugares_list (función) devuelve código 200")
        
        # Prueba con vista basada en clases
        response_class = PlacesListView.as_view()(request)
        self.assertEqual(response_class.status_code, 200)
        print("✅ Vista lugares_list (clase) devuelve código 200")
        
        # Probar búsqueda
        if self.has_places:
            search_term = self.test_place.nombre[:5]  # Usar primeras 5 letras del nombre
            request_search = self.factory.get(f'/lugares/?q={search_term}')
            request_search.user = AnonymousUser()
            response_search = lugares_list(request_search)
            self.assertEqual(response_search.status_code, 200)
            print(f"✅ Búsqueda con término '{search_term}' funciona correctamente")

    def test_lugares_detail_view(self):
        """Prueba la vista lugares_detail."""
        if not self.has_places:
            print("\n--- Omitiendo prueba de lugares_detail (no hay lugares) ---")
            return
            
        print(f"\n--- Probando vista lugares_detail para '{self.test_place.nombre}' ---")
        
        # Prueba con función basada en vistas
        request = self.factory.get(f'/lugar/{self.test_place.slug}/')
        request.user = AnonymousUser()
        response_func = lugares_detail(request, slug=self.test_place.slug)
        self.assertEqual(response_func.status_code, 200)
        print("✅ Vista lugares_detail (función) devuelve código 200")
        
        # Prueba con vista basada en clases
        response_class = PlaceDetailView.as_view()(request, slug=self.test_place.slug)
        self.assertEqual(response_class.status_code, 200)
        print("✅ Vista lugares_detail (clase) devuelve código 200")

    def test_reviews_lugar_view(self):
        """Prueba la vista reviews_lugar."""
        if not self.has_places:
            print("\n--- Omitiendo prueba de reviews_lugar (no hay lugares) ---")
            return
            
        print(f"\n--- Probando vista reviews_lugar para '{self.test_place.nombre}' ---")
        
        # Prueba con función basada en vistas
        request = self.factory.get(f'/lugar/{self.test_place.slug}/reviews/')
        request.user = AnonymousUser()
        response_func = reviews_lugar(request, slug=self.test_place.slug)
        self.assertEqual(response_func.status_code, 200)
        print("✅ Vista reviews_lugar (función) devuelve código 200")
        
        # Prueba con vista basada en clases
        response_class = PlaceReviewsView.as_view()(request, slug=self.test_place.slug)
        self.assertEqual(response_class.status_code, 200)
        print("✅ Vista reviews_lugar (clase) devuelve código 200")

    def test_mixins(self):
        """Prueba que los mixins funcionan correctamente."""
        print("\n--- Probando mixins ---")
        
        # Probar CacheMixin
        request = self.factory.get('/')
        request.user = AnonymousUser()
        
        cache_mixin = CacheMixin()
        cache_mixin.request = request
        cache_key = cache_mixin.get_cache_key()
        self.assertTrue(isinstance(cache_key, str))
        print("✅ CacheMixin.get_cache_key() devuelve una clave válida")
        
        # Probar BasePlacesMixin
        base_mixin = BasePlacesMixin()
        queryset = base_mixin.get_base_queryset()
        self.assertEqual(queryset.model, Places)
        print("✅ BasePlacesMixin.get_base_queryset() devuelve un queryset de Places")
        
        # Probar SearchMixin
        search_mixin = SearchMixin()
        search_vector = search_mixin.get_search_vector()
        self.assertTrue(search_vector is not None)
        print("✅ SearchMixin.get_search_vector() devuelve un vector de búsqueda")

def run_tests():
    """Ejecuta todas las pruebas."""
    print("\n=== INICIANDO PRUEBAS DE VISTAS ===\n")
    
    # Crear una suite de pruebas y ejecutarla
    suite = unittest.TestLoader().loadTestsFromTestCase(ViewsTestCase)
    unittest.TextTestRunner().run(suite)
    
    print("\n=== PRUEBAS COMPLETADAS ===\n")

if __name__ == "__main__":
    run_tests() 