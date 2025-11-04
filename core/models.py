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
        ('ESCALATED', 'Escalated to Next Level'),
    ]
    
    title = models.CharField(max_length=300)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    content = models.TextField()
    period = models.CharField(max_length=100, blank=True, default='', help_text="Reporting period (e.g., 'January 2025', 'Q1 2025', 'Week 1')")
    
    submitted_by = models.ForeignKey('staff.User', on_delete=models.CASCADE, related_name='submitted_reports')
    submitted_to = models.ForeignKey('staff.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='received_reports', help_text="Supervisor who receives this report")
    reviewed_by = models.ForeignKey('staff.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_reports')
    
    parent_report = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='child_reports', help_text="Parent report that this report was escalated from")
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='DRAFT')
    is_reviewed = models.BooleanField(default=False)
    is_escalated = models.BooleanField(default=False, help_text="Whether this report has been escalated to next level")
    review_notes = models.TextField(blank=True)
    
    deadline = models.DateField(null=True, blank=True, help_text="Deadline for report submission")
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True, help_text="When this report was escalated")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'submitted_to'], name='report_status_receiver_idx'),
            models.Index(fields=['status', '-created_at'], name='report_status_created_idx'),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.get_report_type_display()}"
    
    def is_overdue(self):
        """Check if report is overdue"""
        if self.deadline and self.status in ['DRAFT', 'SUBMITTED']:
            from django.utils import timezone
            return timezone.now().date() > self.deadline
        return False
    
    def get_report_chain(self):
        """Get the full chain of reports from root to this report"""
        chain = [self]
        current = self.parent_report
        while current:
            chain.insert(0, current)
            current = current.parent_report
        return chain
    
    def can_be_escalated(self):
        """Check if this report can be escalated to the next level"""
        return (
            self.status == 'APPROVED' and 
            not self.is_escalated and 
            self.report_type in ['WARD_TO_LGA', 'LGA_TO_ZONAL']
        )

