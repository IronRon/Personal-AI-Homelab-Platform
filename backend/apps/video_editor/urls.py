from django.urls import path

from . import views

urlpatterns = [
    path('', views.project_list, name='video_project_list'),
    path('new/', views.project_create, name='video_project_create'),
    path('<uuid:project_id>/', views.project_detail, name='video_project_detail'),
    path('<uuid:project_id>/import/', views.import_asset, name='video_import_asset'),
    path('<uuid:project_id>/sync/', views.update_sync, name='video_update_sync'),
    path('<uuid:project_id>/clips/add/', views.add_clip, name='video_add_clip'),
    path('<uuid:project_id>/clips/<int:clip_id>/toggle/', views.toggle_clip, name='video_toggle_clip'),
    path('<uuid:project_id>/clips/<int:clip_id>/delete/', views.delete_clip, name='video_delete_clip'),
    path('<uuid:project_id>/render/', views.render_project, name='video_render_project'),
    path('jobs/<int:job_id>/download/', views.download_render, name='video_download_render'),
]
