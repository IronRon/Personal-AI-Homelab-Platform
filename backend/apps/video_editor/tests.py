import hashlib
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import VideoClipForm
from .models import MediaAsset, VideoClip, VideoJob, VideoProject
from .services.media import import_from_inbox


class VideoProjectViewTests(TestCase):
    def test_project_list_loads(self):
        response = self.client.get(reverse('video_project_list'))
        self.assertEqual(response.status_code, 200)

    def test_create_project_redirects_to_detail(self):
        response = self.client.post(reverse('video_project_create'), {
            'name': 'Gaming highlights',
            'description': 'Test edit',
            'target_duration_seconds': 1800,
            'review_mode': VideoProject.REVIEW_BOTH,
        })
        self.assertEqual(response.status_code, 302)
        project = VideoProject.objects.get(name='Gaming highlights')
        self.assertEqual(response.url, reverse('video_project_detail', args=[project.pk]))

    def test_project_detail_shows_import_and_clip_sections(self):
        project = VideoProject.objects.create(name='Test project')
        response = self.client.get(reverse('video_project_detail', args=[project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Import recordings')
        self.assertContains(response, 'Build your highlight reel')

    def test_sync_offset_is_saved(self):
        project = VideoProject.objects.create(name='Sync test')
        response = self.client.post(reverse('video_update_sync', args=[project.pk]), {
            'facecam_sync_offset_ms': '1250',
        })
        self.assertEqual(response.status_code, 302)
        project.refresh_from_db()
        self.assertEqual(project.facecam_sync_offset_ms, 1250)


class VideoClipTests(TestCase):
    def setUp(self):
        self.project = VideoProject.objects.create(name='Clip test')
        self.asset = MediaAsset.objects.create(
            project=self.project,
            role=MediaAsset.GAMEPLAY,
            original_filename='gameplay.mp4',
            relative_path='projects/test/source/gameplay.mp4',
            sha256='a' * 64,
            duration_seconds=Decimal('600.000'),
            width=1920,
            height=1080,
        )

    def test_valid_clip_can_be_added(self):
        form = VideoClipForm({
            'gameplay_asset': self.asset.pk,
            'title': 'Good moment',
            'start_seconds': '125.500',
            'end_seconds': '148.000',
        }, project=self.project)
        self.assertTrue(form.is_valid(), form.errors)
        clip = form.save(commit=False)
        clip.project = self.project
        clip.save()
        self.assertEqual(clip.duration_seconds, Decimal('22.500'))

    def test_clip_end_must_be_after_start(self):
        form = VideoClipForm({
            'gameplay_asset': self.asset.pk,
            'title': 'Invalid',
            'start_seconds': '100',
            'end_seconds': '100',
        }, project=self.project)
        self.assertFalse(form.is_valid())
        self.assertIn('end_seconds', form.errors)

    def test_clip_cannot_exceed_source_duration(self):
        form = VideoClipForm({
            'gameplay_asset': self.asset.pk,
            'title': 'Too long',
            'start_seconds': '590',
            'end_seconds': '610',
        }, project=self.project)
        self.assertFalse(form.is_valid())
        self.assertIn('end_seconds', form.errors)

    def test_render_request_creates_queued_job(self):
        VideoClip.objects.create(
            project=self.project,
            gameplay_asset=self.asset,
            start_seconds=Decimal('10'),
            end_seconds=Decimal('20'),
        )
        response = self.client.post(reverse('video_render_project', args=[self.project.pk]))
        self.assertEqual(response.status_code, 302)
        job = VideoJob.objects.get(project=self.project)
        self.assertEqual(job.status, VideoJob.QUEUED)


class MediaImportTests(TestCase):
    def test_import_copies_file_and_records_probe_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'video_editor'
            inbox = root / 'inbox'
            inbox.mkdir(parents=True)
            source = inbox / 'sample.mp4'
            source.write_bytes(b'test video bytes')
            project = VideoProject.objects.create(name='Import test')
            with override_settings(VIDEO_EDITOR_STORAGE_ROOT=root, VIDEO_EDITOR_INBOX=inbox):
                with patch('apps.video_editor.services.media.probe_media', return_value={
                    'duration_seconds': Decimal('42.500'),
                    'width': 1920,
                    'height': 1080,
                    'frame_rate': '60/1',
                    'video_codec': 'h264',
                    'audio_codec': 'aac',
                }):
                    asset = import_from_inbox(project, 'sample.mp4', MediaAsset.GAMEPLAY)
                copied = root / asset.relative_path
                self.assertTrue(copied.is_file())
                self.assertEqual(copied.read_bytes(), source.read_bytes())
                self.assertEqual(asset.duration_seconds, Decimal('42.500'))
                self.assertEqual(asset.sha256, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_import_rejects_path_outside_inbox(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'video_editor'
            inbox = root / 'inbox'
            inbox.mkdir(parents=True)
            outside = Path(temp_dir) / 'outside.mp4'
            outside.write_bytes(b'not in inbox')
            project = VideoProject.objects.create(name='Path test')
            with override_settings(VIDEO_EDITOR_STORAGE_ROOT=root, VIDEO_EDITOR_INBOX=inbox):
                with self.assertRaises(Exception):
                    import_from_inbox(project, '../outside.mp4', MediaAsset.GAMEPLAY)
