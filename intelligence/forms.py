from django import forms
from django.core.exceptions import ValidationError

from editorial.forms import SourceForm
from editorial.models import Source
from leadership.models import Ward
from story_intelligence.models import Institution, Promise

from .models import (
    PROJECT_CATEGORIES, PROJECT_STATUSES, Community, District, FieldReport,
    GeoAlias, IntelligenceCategory, Project, ProjectEvidence,
    ProjectMilestone,
)


class IntelligenceSourceForm(SourceForm):
    """editorial.Source with the intelligence monitoring fields (Doc 04 §3.1)."""

    class Meta(SourceForm.Meta):
        model = Source
        fields = SourceForm.Meta.fields + ['connector_kind', 'poll_interval_minutes', 'home_lga']

    def clean_poll_interval_minutes(self):
        value = self.cleaned_data.get('poll_interval_minutes')
        if value is None or not 5 <= value <= 1440:
            raise ValidationError('Use a poll interval between 5 and 1440 minutes.')
        return value


class GeoAliasForm(forms.ModelForm):
    class Meta:
        model = GeoAlias
        fields = ['alias', 'target_kind', 'lga', 'district', 'ward', 'community', 'geo_entity']


class DistrictForm(forms.ModelForm):
    class Meta:
        model = District
        fields = ['name']


class CommunityForm(forms.ModelForm):
    class Meta:
        model = Community
        fields = ['name', 'ward', 'district']

    def __init__(self, *args, lga=None, **kwargs):
        super().__init__(*args, **kwargs)
        if lga is not None:
            self.fields['ward'].queryset = lga.wards.all()
            self.fields['district'].queryset = District.objects.filter(lga=lga)


# ---------------------------------------------------------------------------
# Phase 5 — project tracker + promise candidate forms.
#
# Integrity rule carried into the forms: the documented-fact fields
# (contractor, contract amount, award/commencement/completion dates)
# are never required — a project is registered with only what a
# source states, and the rest stays blank rather than being filled
# in to satisfy a form.
# ---------------------------------------------------------------------------

class ProjectForm(forms.ModelForm):
    sector = forms.ChoiceField(
        choices=[('', 'Not classified yet')] + list(Promise.SECTOR_CHOICES),
        required=False)
    category = forms.ChoiceField(choices=list(PROJECT_CATEGORIES))

    class Meta:
        model = Project
        fields = ['title', 'description', 'sector', 'category',
                  'institution', 'lga', 'ward', 'district', 'community',
                  'contractor_name', 'contract_amount', 'award_date',
                  'commencement_date', 'expected_completion_date',
                  'assigned_officer', 'source_url']
        widgets = {
            'award_date': forms.DateInput(attrs={'type': 'date'}),
            'commencement_date': forms.DateInput(attrs={'type': 'date'}),
            'expected_completion_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('contractor_name', 'contract_amount', 'award_date',
                     'commencement_date', 'expected_completion_date'):
            self.fields[name].required = False
        lga = None
        if self.is_bound:
            raw = self.data.get('lga')
            if raw and str(raw).isdigit():
                from leadership.models import LGA
                lga = LGA.objects.filter(pk=int(raw)).first()
        elif self.instance and self.instance.pk:
            lga = self.instance.lga
        elif self.initial.get('lga'):
            from leadership.models import LGA
            lga = LGA.objects.filter(pk=self.initial['lga']).first()
        if lga is not None:
            self.fields['ward'].queryset = Ward.objects.filter(lga=lga)
            self.fields['district'].queryset = District.objects.filter(lga=lga)
            self.fields['community'].queryset = Community.objects.filter(lga=lga)


class ProjectStatusForm(forms.Form):
    status = forms.ChoiceField(choices=list(PROJECT_STATUSES))
    note = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}),
                           required=False)


class ProjectMilestoneForm(forms.ModelForm):
    class Meta:
        model = ProjectMilestone
        fields = ['date', 'title', 'body']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}


