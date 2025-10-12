from django import forms
from .models import Event, EventAttendance, MeetingMinutes
from staff.models import User


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'location', 'start_date', 'end_date']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Event Title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Event Description',
                'rows': 4
            }),
            'location': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Event Location'
            }),
            'start_date': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'type': 'datetime-local'
            }),
            'end_date': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'type': 'datetime-local'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and start_date >= end_date:
            raise forms.ValidationError('End date must be after start date.')

        return cleaned_data


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = EventAttendance
        fields = ['attendee', 'present', 'notes']
        widgets = {
            'attendee': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
            'present': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-kpn-blue focus:ring-kpn-blue border-gray-300 rounded'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Additional notes (optional)',
                'rows': 2
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['attendee'].queryset = User.objects.filter(status='APPROVED').exclude(role='GENERAL')


class BulkAttendanceForm(forms.Form):
    event = forms.ModelChoiceField(
        queryset=Event.objects.all(),
        widget=forms.HiddenInput()
    )
    
    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event', None)
        super().__init__(*args, **kwargs)
        
        if event:
            self.fields['event'].initial = event
            leaders = User.objects.filter(status='APPROVED').exclude(role='GENERAL').order_by('last_name', 'first_name')
            
            for leader in leaders:
                field_name = f'attendee_{leader.id}'
                self.fields[field_name] = forms.BooleanField(
                    required=False,
                    label=leader.get_full_name(),
                    initial=False
                )


class MeetingMinutesForm(forms.ModelForm):
    class Meta:
        model = MeetingMinutes
        fields = ['content', 'summary', 'attendees_present', 'is_published']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Enter full meeting minutes here...',
                'rows': 10
            }),
            'summary': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Brief summary of key points and decisions...',
                'rows': 4
            }),
            'attendees_present': forms.CheckboxSelectMultiple(attrs={
                'class': 'h-4 w-4 text-kpn-blue focus:ring-kpn-blue border-gray-300 rounded'
            }),
            'is_published': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-kpn-blue focus:ring-kpn-blue border-gray-300 rounded'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['attendees_present'].queryset = User.objects.filter(status='APPROVED').exclude(role='GENERAL').order_by('last_name', 'first_name')
        self.fields['attendees_present'].required = False
