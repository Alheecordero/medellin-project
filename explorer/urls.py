from django.urls import path
from . import views as views

app_name = 'explorer'

urlpatterns = [
    # Vistas principales
    path('', views.home, name='home'),
    path('semantic-search/', views.SemanticSearchView.as_view(), name='semantic_search_page'),
    path('lugares/', views.lugares_list, name='lugares_list'),
    path('lugares/<slug:comuna_slug>/', views.lugares_por_comuna, name='lugares_por_comuna'),
    path('lugar/<slug:slug>/', views.lugares_detail, name='lugares_detail'),
    path('lugar/<slug:slug>/reviews/', views.reviews_lugar, name='reviews_lugar'),
    
    # API endpoints
    path('api/filtros-ajax/', views.filtros_ajax_view, name='filtros_ajax'),
    path('api/lugares-cercanos/', views.lugares_cercanos_ajax_view, name='lugares_cercanos_ajax'),
    path('api/semantic-search/', views.semantic_search_ajax, name='semantic_search_ajax'),
    path('api/translate_review', views.translate_review_api, name='translate_review_api'),
    # path('api/lugar/<slug:slug>/reviews/', views.reviews_lugar_ajax, name='reviews_lugar_ajax'),  # No necesario con solo 5 reseñas
    
    # Newsletter endpoints
    path('api/newsletter/suscribir/', views.newsletter_subscribe, name='newsletter_subscribe'),
    path('newsletter/confirmar/<str:token>/', views.newsletter_confirm, name='newsletter_confirm'),
    path('newsletter/cancelar/<str:token>/', views.newsletter_unsubscribe, name='newsletter_unsubscribe'),
    path('api/newsletter/estadisticas/', views.newsletter_stats, name='newsletter_stats'),
    
    # Progressive Loading AJAX endpoints
    path('api/lugares/<slug:slug>/cercanos/', views.lugares_cercanos_ajax, name='lugares_cercanos_ajax'),
    path('api/lugares/<slug:slug>/similares/', views.lugares_similares_ajax, name='lugares_similares_ajax'),
    path('api/lugares/<slug:slug>/comuna/', views.lugares_comuna_ajax, name='lugares_comuna_ajax'),
]
