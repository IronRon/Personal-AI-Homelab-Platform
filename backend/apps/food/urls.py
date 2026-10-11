from django.urls import path

from . import views

urlpatterns = [
    path('', views.food_today, name='food_today'),
    path('catalogue/', views.catalogue, name='catalogue'),
    path('new/', views.food_item_create, name='food_item_create'),
    path('today/', views.food_today, name='food_today'),
    path('log/', views.consumption_create, name='consumption_create'),
    path('history/', views.food_history, name='food_history'),
    path('consumption/<int:pk>/edit/', views.consumption_edit, name='consumption_edit'),
    path('consumption/<int:pk>/delete/', views.consumption_delete, name='consumption_delete'),
    path('<int:pk>/', views.food_item_detail, name='food_item_detail'),
    path('<int:pk>/edit/', views.food_item_edit, name='food_item_edit'),
    path(
        '<int:food_item_pk>/prices/new/',
        views.price_observation_create,
        name='price_observation_create',
    ),
    path(
        '<int:food_item_pk>/prices/<int:pk>/edit/',
        views.price_observation_edit,
        name='price_observation_edit',
    ),
]
