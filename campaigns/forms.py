from django import forms
from .models import Campaign
from django.utils.text import slugify
from leadership.models import LGA, Ward


class LGAModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.name

class WardModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.name

class ArticleForm(forms.ModelForm):
    """CMS form for creating/editing KPN Newsroom articles."""

    title = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'id': 'article-title',
            'placeholder': 'Article headline...',
            'class': 'w-full text-3xl font-bold border-0 border-b-2 border-gray-200 '
                     'dark:border-gray-600 bg-transparent focus:outline-none '
                     'focus:border-kpn-green dark:text-white py-3 mb-2',
            'autocomplete': 'off',
        })
    )

    subheadline = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={
            'id': 'article-subheadline',
            'placeholder': 'Short deck / subheadline (optional)...',
            'class': 'w-full text-lg border-0 border-b border-gray-100 '
                     'dark:border-gray-700 bg-transparent focus:outline-none '
                     'focus:border-kpn-blue dark:text-gray-300 py-2 mb-4',
        })
    )

    category = forms.ChoiceField(
        choices=Campaign.CATEGORY_CHOICES,
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border border-gray-300 dark:border-gray-600 '
                     'bg-white dark:bg-gray-700 text-gray-900 dark:text-white '
                     'px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-kpn-green',
        })
    )

    verification_status = forms.ChoiceField(
        choices=Campaign.VERIFICATION_STATUS_CHOICES,
        initial='DEVELOPING',
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border border-gray-300 dark:border-gray-600 '
                     'bg-white dark:bg-gray-700 text-gray-900 dark:text-white '
                     'px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-kpn-green',
        })
    )

    reporter_credit = forms.ChoiceField(
        choices=Campaign.REPORTER_CREDIT_CHOICES,
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border border-gray-300 dark:border-gray-600 '
                     'bg-white dark:bg-gray-700 text-gray-900 dark:text-white '
                     'px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-kpn-green',
        })
    )

    lga = LGAModelChoiceField(
        queryset=LGA.objects.all().select_related('zone').order_by('name'),
        required=False,
        empty_label='— Select LGA —',
        widget=forms.Select(attrs={
            'id': 'id_lga',
            'class': 'block w-full rounded-md border border-gray-300 dark:border-gray-600 '
                     'bg-white dark:bg-gray-700 text-gray-900 dark:text-white '
                     'px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-kpn-green',
        })
    )

    ward = WardModelChoiceField(
        queryset=Ward.objects.none(),
        required=False,
        empty_label='— Select Ward (optional) —',
        widget=forms.Select(attrs={
            'id': 'id_ward',
            'class': 'block w-full rounded-md border border-gray-300 dark:border-gray-600 '
                     'bg-white dark:bg-gray-700 text-gray-900 dark:text-white '
                     'px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-kpn-green',
        })
    )

    location = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Birnin Kebbi, Argungu, Zuru...',
            'class': 'block w-full rounded-md border border-gray-300 dark:border-gray-600 '
                     'bg-white dark:bg-gray-700 text-gray-900 dark:text-white '
                     'px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-kpn-green',
        })
    )

    featured_image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'id': 'id_featured_image',
            'accept': 'image/*',
            'class': 'hidden',
        })
    )

    meta_description = forms.CharField(
        max_length=160,
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'maxlength': 160,
            'placeholder': 'Brief summary for search engines (max 160 characters)...',
            'class': 'block w-full rounded-md border border-gray-300 dark:border-gray-600 '
                     'bg-white dark:bg-gray-700 text-gray-900 dark:text-white '
                     'px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-kpn-green',
        })
    )

    # Hidden field — populated by Editor.js on form submit
    content_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'content-json-field'})
    )

    class Meta:
        model = Campaign
        fields = [
            'title', 'subheadline', 'category', 'verification_status',
            'reporter_credit', 'lga', 'ward', 'location',
            'featured_image', 'meta_description', 'content_json',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate ward queryset when editing an existing article
        if self.instance and self.instance.pk and self.instance.lga_id:
            self.fields['ward'].queryset = Ward.objects.filter(
                lga=self.instance.lga
            ).order_by('name')
        # If POST data has an lga, populate wards for it
        elif 'lga' in (self.data or {}):
            try:
                lga_id = int(self.data.get('lga'))
                self.fields['ward'].queryset = Ward.objects.filter(
                    lga_id=lga_id
                ).order_by('name')
            except (ValueError, TypeError):
                pass

    def clean_content_json(self):
        import json
        raw = self.cleaned_data.get('content_json', '').strip()
        if not raw or raw == 'None' or raw == '{}':
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def save(self, commit=True):
        article = super().save(commit=False)

        # Auto-generate slug from title
        if not article.slug:
            base_slug = slugify(article.title)
            slug = base_slug
            counter = 1
            while Campaign.objects.filter(slug=slug).exclude(pk=article.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            article.slug = slug

        if commit:
            article.save()
        return article


# Keep old form as alias so nothing that imports CampaignForm breaks
CampaignForm = ArticleForm
