from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ImportAssetForm, SyncOffsetForm, VideoClipForm, VideoProjectForm
from .models import MediaAsset, VideoJob, VideoProject
from .services.jobs import enqueue_render
from .services.media import import_from_inbox, list_inbox_files, storage_root


def project_list(request):
    projects = VideoProject.objects.prefetch_related('assets', 'clips', 'jobs')
    return render(request, 'video_editor/project_list.html', {'projects': projects})


def project_create(request):
    if request.method == 'POST':
        form = VideoProjectForm(request.POST)
        if form.is_valid():
            project = form.save()
            messages.success(request, 'Video project created. Copy your recordings into the video inbox to import them.')
            return redirect('video_project_detail', project_id=project.pk)
    else:
        form = VideoProjectForm()
    return render(request, 'video_editor/project_form.html', {'form': form})


def project_detail(request, project_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    inbox_files = list_inbox_files()
    import_form = ImportAssetForm(available_files=inbox_files)
    sync_form = SyncOffsetForm(initial={'facecam_sync_offset_ms': project.facecam_sync_offset_ms})
    clip_form = VideoClipForm(project=project)
    return render(request, 'video_editor/project_detail.html', {
        'project': project,
        'inbox_files': inbox_files,
        'import_form': import_form,
        'sync_form': sync_form,
        'clip_form': clip_form,
        'jobs': project.jobs.all()[:10],
        'gameplay_assets': project.assets.filter(role=MediaAsset.GAMEPLAY),
        'facecam_assets': project.assets.filter(role=MediaAsset.FACECAM),
        'other_assets': project.assets.exclude(role__in=(MediaAsset.GAMEPLAY, MediaAsset.FACECAM)),
        'included_duration': project.clips.filter(included=True).aggregate(
            total=Sum(ExpressionWrapper(F('end_seconds') - F('start_seconds'), output_field=DecimalField(max_digits=12, decimal_places=3)))
        )['total'] or 0,
    })


@require_POST
def import_asset(request, project_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    files = list_inbox_files()
    form = ImportAssetForm(request.POST, available_files=files)
    if form.is_valid():
        try:
            asset = import_from_inbox(
                project,
                form.cleaned_data['inbox_filename'],
                form.cleaned_data['role'],
            )
            messages.success(request, f'Imported {asset.original_filename} ({asset.get_role_display()}).')
        except Exception as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, 'Choose a supported recording and its role.')
    return redirect('video_project_detail', project_id=project.pk)


@require_POST
def update_sync(request, project_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    form = SyncOffsetForm(request.POST)
    if form.is_valid():
        project.facecam_sync_offset_ms = form.cleaned_data['facecam_sync_offset_ms']
        project.save(update_fields=['facecam_sync_offset_ms', 'updated_at'])
        messages.success(request, 'Facecam synchronisation offset saved.')
    else:
        messages.error(request, 'Enter a valid synchronisation offset in milliseconds.')
    return redirect('video_project_detail', project_id=project.pk)


@require_POST
def add_clip(request, project_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    form = VideoClipForm(request.POST, project=project)
    if form.is_valid():
        clip = form.save(commit=False)
        clip.project = project
        clip.position = project.clips.count()
        clip.save()
        messages.success(request, f'Added clip: {clip}.')
    else:
        messages.error(request, 'Could not add clip. Check the selected recording and timestamps.')
    return redirect('video_project_detail', project_id=project.pk)


@require_POST
def toggle_clip(request, project_id, clip_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    clip = get_object_or_404(project.clips, pk=clip_id)
    clip.included = not clip.included
    clip.save(update_fields=['included'])
    return redirect('video_project_detail', project_id=project.pk)


@require_POST
def delete_clip(request, project_id, clip_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    clip = get_object_or_404(project.clips, pk=clip_id)
    clip.delete()
    for index, remaining in enumerate(project.clips.order_by('position', 'id')):
        if remaining.position != index:
            remaining.position = index
            remaining.save(update_fields=['position'])
    messages.success(request, 'Clip removed from the edit. The source recording was not changed.')
    return redirect('video_project_detail', project_id=project.pk)


@require_POST
def render_project(request, project_id):
    project = get_object_or_404(VideoProject, pk=project_id)
    if not project.clips.filter(included=True).exists():
        messages.error(request, 'Add at least one included clip before rendering.')
    elif project.jobs.filter(status__in=(VideoJob.QUEUED, VideoJob.RUNNING)).exists():
        messages.warning(request, 'This project already has a render queued or running.')
    else:
        job = enqueue_render(project)
        messages.success(request, f'Render job #{job.pk} queued. Start the video worker in a second terminal.')
    return redirect('video_project_detail', project_id=project.pk)


def download_render(request, job_id):
    job = get_object_or_404(VideoJob, pk=job_id, status=VideoJob.COMPLETED)
    root = storage_root()
    path = (root / job.output_relative_path).resolve()
    if root not in path.parents or not path.is_file():
        raise Http404('The rendered video file could not be found.')
    return FileResponse(path.open('rb'), as_attachment=True, filename=Path(path).name)
