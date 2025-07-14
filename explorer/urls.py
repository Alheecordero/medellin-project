from django.urls import path
from . import views
from .views import *
from .views import home_modern_view
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from django.urls import reverse_lazy
from django.views.generic import TemplateView


app_name = "explorer"

urlpatterns = [
    path("", home_view, name="home"),  # Página principal
    path("lugar/<slug:slug>/reseñas/", LugarReviewsView.as_view(), name="reseñas_lugar"),  # lugar 

    path("mapa-lugares-medellin/", mapa_explorar, name="mapa_explorar_medellin"), #/mapa-lugares-medellin/ 
    path("registro/", registro_usuario, name="registro"),
    
    
    path("favorito/<int:pk>/", guardar_favorito, name="guardar_favorito"),
    path("favoritos/", mis_favoritos, name="mis_favoritos"),

    path("perfil/", perfil_usuario, name="perfil_usuario"),
    path("acerca/", acerca_de_view, name="acerca"),
   

    path("lugar/<slug:slug>/", LugaresDetailView.as_view(), name="lugares_detail"),
    path("lugares/", LugaresListView.as_view(), name="lugares_list"),
    path('comuna/<slug:slug>/', views.lugares_por_comuna_view, name='lugares_por_comuna'),
    path("eliminar-favorito/<int:pk>/", eliminar_favorito, name="eliminar_favorito"),
    path('zonas-geojson/', zonas_geojson, name='zonas_geojson'),
    path('mapa-zonas/', mapa_zonas, name='mapa_zonas'),
    path('ajax/autocomplete-places/', views.autocomplete_places_view, name='autocomplete_places'),
    
]
