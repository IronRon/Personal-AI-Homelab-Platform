from django.urls import path

from . import views

urlpatterns = [
    path('', views.food_today, name='food_today'),
    path('catalogue/', views.catalogue, name='catalogue'),
    path('new/', views.food_item_create, name='food_item_create'),
    path('today/', views.food_today, name='food_today'),
    path('log/', views.consumption_create, name='consumption_create'),
    path('quick-add/', views.quick_add_consumption, name='quick_add_consumption'),
    path('history/', views.food_history, name='food_history'),
    path('cost-history/', views.food_cost_history, name='food_cost_history'),
    path('purchases/new/', views.food_purchase_create, name='food_purchase_create'),
    path('consumption/<int:pk>/edit/', views.consumption_edit, name='consumption_edit'),
    path('consumption/<int:pk>/delete/', views.consumption_delete, name='consumption_delete'),
    path('recipes/', views.recipe_list, name='recipe_list'),
    path('recipes/new/', views.recipe_create, name='recipe_create'),
    path('recipes/<int:pk>/', views.recipe_detail, name='recipe_detail'),
    path('recipes/<int:pk>/edit/', views.recipe_edit, name='recipe_edit'),
    path(
        'recipes/<int:recipe_pk>/ingredients/new/',
        views.recipe_ingredient_create,
        name='recipe_ingredient_create',
    ),
    path(
        'recipes/<int:recipe_pk>/ingredients/<int:pk>/edit/',
        views.recipe_ingredient_edit,
        name='recipe_ingredient_edit',
    ),
    path(
        'recipes/<int:recipe_pk>/ingredients/<int:pk>/delete/',
        views.recipe_ingredient_delete,
        name='recipe_ingredient_delete',
    ),
    path('batches/', views.meal_prep_list, name='meal_prep_list'),
    path('batches/new/', views.meal_prep_create, name='meal_prep_create'),
    path(
        'batches/<int:batch_pk>/consumption/new/',
        views.batch_consumption_create,
        name='batch_consumption_create',
    ),
    path('batches/<int:pk>/', views.meal_prep_detail, name='meal_prep_detail'),
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
