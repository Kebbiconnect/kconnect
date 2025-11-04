from django import forms
from .models import Campaign
from django.utils.text import slugify


class CampaignForm(forms.ModelForm):
    """Form for creating and editing campaigns"""
    
    title = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'class': 'w-full p-2 border rounded dark:bg-gray-700',
            'placeholder': 'Enter campaign title...'
        })
    )
    
    content = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'w-full p-2 border rounded dark:bg-gray-700',
            'rows': 10,
            'placeholder': 'Write your campaign content here...'
        })
    )
    
    featured_image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'w-full p-2 border rounded dark:bg-gray-700',
            'accept': 'image/*'
        })
    )
    
    class Meta:
        model = Campaign
        fields = ['title', 'content', 'featured_image']
    
    def save(self, commit=True):
        campaign = super().save(commit=False)
        
        if not campaign.slug:
            base_slug = slugify(campaign.title)
            slug = base_slug
            counter = 1
            
            while Campaign.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            campaign.slug = slug
        
        if commit:
            campaign.save()
        
        return campaign
