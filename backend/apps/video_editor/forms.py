from django import forms
from django.core.exceptions import ValidationError

from .models import MediaAsset, VideoClip, VideoProject


class VideoProjectForm(forms.ModelForm):
    class Meta:
        model = VideoProject
        fields = ('name', 'description', 'target_duration_seconds', 'review_mode')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'target_duration_seconds': forms.NumberInput(attrs={'min': 1, 'step': 1}),
        }


class ImportAssetForm(forms.Form):
    inbox_filename = forms.ChoiceField(label='Recording in inbox')
    role = forms.ChoiceField(choices=MediaAsset.ROLE_CHOICES, initial=MediaAsset.GAMEPLAY)

    def __init__(self, *args, available_files=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(item['name'], f"{item['name']} ({item['size_label']})") for item in (available_files or [])]
        self.fields['inbox_filename'].choices = choices
        if not choices:
            self.fields['inbox_filename'].choices = [('', 'No supported recordings found')]
            self.fields['inbox_filename'].disabled = True


class SyncOffsetForm(forms.Form):
    facecam_sync_offset_ms = forms.IntegerField(
        label='Facecam offset (milliseconds)',
        help_text='Positive = facecam starts later than gameplay. Negative = facecam starts earlier.',
        widget=forms.NumberInput(attrs={'step': 10}),
    )


class VideoClipForm(forms.ModelForm):
    class Meta:
        model = VideoClip
        fields = ('gameplay_asset', 'title', 'start_seconds', 'end_seconds')
        widgets = {
            'start_seconds': forms.NumberInput(attrs={'min': 0, 'step': '0.001', 'placeholder': 'e.g. 125.5'}),
            'end_seconds': forms.NumberInput(attrs={'min': 0, 'step': '0.001', 'placeholder': 'e.g. 148.0'}),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.fields['gameplay_asset'].queryset = (
            MediaAsset.objects.filter(project=project, role=MediaAsset.GAMEPLAY) if project else MediaAsset.objects.none()
        )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_seconds')
        end = cleaned.get('end_seconds')
        asset = cleaned.get('gameplay_asset')
        if start is not None and end is not None and end <= start:
            self.add_error('end_seconds', 'End time must be later than start time.')
        if asset and end is not None and asset.duration_seconds is not None and end > asset.duration_seconds:
            self.add_error('end_seconds', 'End time exceeds the recording duration.')
        if asset and self.project and asset.project_id != self.project.pk:
            self.add_error('gameplay_asset', 'Select a gameplay recording from this project.')
        return cleaned