class ProjectEvidenceForm(forms.ModelForm):
    class Meta:
        model = ProjectEvidence
        fields = ['kind', 'title', 'url', 'file', 'captured_at',
                  'verification_state', 'is_public']
        widgets = {
            'captured_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class CandidateConfirmForm(forms.Form):
    """Confirm a promise candidate into a real Promise.

    The institution is chosen from the register or entered by name
    (created on confirm). The deadline is a real date field the
    editor fills ONLY when the stated phrase gives one — it is never
    pre-filled from the detector's phrase.
    """
    institution = forms.ModelChoiceField(
        queryset=Institution.objects.all(), required=False,
        empty_label='— Enter a new institution name below —')
    institution_name = forms.CharField(max_length=200, required=False)
    title = forms.CharField(max_length=250)
    description = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}))
    announced_by = forms.CharField(max_length=200, required=False)
    announced_on = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}))
    deadline = forms.DateField(
        required=False, widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Only if the statement itself announced a date.')
    sector = forms.ChoiceField(
        choices=[('', 'Not classified yet')] + list(Promise.SECTOR_CHOICES),
        required=False)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('institution') and not (
                cleaned.get('institution_name') or '').strip():
            raise ValidationError(
                'Choose the institution that made this commitment, or '
                'enter its name.')
        return cleaned


# ---------------------------------------------------------------------------
# Phase 6 — security desk, alert rules.
#
# The incident form deliberately has NO field for precise locations,
# coordinates, troop positions or vulnerable-person locations: the
# security path is located at LGA level only (blueprint §14). The
# claims form records a figure only together with the source that
# reported it.
# ---------------------------------------------------------------------------

from leadership.capabilities import ALL_CAPABILITIES  # noqa: E402

from .models import (  # noqa: E402
    ALERT_CHANNELS, AlertRule, IncidentClaim, SecurityIncident,
)


class SecurityIncidentForm(forms.ModelForm):
    class Meta:
        model = SecurityIncident
        fields = ['title', 'incident_type', 'occurred_at', 'lga',
                  'location_text', 'has_offline_detail', 'working_notes']
        widgets = {
            'occurred_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'working_notes': forms.Textarea(attrs={'rows': 5}),
        }


class IncidentClaimForm(forms.ModelForm):
    class Meta:
        model = IncidentClaim
        fields = ['label', 'count', 'source_name', 'source_url']


class FieldReportForm(forms.ModelForm):
    """The field-report form (Phase 7): plain server-rendered fields,
    no JavaScript dependency — built for weak connections."""

    class Meta:
        model = FieldReport
        fields = ['headline', 'report_text', 'lga', 'category',
                  'occurred_at', 'photo']
        widgets = {
            'report_text': forms.Textarea(attrs={'rows': 8}),
            'occurred_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}),
        }
        labels = {
            'report_text': 'What happened?',
            'lga': 'LGA',
            'occurred_at': 'When did it happen?',
            'photo': 'Photo evidence (optional)',
        }
        help_texts = {
            'lga': 'The LGA where this happened — you are recording '
                   'it first-hand.',
            'photo': 'One photo, if you have one. It is stored as '
                     'evidence and never published as-is.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from leadership.models import LGA
        self.fields['lga'].queryset = LGA.objects.select_related(
            'zone').order_by('name')
        self.fields['category'].queryset = IntelligenceCategory.objects \
            .order_by('label')
        self.fields['occurred_at'].input_formats = [
            '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S']


class ArticleLocationForm(forms.Form):
    """Add one article↔LGA tag on the staff tagging control."""
    lga = forms.ModelChoiceField(
        queryset=None, label='LGA',
        help_text='The LGA this story belongs to.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from leadership.models import LGA
        self.fields['lga'].queryset = LGA.objects.order_by('name')


class IncidentStatusForm(forms.Form):
    status = forms.ChoiceField(choices=list(SecurityIncident.STATUS))


class RedactForm(forms.Form):
    passage = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}),
        help_text='The exact passage to blank out of the working copy. '
                  'The original evidence is never altered.')


class AlertRuleForm(forms.ModelForm):
    channels = forms.MultipleChoiceField(
        choices=list(ALERT_CHANNELS), required=False,
        widget=forms.CheckboxSelectMultiple)
    recipient_capability = forms.ChoiceField(
        choices=[(cap, cap) for cap in ALL_CAPABILITIES])

    class Meta:
        model = AlertRule
        fields = ['enabled', 'channels', 'recipient_capability',
                  'recipient_emails', 'telegram_chat_ids']
        widgets = {
            'recipient_emails': forms.Textarea(attrs={'rows': 3}),
        }
