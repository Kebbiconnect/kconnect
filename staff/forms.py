from django import forms
from .models import User, DisciplinaryAction, WomensProgram, YouthProgram, WelfareProgram, CommunityOutreach, WardMeeting, WardMeetingAttendance, Announcement
from leadership.models import RoleDefinition, Zone, LGA, Ward
from core.models import FAQ


class EditMemberRoleForm(forms.ModelForm):
    """Form for editing a member's role and position"""
    
    role_definition = forms.ModelChoiceField(
        queryset=RoleDefinition.objects.all(),
        required=False,
        empty_label="General Member (No Leadership Position)",
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    zone = forms.ModelChoiceField(
        queryset=Zone.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    lga = forms.ModelChoiceField(
        queryset=LGA.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    ward = forms.ModelChoiceField(
        queryset=Ward.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    class Meta:
        model = User
        fields = ['role_definition', 'zone', 'lga', 'ward']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if 'zone' in self.data:
            try:
                zone_id = int(self.data.get('zone'))
                self.fields['lga'].queryset = LGA.objects.filter(zone_id=zone_id).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.zone:
            self.fields['lga'].queryset = self.instance.zone.lgas.order_by('name')
        
        if 'lga' in self.data:
            try:
                lga_id = int(self.data.get('lga'))
                self.fields['ward'].queryset = Ward.objects.filter(lga_id=lga_id).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.lga:
            self.fields['ward'].queryset = self.instance.lga.wards.order_by('name')
    
    def clean(self):
        cleaned_data = super().clean()
        role_definition = cleaned_data.get('role_definition')
        zone = cleaned_data.get('zone')
        lga = cleaned_data.get('lga')
        ward = cleaned_data.get('ward')
        
        if role_definition:
            tier = role_definition.tier
            
            if tier == 'STATE':
                pass
            elif tier == 'ZONAL':
                if not zone:
                    raise forms.ValidationError("Zone is required for Zonal positions")
            elif tier == 'LGA':
                if not lga:
                    raise forms.ValidationError("LGA is required for LGA positions")
            elif tier == 'WARD':
                if not ward:
                    raise forms.ValidationError("Ward is required for Ward positions")
            
            existing_holder = User.objects.filter(
                role_definition=role_definition,
                zone=zone,
                lga=lga,
                ward=ward,
                status='APPROVED'
            ).exclude(pk=self.instance.pk).first()
            
            if existing_holder:
                raise forms.ValidationError(
                    f"This position is already held by {existing_holder.get_full_name()}. "
                    f"Please dismiss or transfer them first."
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        
        if user.role_definition:
            user.role = user.role_definition.tier
        else:
            user.role = 'GENERAL'
        
        if commit:
            user.save()
        return user


class PromoteMemberForm(forms.Form):
    """Form for promoting a member to a higher tier or specific position"""
    
    new_role_definition = forms.ModelChoiceField(
        queryset=RoleDefinition.objects.all(),
        label="Promote to Position",
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    zone = forms.ModelChoiceField(
        queryset=Zone.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    lga = forms.ModelChoiceField(
        queryset=LGA.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    ward = forms.ModelChoiceField(
        queryset=Ward.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            current_tier = self.user.role
            tier_hierarchy = ['GENERAL', 'WARD', 'LGA', 'ZONAL', 'STATE']
            
            try:
                current_index = tier_hierarchy.index(current_tier)
                higher_tiers = tier_hierarchy[current_index + 1:]
                self.fields['new_role_definition'].queryset = RoleDefinition.objects.filter(
                    tier__in=higher_tiers
                )
            except (ValueError, IndexError):
                self.fields['new_role_definition'].queryset = RoleDefinition.objects.all()


class DemoteMemberForm(forms.Form):
    """Form for demoting a member to a lower tier"""
    
    new_role = forms.ChoiceField(
        choices=[
            ('GENERAL', 'General Member (No Leadership Position)'),
            ('WARD', 'Ward Leader'),
            ('LGA', 'LGA Coordinator'),
            ('ZONAL', 'Zonal Coordinator'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-radio'})
    )
    
    new_role_definition = forms.ModelChoiceField(
        queryset=RoleDefinition.objects.none(),
        required=False,
        label="Specific Position (if applicable)",
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    zone = forms.ModelChoiceField(
        queryset=Zone.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    lga = forms.ModelChoiceField(
        queryset=LGA.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    ward = forms.ModelChoiceField(
        queryset=Ward.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            current_tier = self.user.role
            tier_hierarchy = ['GENERAL', 'WARD', 'LGA', 'ZONAL', 'STATE']
            
            try:
                current_index = tier_hierarchy.index(current_tier)
                lower_tiers = tier_hierarchy[:current_index]
                
                choices = [('GENERAL', 'General Member (No Leadership Position)')]
                for tier in lower_tiers:
                    if tier != 'GENERAL':
                        tier_label = dict([
                            ('WARD', 'Ward Leader'),
                            ('LGA', 'LGA Coordinator'),
                            ('ZONAL', 'Zonal Coordinator'),
                        ]).get(tier, tier)
                        choices.append((tier, tier_label))
                
                self.fields['new_role'].choices = choices
            except (ValueError, IndexError):
                pass


class SwapPositionsForm(forms.Form):
    """Form for swapping positions between two members"""
    
    member1 = forms.ModelChoiceField(
        queryset=User.objects.filter(status='APPROVED').exclude(role='GENERAL'),
        label="First Member",
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    member2 = forms.ModelChoiceField(
        queryset=User.objects.filter(status='APPROVED').exclude(role='GENERAL'),
        label="Second Member",
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        member1 = cleaned_data.get('member1')
        member2 = cleaned_data.get('member2')
        
        if member1 and member2:
            if member1.pk == member2.pk:
                raise forms.ValidationError("Cannot swap a member with themselves")
            
            if not member1.role_definition or not member2.role_definition:
                raise forms.ValidationError("Both members must have leadership positions to swap")
        
        return cleaned_data


class DisciplinaryActionForm(forms.ModelForm):
    """Form for creating disciplinary actions"""
    
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(status='APPROVED', is_superuser=False),
        label="Select Member",
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    action_type = forms.ChoiceField(
        choices=DisciplinaryAction.ACTION_CHOICES,
        label="Action Type",
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    reason = forms.CharField(
        label="Reason for Disciplinary Action",
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Provide a detailed reason for this disciplinary action...',
            'rows': 5
        })
    )
    
    class Meta:
        model = DisciplinaryAction
        fields = ['user', 'action_type', 'reason']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Exclude superusers from disciplinary actions
        self.fields['user'].queryset = User.objects.filter(status='APPROVED', is_superuser=False).order_by('last_name', 'first_name')


class MemberMobilizationFilterForm(forms.Form):
    """Advanced filter form for member mobilization and contact list generation"""
    
    zone = forms.ModelChoiceField(
        queryset=Zone.objects.all(),
        required=False,
        empty_label="All Zones",
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    lga = forms.ModelChoiceField(
        queryset=LGA.objects.all(),
        required=False,
        empty_label="All LGAs",
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    ward = forms.ModelChoiceField(
        queryset=Ward.objects.all(),
        required=False,
        empty_label="All Wards",
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    role = forms.ChoiceField(
        choices=[('', 'All Roles')] + User.ROLE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    gender = forms.ChoiceField(
        choices=[('', 'All Genders')] + User.GENDER_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    status = forms.ChoiceField(
        choices=[('', 'All Status'), ('APPROVED', 'Approved'), ('PENDING', 'Pending'), ('SUSPENDED', 'Suspended')],
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    tier = forms.ChoiceField(
        choices=[
            ('', 'All Tiers'),
            ('STATE', 'State Executive'),
            ('ZONAL', 'Zonal'),
            ('LGA', 'LGA'),
            ('WARD', 'Ward'),
            ('GENERAL', 'General Members')
        ],
        required=False,
        label="Filter by Tier",
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded dark:bg-gray-700'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Dynamic LGA filtering based on zone
        if 'zone' in self.data:
            try:
                zone_id = int(self.data.get('zone'))
                self.fields['lga'].queryset = LGA.objects.filter(zone_id=zone_id).order_by('name')
            except (ValueError, TypeError):
                pass
        
        # Dynamic Ward filtering based on LGA
        if 'lga' in self.data:
            try:
                lga_id = int(self.data.get('lga'))
                self.fields['ward'].queryset = Ward.objects.filter(lga_id=lga_id).order_by('name')
            except (ValueError, TypeError):
                pass


class WomensProgramForm(forms.ModelForm):
    """Form for creating and editing women's programs"""
    
    title = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Enter program title...'
        })
    )
    
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Describe the program objectives and activities...',
            'rows': 5
        })
    )
    
    program_type = forms.ChoiceField(
        choices=WomensProgram.PROGRAM_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    status = forms.ChoiceField(
        choices=WomensProgram.PROGRAM_STATUS_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    location = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Enter location/venue...'
        })
    )
    
    target_participants = forms.IntegerField(
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'min': 0
        })
    )
    
    budget = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'step': '0.01',
            'placeholder': '0.00'
        })
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Additional notes or comments...',
            'rows': 3
        })
    )
    
    class Meta:
        model = WomensProgram
        fields = ['title', 'description', 'program_type', 'status', 'start_date', 'end_date', 
                  'location', 'target_participants', 'budget', 'notes']


class FAQForm(forms.ModelForm):
    """Form for managing FAQs"""
    
    question = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Enter the question...'
        })
    )
    
    answer = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Enter the answer...',
            'rows': 5
        })
    )
    
    order = forms.IntegerField(
        initial=0,
        help_text="Lower numbers appear first",
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'min': 0
        })
    )
    
    is_active = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-kpn-blue border-gray-300 rounded focus:ring-kpn-blue dark:focus:ring-kpn-blue dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600'
        })
    )
    
    class Meta:
        model = FAQ
        fields = ['question', 'answer', 'order', 'is_active']


