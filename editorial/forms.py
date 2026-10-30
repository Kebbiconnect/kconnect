from django import forms
from django.core.exceptions import ValidationError
from .models import Source
from .fetch import canonical, hosts_for, FetchError

class SourceForm(forms.ModelForm):
    class Meta:
        model=Source
        fields=['name','kind','url','feed','allowed_hosts','keywords','max_items','enabled']
        widgets={'allowed_hosts':forms.Textarea(attrs={'rows':3})}
    def clean(self):
        data=super().clean()
        try:
            self.instance.url=canonical(data.get('url',''))
            self.instance.allowed_hosts=data.get('allowed_hosts','')
            hosts_for(self.instance);data['url']=self.instance.url
        except (FetchError,ValueError):raise ValidationError('Use HTTPS and exact approved hostnames; no credentials, wildcards or custom ports.')
        if not 1<=data.get('max_items',0)<=5:raise ValidationError('Use 1–5 items per source per daily run.')
        return data

class DraftForm(forms.Form):
    version=forms.IntegerField(min_value=1,widget=forms.HiddenInput)
    def __init__(self,*args,item,**kwargs):
        super().__init__(*args,**kwargs)
        names={
            'NEWS':['title','body','category','notes'],
            'OPPORTUNITY':['title','body','provider','category','requirements','benefits','application_link','deadline','notes'],
            'REPORT_EDIT':['title','content','notes'],
            'COMMUNITY_EDIT':['title','what_happened','who_was_involved','why_is_it_important','notes'],
        }.get(item.kind,['title','body','notes'])
        for name in names:
            initial=item.draft.get(name,item.title if name=='title' else '')
            if name=='category' and item.kind in {'NEWS','OPPORTUNITY'}:
                # Category is a dropdown of the REAL backend categories for
                # this kind (news and opportunity lists are different), so a
                # reviewer can never save a category the handoff will reject.
                from campaigns.models import Campaign
                from core.models import Opportunity
                choices=(Campaign.CATEGORY_CHOICES if item.kind=='NEWS' else Opportunity.CATEGORY_CHOICES)
                self.fields[name]=forms.ChoiceField(choices=choices,required=True,initial=initial if initial in dict(choices) else '')
            else:
                self.fields[name]=forms.CharField(required=name=='title',max_length=300 if name=='title' else 20000,widget=forms.TextInput if name in {'title','provider','deadline','application_link'} else forms.Textarea(attrs={'rows':6}),initial=initial)
        self.fields['version'].initial=item.version
