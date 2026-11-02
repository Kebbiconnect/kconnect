from django import forms

from campaigns.models import Campaign

from .models import (
    Claim, ConsentRecord, Correction, EvidenceRecord, Institution, Promise,
    PromiseUpdate, StoryProfile, StorySourceLink, StoryUpdate,
)
from .services import REDACTION_REASON_CATEGORIES

_INPUT = ('block w-full rounded-md border border-gray-300 dark:border-gray-600 '
          'bg-white dark:bg-gray-700 text-gray-900 dark:text-white px-3 py-2 '
          'text-sm focus:outline-none focus:ring-2 focus:ring-kpn-green')


class StoryProfileForm(forms.ModelForm):
    class Meta:
        model = StoryProfile
        fields = ['kind', 'why_it_matters', 'who_is_affected', 'what_is_unknown',
                  'what_to_watch',
                  # Phase 4 — Future Signal framing
                  'signal_observation', 'signal_confidence', 'signal_horizon',
                  'signal_change_condition', 'related_stories',
                  # Phase 4 — Human Impact framing
                  'features_identifiable_people', 'impact_story']
        widgets = {
            'kind': forms.Select(attrs={'class': _INPUT}),
            'why_it_matters': forms.Textarea(attrs={'class': _INPUT, 'rows': 3}),
            'who_is_affected': forms.Textarea(attrs={'class': _INPUT, 'rows': 3}),
            'what_is_unknown': forms.Textarea(attrs={'class': _INPUT, 'rows': 3}),
            'what_to_watch': forms.Textarea(attrs={'class': _INPUT, 'rows': 3}),
            'signal_observation': forms.Textarea(attrs={'class': _INPUT, 'rows': 3}),
            'signal_confidence': forms.Select(attrs={'class': _INPUT}),
            'signal_horizon': forms.TextInput(attrs={'class': _INPUT}),
            'signal_change_condition': forms.Textarea(attrs={'class': _INPUT, 'rows': 2}),
            'related_stories': forms.SelectMultiple(attrs={'class': _INPUT, 'size': 6}),
        }

    def __init__(self, *args, article=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['related_stories'].required = False
        # A signal analyses already-published stories, never itself.
        related = Campaign.objects.filter(status='PUBLISHED')
        if article is not None:
            related = related.exclude(pk=article.pk)
        self.fields['related_stories'].queryset = related.order_by('-published_at')
        self.fields['impact_story'].required = False


class StoryUpdateForm(forms.ModelForm):
    publish_now = forms.BooleanField(required=False, label='Publish immediately')

    class Meta:
        model = StoryUpdate
        fields = ['kind', 'title', 'body']
        widgets = {
            'kind': forms.Select(attrs={'class': _INPUT}),
            'title': forms.TextInput(attrs={'class': _INPUT}),
            'body': forms.Textarea(attrs={'class': _INPUT, 'rows': 4}),
        }


class ClaimForm(forms.ModelForm):
    class Meta:
        model = Claim
        fields = ['text', 'status', 'source_name', 'source_url']
        widgets = {
            'text': forms.Textarea(attrs={'class': _INPUT, 'rows': 3}),
            'status': forms.Select(attrs={'class': _INPUT}),
            'source_name': forms.TextInput(attrs={'class': _INPUT}),
            'source_url': forms.URLInput(attrs={'class': _INPUT}),
        }


class ClaimStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Claim.STATUS_CHOICES, widget=forms.Select(attrs={'class': _INPUT}))
    reason = forms.CharField(required=False, max_length=300, widget=forms.TextInput(attrs={'class': _INPUT}))


