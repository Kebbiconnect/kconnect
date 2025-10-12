from django.db import models

class FAQ(models.Model):
    question = models.CharField(max_length=500)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = 'FAQ'
        verbose_name_plural = 'FAQs'
    
    def __str__(self):
        return self.question


class Report(models.Model):
    REPORT_TYPE_CHOICES = [
        ('WARD_TO_LGA', 'Ward to LGA Report'),
        ('LGA_TO_ZONAL', 'LGA to Zonal Report'),
        ('ZONAL_TO_STATE', 'Zonal to State Report'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('UNDER_REVIEW', 'Under Review'),
        ('APPROVED', 'Approved'),
        ('FLAGGED', 'Flagged for Issues'),
        ('REJECTED', 'Rejected'),
    ]
    
    title = models.CharField(max_length=300)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    content = models.TextField()
    period = models.CharField(max_length=100, blank=True, default='', help_text="Reporting period (e.g., 'January 2025', 'Q1 2025', 'Week 1')")
    
    submitted_by = models.ForeignKey('staff.User', on_delete=models.CASCADE, related_name='submitted_reports')
    submitted_to = models.ForeignKey('staff.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='received_reports', help_text="Supervisor who receives this report")
    reviewed_by = models.ForeignKey('staff.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_reports')
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='DRAFT')
    is_reviewed = models.BooleanField(default=False)
    review_notes = models.TextField(blank=True)
    
    deadline = models.DateField(null=True, blank=True, help_text="Deadline for report submission")
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.get_report_type_display()}"
    
    def is_overdue(self):
        """Check if report is overdue"""
        if self.deadline and self.status in ['DRAFT', 'SUBMITTED']:
            from django.utils import timezone
            return timezone.now().date() > self.deadline
        return False