class LegalReviewForm(forms.Form):
    """Form for Legal Adviser to review disciplinary actions"""
    
    legal_opinion = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Provide your legal opinion on this disciplinary action...',
            'rows': 5
        })
    )
    
    legal_approved = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-kpn-blue border-gray-300 rounded focus:ring-kpn-blue dark:focus:ring-kpn-blue dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600'
        })
    )


class YouthProgramForm(forms.ModelForm):
    """Form for creating and editing youth programs"""
    
    class Meta:
        model = YouthProgram
        fields = ['title', 'description', 'program_type', 'status', 'start_date', 'end_date', 
                  'location', 'target_participants', 'budget', 'impact_report', 'notes']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Enter program title...'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Describe the program objectives and activities...',
                'rows': 5
            }),
            'program_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
            'location': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Enter location/venue...'
            }),
            'target_participants': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'min': 0
            }),
            'budget': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'step': '0.01',
                'min': 0
            }),
            'impact_report': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Summary of program impact and outcomes...',
                'rows': 4
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Additional notes or comments...',
                'rows': 3
            }),
        }


class WelfareProgramForm(forms.ModelForm):
    """Form for creating and editing welfare programs"""
    
    class Meta:
        model = WelfareProgram
        fields = ['title', 'description', 'program_type', 'status', 'start_date', 'end_date', 
                  'target_beneficiaries', 'budget', 'funds_disbursed', 'notes']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Enter program title...'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Describe the welfare program...',
                'rows': 5
            }),
            'program_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
            }),
            'target_beneficiaries': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'min': 0
            }),
            'budget': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'step': '0.01',
                'min': 0
            }),
            'funds_disbursed': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'step': '0.01',
                'min': 0
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
                'placeholder': 'Additional notes or comments...',
                'rows': 3
            }),
        }


