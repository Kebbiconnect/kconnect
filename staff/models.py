from django.contrib.auth.models import AbstractUser
from django.db import models
from leadership.models import Zone, LGA, Ward, RoleDefinition

class User(AbstractUser):
    ROLE_CHOICES = [
        ('GENERAL', 'General Member'),
        ('STATE', 'State Executive'),
        ('ZONAL', 'Zonal Coordinator'),
        ('LGA', 'LGA Coordinator'),
        ('WARD', 'Ward Leader'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('SUSPENDED', 'Suspended'),
        ('DISMISSED', 'Dismissed'),
    ]
    
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]
    
    phone = models.CharField(max_length=20)
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='GENERAL')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    
    zone = models.ForeignKey(Zone, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    lga = models.ForeignKey(LGA, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    ward = models.ForeignKey(Ward, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    
    role_definition = models.ForeignKey(RoleDefinition, on_delete=models.SET_NULL, null=True, blank=True, related_name='holders')
    
    facebook_verified = models.BooleanField(default=False)
    date_approved = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_members')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username
    
    def is_leader(self):
        return self.role in ['STATE', 'ZONAL', 'LGA', 'WARD']
    
    def can_approve_members(self):
        return self.role in ['STATE', 'ZONAL', 'LGA'] and self.status == 'APPROVED'
    
    def get_jurisdiction(self):
        if self.role == 'STATE':
            return 'State'
        elif self.role == 'ZONAL' and self.zone:
            return self.zone.name
        elif self.role == 'LGA' and self.lga:
            return self.lga.name
        elif self.role == 'WARD' and self.ward:
            return self.ward.name
        return 'N/A'


class DisciplinaryAction(models.Model):
    ACTION_CHOICES = [
        ('WARNING', 'Warning'),
        ('SUSPENSION', 'Suspension'),
        ('DISMISSAL', 'Dismissal'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='disciplinary_actions')
    action_type = models.CharField(max_length=15, choices=ACTION_CHOICES)
    reason = models.TextField()
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='issued_actions')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_actions')
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_action_type_display()} - {self.user.get_full_name()}"
