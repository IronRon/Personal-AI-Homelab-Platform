from django.contrib import admin

from .models import MediaAsset, VideoClip, VideoJob, VideoProject


class MediaAssetInline(admin.TabularInline):
    model = MediaAsset
    extra = 0
    readonly_fields = ('original_filename', 'relative_path', 'file_size_bytes', 'sha256', 'duration_seconds')


@admin.register(VideoProject)
class VideoProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'editing_style', 'target_duration_seconds', 'created_at')
    inlines = (MediaAssetInline,)


@admin.register(VideoClip)
class VideoClipAdmin(admin.ModelAdmin):
    list_display = ('project', 'title', 'start_seconds', 'end_seconds', 'included', 'position')
    list_filter = ('included',)


@admin.register(VideoJob)
class VideoJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'job_type', 'status', 'progress', 'created_at')
    list_filter = ('status', 'job_type')
