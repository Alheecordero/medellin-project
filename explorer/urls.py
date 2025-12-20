from django.urls import path
from django.utils.translation import pgettext_lazy
from . import views as views

app_name = 'explorer'

urlpatterns = [
    # Vistas principales
    path('', views.home, name='home'),
    # About: español y inglés con slugs separados
    # ES: /nosotros/        | EN: /en/nosotros/   (alias)
    path('nosotros/', views.about, name='about_es'),
    # EN principal: /en/about-us/
    path('about-us/', views.about, name='about'),
    path('semantic-search/', views.SemanticSearchView.as_view(), name='semantic_search_page'),
    path(pgettext_lazy('url', 'lugares/'), views.lugares_list, name='lugares_list'),
    path(pgettext_lazy('url', 'lugares/<slug:comuna_slug>/'), views.lugares_por_comuna, name='lugares_por_comuna'),
    path(pgettext_lazy('url', 'lugar/<slug:slug>/'), views.lugares_detail, name='lugares_detail'),
    # Nota: en español usamos "reseñas" y en inglés se traduce a "reviews" vía msgctxt "url"
    path(pgettext_lazy('url', 'lugar/<slug:slug>/reseñas/'), views.reviews_lugar, name='reviews_lugar'),
    
    # API endpoints
    path('api/filtros-ajax/', views.filtros_ajax_view, name='filtros_ajax'),
    # Near Me (geolocalización) - nombre ÚNICO (evita colisiones con endpoints por slug)
    path('api/lugares-cercanos/', views.lugares_cercanos_ajax_view, name='lugares_cercanos_near_me'),
    path('api/semantic-search/', views.semantic_search_ajax, name='semantic_search_ajax'),
    path('api/translate_review', views.translate_review_api, name='translate_review_api'),
    # path('api/lugar/<slug:slug>/reviews/', views.reviews_lugar_ajax, name='reviews_lugar_ajax'),  # No necesario con solo 5 reseñas
    
    # Progressive Loading AJAX endpoints
    path('api/lugares/<slug:slug>/cercanos/', views.lugares_cercanos_ajax, name='lugares_cercanos_ajax_slug'),
    path('api/lugares/<slug:slug>/similares/', views.lugares_similares_ajax, name='lugares_similares_ajax_slug'),
    path('api/lugares/<slug:slug>/comuna/', views.lugares_comuna_ajax, name='lugares_comuna_ajax_slug'),
]
