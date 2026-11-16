import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class VideoProject(models.Model):
    HIGHLIGHTS = 'highlights'
    REVIEW_BOTH = 'both'
    REVIEW_MANUAL = 'manual'
    REVIEW_AUTOMATIC = 'automatic'
    REVIEW_CHOICES = (
        (REVIEW_BOTH, 'Manual approval and automatic selection'),
        (REVIEW_MANUAL, 'Manual approval'),
        (REVIEW_AUTOMATIC, 'Automatic selection'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    editing_style = models.CharField(max_length=30, default=HIGHLIGHTS)
    review_mode = models.CharField(max_length=20, choices=REVIEW_CHOICES, default=REVIEW_BOTH)
    target_duration_seconds = models.PositiveIntegerField(default=1800)
    facecam_sync_offset_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-updated_at', '-created_at')

    def __str__(self):
        return self.name


class MediaAsset(models.Model):
    GAMEPLAY = 'gameplay'
    FACECAM = 'facecam'
    OTHER = 'other'
    ROLE_CHOICES = (
        (GAMEPLAY, 'Gameplay'),
        (FACECAM, 'Facecam'),
        (OTHER, 'Other'),
    )

    project = models.ForeignKey(VideoProject, on_delete=models.CASCADE, related_name='assets')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=GAMEPLAY)
    original_filename = models.CharField(max_length=255)
    relative_path = models.CharField(max_length=500, unique=True)
    file_size_bytes = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    duration_seconds = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    frame_rate = models.CharField(max_length=30, blank=True)
    video_codec = models.CharField(max_length=80, blank=True)
    audio_codec = models.CharField(max_length=80, blank=True)
    imported_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ('role', 'original_filename')

    @property
    def filename(self):
        return Path(self.original_filename).name

    def __str__(self):
        return f'{self.get_role_display()}: {self.original_filename}'


class VideoClip(models.Model):
    project = models.ForeignKey(VideoProject, on_delete=models.CASCADE, related_name='clips')
    gameplay_asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.PROTECT,
        related_name='clips',
        limit_choices_to={'role': MediaAsset.GAMEPLAY},
    )
    title = models.CharField(max_length=160, blank=True)
    start_seconds = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
    end_seconds = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
    position = models.PositiveIntegerField(default=0)
    included = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ('position', 'id')

    @property
    def duration_seconds(self):
        return self.end_seconds - self.start_seconds

    def clean(self):
        errors = {}
        if self.start_seconds is not None and self.end_seconds is not None:
            if self.end_seconds <= self.start_seconds:
                errors['end_seconds'] = 'End time must be later than start time.'
            if self.gameplay_asset_id and self.gameplay_asset.duration_seconds is not None:
                if self.end_seconds > self.gameplay_asset.duration_seconds:
                    errors['end_seconds'] = 'End time exceeds the gameplay recording duration.'
        if self.gameplay_asset_id and self.gameplay_asset.role != MediaAsset.GAMEPLAY:
            errors['gameplay_asset'] = 'Selected media asset must be a gameplay recording.'
        if self.gameplay_asset_id and self.project_id and self.gameplay_asset.project_id != self.project_id:
            errors['gameplay_asset'] = 'Select a gameplay recording belonging to this project.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title or f'Clip {self.position + 1}'


class VideoJob(models.Model):
    RENDER = 'render'
    JOB_TYPES = ((RENDER, 'Render highlight video'),)
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    STATUS_CHOICES = (
        (QUEUED, 'Queued'),
        (RUNNING, 'Running'),
        (COMPLETED, 'Completed'),
        (FAILED, 'Failed'),
    )

    project = models.ForeignKey(VideoProject, on_delete=models.CASCADE, related_name='jobs')
    job_type = models.CharField(max_length=30, choices=JOB_TYPES, default=RENDER)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.CharField(max_length=500, blank=True)
    output_relative_path = models.CharField(max_length=500, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.get_job_type_display()} - {self.get_status_display()}'
