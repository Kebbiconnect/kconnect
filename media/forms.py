from django import forms
from .models import MediaItem


class OpinionUploadForm(forms.Form):
    """Form for uploading multiple media files (opinions) with captions"""
    caption = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'w-full p-3 border rounded dark:bg-gray-700',
            'placeholder': 'Add a caption for your media post...'
        }),
        label='Caption',
        required=True,
        max_length=500
    )


class MediaItemEditForm(forms.ModelForm):
    """Form for editing individual media items"""
    class Meta:
        model = MediaItem
        fields = ['title', 'description', 'media_type']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full p-3 border rounded dark:bg-gray-700'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'w-full p-3 border rounded dark:bg-gray-700'}),
            'media_type': forms.Select(attrs={'class': 'w-full p-3 border rounded dark:bg-gray-700'}),
<<<<<<< HEAD
      }
=======
        }
>>>>>>> dcc6e63 (Mupdate)
