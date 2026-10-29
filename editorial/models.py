"""Private automation state. These models are never public publishing records."""
from django.conf import settings
from django.db import models
from django.utils import timezone

class Control(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    lease_token = models.CharField(max_length=40, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)

class Source(models.Model):
    KIND = [('NEWS','Kebbi news'),('OPPORTUNITY','Opportunities')]
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=KIND)
    url = models.URLField(max_length=1000)
    feed = models.BooleanField(default=True, help_text='RSS/Atom feed; otherwise a single monitored page.')
    allowed_hosts = models.TextField(blank=True, help_text='Additional explicitly approved hostnames, one per line. No wildcards.')
    keywords = models.CharField(max_length=500, default='Kebbi,Birnin Kebbi,Argungu,Yauri,Zuru', blank=True)
    enabled = models.BooleanField(default=False)
    max_items = models.PositiveSmallIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class Item(models.Model):
    KIND = [(x,x.replace('_',' ').title()) for x in ('NEWS','OPPORTUNITY','REPORT_EDIT','COMMUNITY_EDIT','CAPTION','BRIEFING','WEEKLY','DUPLICATE','DEADLINE','LINK_ALERT')]
    STATE = [('WAITING','Waiting for processing'),('REVIEW','Needs human review'),('HANDED_OFF','Handed to existing workflow'),('APPLIED','Wording applied by reviewer'),('DISMISSED','Dismissed')]
    key = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=24, choices=KIND)
    state = models.CharField(max_length=24, choices=STATE, default='WAITING')
    title = models.CharField(max_length=300)
    source = models.ForeignKey(Source, null=True, blank=True, on_delete=models.SET_NULL)
    source_url = models.URLField(max_length=1000, blank=True)
    original = models.JSONField(default=dict)
    draft = models.JSONField(default=dict)
    report = models.ForeignKey('core.Report',null=True,blank=True,on_delete=models.CASCADE)
    community_report = models.ForeignKey('core.CommunityReport',null=True,blank=True,on_delete=models.CASCADE)
    article = models.ForeignKey('campaigns.Campaign',null=True,blank=True,on_delete=models.SET_NULL)
    opportunity = models.ForeignKey('core.Opportunity',null=True,blank=True,on_delete=models.SET_NULL)
    version = models.PositiveIntegerField(default=1)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-created_at','-pk']
        indexes = [models.Index(fields=['kind','state'],name='editorial_kind_state_idx')]
    def __str__(self): return self.title

class Job(models.Model):
    STATE = [(x,x.title()) for x in ('QUEUED','RUNNING','DONE','FAILED','BLOCKED')]
    key = models.CharField(max_length=120,unique=True)
    kind = models.CharField(max_length=16,choices=[('DISCOVER','Discover source'),('GENERATE','Generate private draft')])
    source = models.ForeignKey(Source,null=True,blank=True,on_delete=models.CASCADE)
    item = models.ForeignKey(Item,null=True,blank=True,on_delete=models.CASCADE,related_name='jobs')
    state = models.CharField(max_length=16,choices=STATE,default='QUEUED')
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True,blank=True)
    error_code = models.CharField(max_length=100,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['created_at','pk']
        indexes = [models.Index(fields=['state','available_at'],name='editorial_job_due_idx')]

class Audit(models.Model):
    item = models.ForeignKey(Item,null=True,blank=True,on_delete=models.SET_NULL,related_name='audit')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']

class Delivery(models.Model):
    item = models.ForeignKey(Item,on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    class Meta: constraints = [models.UniqueConstraint(fields=['item','user'],name='editorial_delivery_once')]

class LinkCheck(models.Model):
    opportunity = models.ForeignKey('core.Opportunity',on_delete=models.CASCADE)
    url = models.URLField(max_length=1000)
    day = models.DateField()
    state = models.CharField(max_length=16)
    http_status = models.PositiveSmallIntegerField(null=True)
    class Meta: constraints = [models.UniqueConstraint(fields=['opportunity','day'],name='editorial_link_day_once')]
