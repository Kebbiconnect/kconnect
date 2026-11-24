from django import forms
from .models import Report, OpportunityReport, CommunityReport


class OpportunityReportForm(forms.ModelForm):
    """Public 'report a suspicious listing' form (brief §B, D-07).
    Reason is required; name and contact are optional."""

    class Meta:
        model = OpportunityReport
        fields = ['reason', 'reporter_name', 'reporter_contact']
        widgets = {
            'reason': forms.Textarea(attrs={
                'class': 'kpn-input w-full', 'rows': 5,
                'placeholder': 'What looks wrong about this listing?',
            }),
            'reporter_name': forms.TextInput(attrs={
                'class': 'kpn-input w-full', 'placeholder': 'Your name (optional)',
            }),
            'reporter_contact': forms.TextInput(attrs={
                'class': 'kpn-input w-full',
                'placeholder': 'Email or phone (optional)',
            }),
        }


class PublicCommunityReportForm(forms.ModelForm):
    """Public community-report form (brief §D/§E, decision D-08).

    The open door into the same CommunityReport review queue the
    trusted-reporter route uses. A submission lands as PENDING and is
    never published automatically; Community Voice shows only reports
    a reviewer explicitly publishes. The form tells the reporter so.
    """

    class Meta:
        model = CommunityReport
        fields = [
            'reporter_name', 'reporter_phone', 'category',
            'lga', 'ward', 'location_details',
            'incident_date', 'incident_time',
            'what_happened', 'who_was_involved', 'why_is_it_important',
            'evidence_image', 'evidence_video',
        ]
        widgets = {
            'reporter_name': forms.TextInput(attrs={
                'class': 'kpn-input w-full', 'placeholder': 'Your name'}),
            'reporter_phone': forms.TextInput(attrs={
                'class': 'kpn-input w-full',
                'placeholder': 'Phone number (optional — only KPN reviewers see it)'}),
            'category': forms.Select(attrs={'class': 'kpn-input kpn-select w-full'}),
            'lga': forms.Select(attrs={'class': 'kpn-input kpn-select w-full'}),
            'ward': forms.Select(attrs={'class': 'kpn-input kpn-select w-full'}),
            'location_details': forms.TextInput(attrs={
                'class': 'kpn-input w-full',
                'placeholder': 'Village, street or landmark'}),
            'incident_date': forms.DateInput(attrs={
                'class': 'kpn-input w-full', 'type': 'date'}),
            'incident_time': forms.TimeInput(attrs={
                'class': 'kpn-input w-full', 'type': 'time'}),
            'what_happened': forms.Textarea(attrs={
                'class': 'kpn-input w-full', 'rows': 5,
                'placeholder': 'Describe what happened, as clearly as you can.'}),
            'who_was_involved': forms.Textarea(attrs={
                'class': 'kpn-input w-full', 'rows': 2}),
            'why_is_it_important': forms.Textarea(attrs={
                'class': 'kpn-input w-full', 'rows': 2}),
            'evidence_image': forms.ClearableFileInput(attrs={'class': 'kpn-input w-full'}),
            'evidence_video': forms.ClearableFileInput(attrs={'class': 'kpn-input w-full'}),
        }
        labels = {
            'reporter_name': 'Your name',
            'reporter_phone': 'Phone (optional)',
            'location_details': 'Where exactly?',
            'what_happened': 'What happened?',
            'who_was_involved': 'Who was involved? (optional)',
            'why_is_it_important': 'Why does it matter? (optional)',
            'evidence_image': 'Photo evidence (optional)',
            'evidence_video': 'Video evidence (optional)',
        }


class ReportSubmissionForm(forms.ModelForm):
    """Base form for report submission"""
    
    class Meta:
        model = Report
        fields = ['title', 'period', 'content', 'deadline']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Enter report title'
            }),
            'period': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'e.g., January 2025, Q1 2025, Week 1'
            }),
            'content': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'rows': 10,
                'placeholder': 'Write your detailed report here...'
            }),
            'deadline': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'type': 'date'
            }),
        }


class WardReportForm(ReportSubmissionForm):
    """Form for Ward leaders to submit reports to LGA"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.instance.report_type = 'WARD_TO_LGA'


class LGAReportForm(ReportSubmissionForm):
    """Form for LGA coordinators to submit reports to Zonal"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.instance.report_type = 'LGA_TO_ZONAL'


class ZonalReportForm(ReportSubmissionForm):
    """Form for Zonal coordinators to submit reports to State"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.instance.report_type = 'ZONAL_TO_STATE'


class ReportReviewForm(forms.ModelForm):
    """Form for supervisors to review reports"""
    
    ACTION_CHOICES = [
        ('APPROVED', 'Approve Report'),
        ('FLAGGED', 'Flag for Issues'),
        ('REJECTED', 'Reject Report'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-radio text-kpn-green'}),
        label="Review Action"
    )
    
    class Meta:
        model = Report
        fields = ['review_notes']
        widgets = {
            'review_notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'rows': 5,
                'placeholder': 'Enter your review comments, instructions for revision, or approval notes...'
            }),
        }

from .models import CommunityReport

class CommunityReportForm(forms.ModelForm):
    class Meta:
        model = CommunityReport
        fields = [
            'reporter_name', 'reporter_phone', 'category', 
            'lga', 'ward', 'location_details',
            'incident_date', 'incident_time',
            'what_happened', 'who_was_involved', 'why_is_it_important',
            'evidence_image', 'evidence_video'
        ]
        widgets = {
            'reporter_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'reporter_phone': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'category': forms.Select(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'lga': forms.Select(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'ward': forms.Select(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'location_details': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'incident_date': forms.DateInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'type': 'date'}),
            'incident_time': forms.TimeInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'type': 'time'}),
            'what_happened': forms.Textarea(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'rows': 4}),
            'who_was_involved': forms.Textarea(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'rows': 2}),
            'why_is_it_important': forms.Textarea(attrs={'class': 'w-full px-4 py-2 border rounded-lg', 'rows': 2}),
            'evidence_image': forms.FileInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'evidence_video': forms.FileInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
        }
