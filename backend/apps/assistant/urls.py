from django.urls import path

from . import views

urlpatterns = [
    path("", views.chat_page, name="assistant_chat"),
    path("api/chat/", views.chat_api, name="assistant_chat_api"),
    path("new/", views.new_conversation, name="assistant_new_conversation"),
    path("api/settings/", views.assistant_settings_api, name="assistant_settings_api"),
    path("api/food-action/confirm/", views.confirm_food_action, name="assistant_confirm_food_action"),
    path("api/food-action/cancel/", views.cancel_food_action, name="assistant_cancel_food_action"),
]
