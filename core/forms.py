from django import forms
from .models import Report


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
                'placeholder': 'Provide feedback or notes on this report...'
            }),
        }
