from django.db import transaction
from django.utils import timezone

from apps.video_editor.models import VideoJob
from .render import render_job


def enqueue_render(project):
    return VideoJob.objects.create(project=project, job_type=VideoJob.RENDER)


def run_next_job():
    with transaction.atomic():
        job = (
            VideoJob.objects.select_for_update()
            .filter(status=VideoJob.QUEUED)
            .order_by('created_at')
            .first()
        )
        if job is None:
            return False
        job.status = VideoJob.RUNNING
        job.progress = 1
        job.message = 'Starting render'
        job.started_at = timezone.now()
        job.save(update_fields=['status', 'progress', 'message', 'started_at'])
        job_id = job.pk

    try:
        render_job(job_id)
    except Exception as exc:
        job = VideoJob.objects.get(pk=job_id)
        job.status = VideoJob.FAILED
        job.message = 'Render failed.'
        job.error_message = str(exc)[:10000]
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'message', 'error_message', 'completed_at'])
    return True
