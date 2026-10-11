from django.urls import path

from . import views

urlpatterns = [
    path('', views.catalogue, name='catalogue'),
    path('new/', views.food_item_create, name='food_item_create'),
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