class CommunityOutreachForm(forms.ModelForm):
    """Form for creating and managing community outreach activities"""
    
    organization = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Organization or community group name...'
        })
    )
    
    contact_person = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Contact person name...'
        })
    )
    
    contact_phone = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Phone number...'
        })
    )
    
    contact_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Email address...'
        })
    )
    
    engagement_type = forms.ChoiceField(
        choices=CommunityOutreach.ENGAGEMENT_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    status = forms.ChoiceField(
        choices=CommunityOutreach.STATUS_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    location = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Location of engagement...'
        })
    )
    
    purpose = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Purpose of the outreach activity...',
            'rows': 4
        })
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Details and outcomes of the engagement...',
            'rows': 4
        })
    )
    
    follow_up_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    follow_up_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Follow-up action items...',
            'rows': 3
        })
    )
    
    class Meta:
        model = CommunityOutreach
        fields = ['organization', 'contact_person', 'contact_phone', 'contact_email', 
                  'engagement_type', 'status', 'date', 'location', 'purpose', 'notes', 
                  'follow_up_date', 'follow_up_notes']


class WardMeetingForm(forms.ModelForm):
    """Form for creating and managing ward meetings"""
    
    ward = forms.ModelChoiceField(
        queryset=Ward.objects.all(),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    meeting_type = forms.ChoiceField(
        choices=WardMeeting.MEETING_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    title = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Meeting title...'
        })
    )
    
    date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={
            'type': 'time',
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white'
        })
    )
    
    location = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Meeting location/venue...'
        })
    )
    
    agenda = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Meeting agenda and topics...',
            'rows': 4
        })
    )
    
    minutes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-blue dark:bg-gray-700 dark:text-white',
            'placeholder': 'Meeting minutes and decisions...',
            'rows': 6
        })
    )
    
    class Meta:
        model = WardMeeting
        fields = ['ward', 'meeting_type', 'title', 'date', 'time', 'location', 'agenda', 'minutes']
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user and user.ward:
            self.fields['ward'].initial = user.ward
            self.fields['ward'].queryset = Ward.objects.filter(pk=user.ward.pk)


