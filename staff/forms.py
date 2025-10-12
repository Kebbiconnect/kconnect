from django import forms
from .models import User, DisciplinaryAction
from leadership.models import RoleDefinition, Zone, LGA, Ward


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
        queryset=User.objects.filter(status='APPROVED'),
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
        self.fields['user'].queryset = User.objects.filter(status='APPROVED').order_by('last_name', 'first_name')


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