class EvidenceForm(forms.ModelForm):
    class Meta:
        model = EvidenceRecord
        fields = ['kind', 'title', 'url', 'file', 'description', 'is_public', 'claim']
        widgets = {
            'kind': forms.Select(attrs={'class': _INPUT}),
            'title': forms.TextInput(attrs={'class': _INPUT}),
            'url': forms.URLInput(attrs={'class': _INPUT}),
            'description': forms.Textarea(attrs={'class': _INPUT, 'rows': 2}),
            'claim': forms.Select(attrs={'class': _INPUT}),
        }

    def __init__(self, *args, article=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['claim'].required = False
        if article is not None:
            self.fields['claim'].queryset = Claim.objects.filter(article=article)


class CorrectionForm(forms.ModelForm):
    class Meta:
        model = Correction
        fields = ['kind', 'text', 'published', 'update', 'claim']
        widgets = {
            'kind': forms.Select(attrs={'class': _INPUT}),
            'text': forms.Textarea(attrs={'class': _INPUT, 'rows': 3}),
            'update': forms.Select(attrs={'class': _INPUT}),
            'claim': forms.Select(attrs={'class': _INPUT}),
        }

    def __init__(self, *args, article=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['update'].required = False
        self.fields['claim'].required = False
        if article is not None:
            self.fields['update'].queryset = StoryUpdate.objects.filter(article=article)
            self.fields['claim'].queryset = Claim.objects.filter(article=article)


class ConsentForm(forms.ModelForm):
    class Meta:
        model = ConsentRecord
        fields = ['subject_descriptor', 'consent_basis', 'notes']
        widgets = {
            'subject_descriptor': forms.TextInput(attrs={'class': _INPUT}),
            'consent_basis': forms.Select(attrs={'class': _INPUT}),
            'notes': forms.Textarea(attrs={'class': _INPUT, 'rows': 2}),
        }


class ArticleVerificationForm(forms.Form):
    verification_status = forms.ChoiceField(
        choices=Campaign.VERIFICATION_STATUS_CHOICES,
        widget=forms.Select(attrs={'class': _INPUT}))
    reason = forms.CharField(required=False, max_length=300, widget=forms.TextInput(attrs={'class': _INPUT}))


class RedactionForm(forms.Form):
    target_type = forms.ChoiceField(choices=[
        ('article', 'The article body'),
        ('update', 'A story update'),
        ('claim', 'A claim'),
        ('evidence', 'An evidence record'),
    ], widget=forms.Select(attrs={'class': _INPUT}))
    target_id = forms.IntegerField(widget=forms.NumberInput(attrs={'class': _INPUT}))
    reason_category = forms.ChoiceField(
        choices=REDACTION_REASON_CATEGORIES, widget=forms.Select(attrs={'class': _INPUT}))


# ─── Phase 2 forms ────────────────────────────────────────────────────────────

class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ['name', 'kind', 'contact_note', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': _INPUT}),
            'kind': forms.Select(attrs={'class': _INPUT}),
            'contact_note': forms.TextInput(attrs={'class': _INPUT}),
            'notes': forms.Textarea(attrs={'class': _INPUT, 'rows': 2}),
        }


class PromiseForm(forms.ModelForm):
    class Meta:
        model = Promise
        fields = ['institution', 'title', 'description', 'announced_by',
                  'announced_on', 'source_name', 'source_url', 'deadline',
                  'zone', 'lga', 'ward', 'stories', 'next_check_date']
        widgets = {
            'institution': forms.Select(attrs={'class': _INPUT}),
            'title': forms.TextInput(attrs={'class': _INPUT}),
            'description': forms.Textarea(attrs={'class': _INPUT, 'rows': 4}),
            'announced_by': forms.TextInput(attrs={'class': _INPUT}),
            'announced_on': forms.DateInput(attrs={'class': _INPUT, 'type': 'date'}),
            'source_name': forms.TextInput(attrs={'class': _INPUT}),
            'source_url': forms.URLInput(attrs={'class': _INPUT}),
            'deadline': forms.DateInput(attrs={'class': _INPUT, 'type': 'date'}),
            'zone': forms.Select(attrs={'class': _INPUT}),
            'lga': forms.Select(attrs={'class': _INPUT}),
            'ward': forms.Select(attrs={'class': _INPUT}),
            'stories': forms.SelectMultiple(attrs={'class': _INPUT, 'size': 6}),
            'next_check_date': forms.DateInput(attrs={'class': _INPUT, 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['stories'].required = False
        self.fields['stories'].queryset = Campaign.objects.filter(status='PUBLISHED')
        for name in ('zone', 'lga', 'ward', 'deadline', 'next_check_date',
                     'announced_by', 'source_name', 'source_url'):
            self.fields[name].required = False


class PromiseStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Promise.STATUS_CHOICES,
                               widget=forms.Select(attrs={'class': _INPUT}))
    note = forms.CharField(required=False, max_length=2000,
                           widget=forms.TextInput(attrs={'class': _INPUT}))


class PromiseUpdateForm(forms.ModelForm):
    new_status = forms.ChoiceField(
        required=False,
        choices=[('', 'No status change')] + list(Promise.STATUS_CHOICES),
        widget=forms.Select(attrs={'class': _INPUT}),
        help_text='Optionally move the promise to a new status with this update.')

    class Meta:
        model = PromiseUpdate
        fields = ['update_date', 'title', 'body', 'evidence_title', 'evidence_url']
        widgets = {
            'update_date': forms.DateInput(attrs={'class': _INPUT, 'type': 'date'}),
            'title': forms.TextInput(attrs={'class': _INPUT}),
            'body': forms.Textarea(attrs={'class': _INPUT, 'rows': 3}),
            'evidence_title': forms.TextInput(attrs={'class': _INPUT}),
            'evidence_url': forms.URLInput(attrs={'class': _INPUT}),
        }


class PromiseVerificationClaimForm(forms.ModelForm):
    class Meta:
        model = Promise
        fields = ['verification_claim']
        widgets = {'verification_claim': forms.Select(attrs={'class': _INPUT})}

    def __init__(self, *args, promise=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['verification_claim'].required = False
        if promise is not None:
            self.fields['verification_claim'].queryset = Claim.objects.filter(
                article__in=promise.stories.all())
        else:
            self.fields['verification_claim'].queryset = Claim.objects.none()


class LinkReportForm(forms.Form):
    report_id = forms.IntegerField(widget=forms.NumberInput(attrs={'class': _INPUT}))
    kind = forms.ChoiceField(choices=StorySourceLink.KIND_CHOICES,
                             widget=forms.Select(attrs={'class': _INPUT}))
