from django.db import models
from django.conf import settings

class Donation(models.Model):
    STATUS_CHOICES = [
        ('UNVERIFIED', 'Unverified'),
        ('VERIFIED', 'Verified'),
        ('RECORDED', 'Recorded'),
    ]
    
    donor_name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, unique=True, help_text="Bank transaction reference")
    notes = models.TextField(blank=True)
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='UNVERIFIED')
    
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_donations')
    verified_at = models.DateTimeField(null=True, blank=True)
    
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_donations')
    recorded_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.donor_name} - ₦{self.amount}"


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('OPERATIONS', 'Operational Expenses'),
        ('EVENTS', 'Events & Meetings'),
        ('PUBLICITY', 'Publicity & Media'),
        ('WELFARE', 'Welfare & Support'),
        ('OTHER', 'Other'),
    ]
    
    description = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    notes = models.TextField(blank=True)
    date = models.DateField()
    
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='recorded_expenses')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.description} - ₦{self.amount}"


class FinancialReport(models.Model):
    title = models.CharField(max_length=300)
    report_period = models.CharField(max_length=100, help_text="e.g., 'January 2025' or 'Q1 2025'")
    total_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    report_file = models.FileField(upload_to='financial_reports/', blank=True, null=True)
    summary = models.TextField()
    
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='prepared_reports')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.report_period}"


class AuditReport(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('REVIEWED', 'Reviewed'),
    ]
    
    title = models.CharField(max_length=300)
    audit_period = models.CharField(max_length=100, help_text="e.g., 'Q1 2025' or 'January-March 2025'")
    findings = models.TextField(help_text="Key findings from the audit")
    recommendations = models.TextField(help_text="Recommendations for improvement")
    compliance_status = models.CharField(max_length=200, blank=True, help_text="Overall compliance status")
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='DRAFT')
    
    report_file = models.FileField(upload_to='audit_reports/', blank=True, null=True, help_text="Upload detailed audit report PDF")
    
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='submitted_audits')
    submitted_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_audits', help_text="Usually the President")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_audits')
    
    review_notes = models.TextField(blank=True, help_text="Notes from the reviewer")
    
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Audit Report"
        verbose_name_plural = "Audit Reports"
    
    def __str__(self):
        return f"{self.title} - {self.audit_period}"
