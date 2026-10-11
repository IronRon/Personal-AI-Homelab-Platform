from django.urls import path

from . import views

urlpatterns = [
    path('', views.food_home, name='food_home'),
]