class WardMeetingAttendanceForm(forms.Form):
    """Form for recording ward meeting attendance"""
    
    def __init__(self, *args, **kwargs):
        meeting = kwargs.pop('meeting', None)
        super().__init__(*args, **kwargs)
        
        if meeting and meeting.ward:
            ward_members = User.objects.filter(
                ward=meeting.ward,
                status='APPROVED'
            ).order_by('last_name', 'first_name')
            
            for member in ward_members:
                self.fields[f'attendee_{member.id}'] = forms.BooleanField(
                    required=False,
                    label=member.get_full_name(),
                    widget=forms.CheckboxInput(attrs={
                        'class': 'w-4 h-4 text-kpn-blue border-gray-300 rounded focus:ring-kpn-blue'
                    })
                )


class AnnouncementForm(forms.ModelForm):
    """Form for creating announcements with role-based permission filtering"""
    
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-green dark:bg-gray-700 dark:text-white',
            'placeholder': 'Brief title for the announcement...'
        })
    )
    
    content = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-green dark:bg-gray-700 dark:text-white',
            'placeholder': 'Write your announcement message here...',
            'rows': 6
        })
    )
    
    scope = forms.ChoiceField(
        choices=Announcement.SCOPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-green dark:bg-gray-700 dark:text-white',
            'id': 'scope-select'
        })
    )
    
    priority = forms.ChoiceField(
        choices=Announcement.PRIORITY_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-green dark:bg-gray-700 dark:text-white'
        })
    )
    
    target_zone = forms.ModelChoiceField(
        queryset=Zone.objects.all(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-green dark:bg-gray-700 dark:text-white',
            'id': 'zone-select'
        })
    )
    
    target_lga = forms.ModelChoiceField(
        queryset=LGA.objects.all(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-green dark:bg-gray-700 dark:text-white',
            'id': 'lga-select'
        })
    )
    
    target_ward = forms.ModelChoiceField(
        queryset=Ward.objects.all(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-green dark:bg-gray-700 dark:text-white',
            'id': 'ward-select'
        })
    )
    
    expires_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local',
            'class': 'w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-kpn-green dark:bg-gray-700 dark:text-white'
        })
    )
    
    class Meta:
        model = Announcement
        fields = ['title', 'content', 'scope', 'priority', 'target_zone', 'target_lga', 'target_ward', 'expires_at']
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            if user.role == 'STATE':
                pass
            elif user.role == 'ZONAL' and user.zone:
                self.fields['scope'].choices = [
                    ('ZONAL', 'Zonal - Specific Zone'),
                    ('LGA', 'LGA - Specific LGA'),
                    ('WARD', 'Ward - Specific Ward'),
                ]
                self.fields['target_zone'].queryset = Zone.objects.filter(pk=user.zone.pk)
                self.fields['target_zone'].initial = user.zone
                self.fields['target_lga'].queryset = LGA.objects.filter(zone=user.zone)
                self.fields['target_ward'].queryset = Ward.objects.filter(lga__zone=user.zone)
            elif user.role == 'LGA' and user.lga:
                self.fields['scope'].choices = [
                    ('LGA', 'LGA - Specific LGA'),
                    ('WARD', 'Ward - Specific Ward'),
                ]
                self.fields['target_lga'].queryset = LGA.objects.filter(pk=user.lga.pk)
                self.fields['target_lga'].initial = user.lga
                self.fields['target_ward'].queryset = Ward.objects.filter(lga=user.lga)
                del self.fields['target_zone']
            elif user.role == 'WARD' and user.ward:
                self.fields['scope'].choices = [
                    ('WARD', 'Ward - Specific Ward'),
                ]
                self.fields['target_ward'].queryset = Ward.objects.filter(pk=user.ward.pk)
                self.fields['target_ward'].initial = user.ward
                del self.fields['target_zone']
                del self.fields['target_lga']
    
    def clean(self):
        cleaned_data = super().clean()
        scope = cleaned_data.get('scope')
        target_zone = cleaned_data.get('target_zone')
        target_lga = cleaned_data.get('target_lga')
        target_ward = cleaned_data.get('target_ward')
        
        if scope == 'GENERAL':
            if target_zone or target_lga or target_ward:
                raise forms.ValidationError("General announcements should not have zone, LGA, or ward targets.")
        elif scope == 'ZONAL':
            if not target_zone:
                raise forms.ValidationError("Please select a zone for this zonal announcement.")
            if target_lga or target_ward:
                raise forms.ValidationError("Zonal announcements should only specify a zone.")
        elif scope == 'LGA':
            if not target_lga:
                raise forms.ValidationError("Please select an LGA for this LGA announcement.")
            if target_ward:
                raise forms.ValidationError("LGA announcements should not specify a ward.")
        elif scope == 'WARD':
            if not target_ward:
                raise forms.ValidationError("Please select a ward for this ward announcement.")
        
        return cleaned_data
