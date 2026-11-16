import hashlib
import json
import shutil
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.video_editor.models import MediaAsset

SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v'}


def storage_root():
    return Path(settings.VIDEO_EDITOR_STORAGE_ROOT).resolve()


def inbox_path():
    path = Path(settings.VIDEO_EDITOR_INBOX).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_inbox_files():
    root = inbox_path()
    files = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
            files.append({
                'name': path.name,
                'size': path.stat().st_size,
                'size_label': _format_bytes(path.stat().st_size),
            })
    return files


def _format_bytes(value):
    size = float(value)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.1f} {unit}'
        size /= 1024


def _executable(setting_name, fallback):
    configured = getattr(settings, setting_name, fallback)
    found = shutil.which(str(configured)) if not Path(str(configured)).is_absolute() else str(configured)
    if not found or not Path(found).is_file():
        raise RuntimeError(f'{fallback} was not found. Install FFmpeg and configure {setting_name} if needed.')
    return found


def probe_media(path):
    executable = _executable('FFPROBE_PATH', 'ffprobe')
    command = [
        executable, '-v', 'error', '-show_entries',
        'format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate',
        '-of', 'json', str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('FFprobe timed out while inspecting this recording.') from exc
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-1500:] or 'FFprobe could not read this recording.')
    try:
        data = json.loads(result.stdout)
        duration = Decimal(str(data.get('format', {}).get('duration', '0')))
    except (json.JSONDecodeError, InvalidOperation, TypeError) as exc:
        raise RuntimeError('FFprobe returned invalid media metadata.') from exc
    if duration <= 0:
        raise RuntimeError('The selected file does not contain a valid video duration.')
    video = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), {})
    audio = next((s for s in data.get('streams', []) if s.get('codec_type') == 'audio'), {})
    return {
        'duration_seconds': duration.quantize(Decimal('0.001')),
        'width': video.get('width'),
        'height': video.get('height'),
        'frame_rate': str(video.get('avg_frame_rate') or ''),
        'video_codec': str(video.get('codec_name') or ''),
        'audio_codec': str(audio.get('codec_name') or ''),
    }


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def import_from_inbox(project, filename, role):
    root = inbox_path()
    candidate = (root / filename).resolve()
    if candidate.parent != root or not candidate.is_file():
        raise ValidationError('The selected recording is not available in the video inbox.')
    if candidate.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        raise ValidationError('This video file extension is not supported.')

    project_root = storage_root() / 'projects' / str(project.pk)
    source_dir = project_root / 'source'
    source_dir.mkdir(parents=True, exist_ok=True)
    destination = source_dir / candidate.name
    if destination.exists():
        raise ValidationError('A file with this name has already been imported into this project.')

    free_bytes = shutil.disk_usage(project_root).free
    if free_bytes < candidate.stat().st_size * 1.05:
        raise ValidationError('There is not enough free disk space to copy this recording.')

    staging = destination.with_name(destination.name + '.importing')
    try:
        shutil.copy2(candidate, staging)
        source_hash = _sha256(candidate)
        copied_hash = _sha256(staging)
        if source_hash != copied_hash:
            raise RuntimeError('The copied recording failed its SHA-256 verification.')
        metadata = probe_media(staging)
        staging.replace(destination)
    except Exception:
        staging.unlink(missing_ok=True)
        raise

    relative_path = destination.relative_to(storage_root()).as_posix()
    return MediaAsset.objects.create(
        project=project,
        role=role,
        original_filename=candidate.name,
        relative_path=relative_path,
        file_size_bytes=destination.stat().st_size,
        sha256=source_hash,
        **metadata,
    )


def resolve_asset_path(asset):
    root = storage_root()
    path = (root / asset.relative_path).resolve()
    if root not in path.parents or not path.is_file():
        raise RuntimeError(f'Media file is missing or outside managed storage: {asset.original_filename}')
    return path
