import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.video_editor.models import MediaAsset, VideoClip, VideoJob
from .media import resolve_asset_path, storage_root


def _ffmpeg_path():
    import shutil
    configured = getattr(settings, 'FFMPEG_PATH', 'ffmpeg')
    found = shutil.which(str(configured)) if not Path(str(configured)).is_absolute() else str(configured)
    if not found or not Path(found).is_file():
        raise RuntimeError('FFmpeg was not found. Install FFmpeg and add it to PATH.')
    return found


def _run(command):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or 'FFmpeg failed.')[-3000:])


def _render_one_clip(ffmpeg, clip, facecam, offset_seconds, output_path):
    gameplay_path = resolve_asset_path(clip.gameplay_asset)
    start = float(clip.start_seconds)
    end = float(clip.end_seconds)
    duration = end - start
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{start:.3f}', '-i', str(gameplay_path)]

    if facecam:
        facecam_path = resolve_asset_path(facecam)
        facecam_seek = max(0.0, start - offset_seconds)
        facecam_delay = max(0.0, offset_seconds - start)
        command += ['-ss', f'{facecam_seek:.3f}', '-i', str(facecam_path)]
        delay_expr = f'PTS-STARTPTS+{facecam_delay:.3f}/TB'
        filters = (
            '[0:v]fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,'
            'pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[base];'
            f'[1:v]setpts={delay_expr},scale=480:-2[cam];'
            '[base][cam]overlay=W-w-32:H-h-32:eof_action=repeat[v]'
        )
    else:
        filters = '[0:v]fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[v]'

    if not clip.gameplay_asset.audio_codec:
        silent_audio_index = 2 if facecam else 1
        command += ['-f', 'lavfi', '-t', f'{duration:.3f}', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000']

    command += ['-t', f'{duration:.3f}', '-filter_complex', filters, '-map', '[v]']
    if clip.gameplay_asset.audio_codec:
        command += ['-map', '0:a:0']
    else:
        command += ['-map', f'{silent_audio_index}:a:0']

    command += [
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-ac', '2', '-ar', '48000',
        '-movflags', '+faststart', str(output_path),
    ]
    _run(command)


def render_job(job_id):
    job = VideoJob.objects.select_related('project').get(pk=job_id)
    project = job.project
    clips = list(
        VideoClip.objects.filter(project=project, included=True)
        .select_related('gameplay_asset').order_by('position', 'id')
    )
    if not clips:
        raise RuntimeError('Add at least one included clip before rendering.')
    if any(clip.gameplay_asset.role != MediaAsset.GAMEPLAY for clip in clips):
        raise RuntimeError('Every selected clip must use a gameplay recording.')

    facecam = project.assets.filter(role=MediaAsset.FACECAM).order_by('-imported_at').first()
    offset_seconds = project.facecam_sync_offset_ms / 1000.0
    ffmpeg = _ffmpeg_path()
    project_root = storage_root() / 'projects' / str(project.pk)
    render_dir = project_root / 'renders'
    render_dir.mkdir(parents=True, exist_ok=True)
    output = render_dir / f'highlights-{job.pk}.mp4'

    with tempfile.TemporaryDirectory(prefix='video-render-', dir=str(project_root)) as temp_name:
        temp_dir = Path(temp_name)
        segments = []
        for index, clip in enumerate(clips, start=1):
            segment = temp_dir / f'segment-{index:04d}.mp4'
            job.message = f'Rendering clip {index} of {len(clips)}'
            job.progress = int((index - 1) / len(clips) * 90)
            job.save(update_fields=['message', 'progress'])
            _render_one_clip(ffmpeg, clip, facecam, offset_seconds, segment)
            segments.append(segment)

        concat_file = temp_dir / 'concat.txt'
        def concat_quote(path):
            return path.as_posix().replace('\\', '/').replace("'", "'\\\"'\\\"'")
        concat_file.write_text(''.join(f"file '{concat_quote(p)}'\n" for p in segments), encoding='utf-8')
        job.message = 'Joining rendered clips'
        job.progress = 95
        job.save(update_fields=['message', 'progress'])
        _run([
            ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'concat', '-safe', '0', '-i', str(concat_file),
            '-c', 'copy', '-movflags', '+faststart', str(output),
        ])

    relative = output.relative_to(storage_root()).as_posix()
    job.status = VideoJob.COMPLETED
    job.progress = 100
    job.message = 'Highlight video exported successfully.'
    job.output_relative_path = relative
    job.completed_at = timezone.now()
    job.save(update_fields=['status', 'progress', 'message', 'output_relative_path', 'completed_at'])
