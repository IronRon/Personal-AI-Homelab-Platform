import uuid
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='VideoProject',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=160)),
                ('description', models.TextField(blank=True)),
                ('editing_style', models.CharField(default='highlights', max_length=30)),
                ('review_mode', models.CharField(choices=[('both', 'Manual approval and automatic selection'), ('manual', 'Manual approval'), ('automatic', 'Automatic selection')], default='both', max_length=20)),
                ('target_duration_seconds', models.PositiveIntegerField(default=1800)),
                ('facecam_sync_offset_ms', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ('-updated_at', '-created_at')},
        ),
        migrations.CreateModel(
            name='MediaAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('gameplay', 'Gameplay'), ('facecam', 'Facecam'), ('other', 'Other')], default='gameplay', max_length=20)),
                ('original_filename', models.CharField(max_length=255)),
                ('relative_path', models.CharField(max_length=500, unique=True)),
                ('file_size_bytes', models.BigIntegerField(default=0)),
                ('sha256', models.CharField(max_length=64)),
                ('duration_seconds', models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True)),
                ('width', models.PositiveIntegerField(blank=True, null=True)),
                ('height', models.PositiveIntegerField(blank=True, null=True)),
                ('frame_rate', models.CharField(blank=True, max_length=30)),
                ('video_codec', models.CharField(blank=True, max_length=80)),
                ('audio_codec', models.CharField(blank=True, max_length=80)),
                ('imported_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assets', to='video_editor.videoproject')),
            ],
            options={'ordering': ('role', 'original_filename')},
        ),
        migrations.CreateModel(
            name='VideoClip',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, max_length=160)),
                ('start_seconds', models.DecimalField(decimal_places=3, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('end_seconds', models.DecimalField(decimal_places=3, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('position', models.PositiveIntegerField(default=0)),
                ('included', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('gameplay_asset', models.ForeignKey(limit_choices_to={'role': 'gameplay'}, on_delete=django.db.models.deletion.PROTECT, related_name='clips', to='video_editor.mediaasset')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='clips', to='video_editor.videoproject')),
            ],
            options={'ordering': ('position', 'id')},
        ),
        migrations.CreateModel(
            name='VideoJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job_type', models.CharField(choices=[('render', 'Render highlight video')], default='render', max_length=30)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')], default='queued', max_length=20)),
                ('progress', models.PositiveSmallIntegerField(default=0)),
                ('message', models.CharField(blank=True, max_length=500)),
                ('output_relative_path', models.CharField(blank=True, max_length=500)),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='jobs', to='video_editor.videoproject')),
            ],
            options={'ordering': ('-created_at',)},
        ),
    ]
