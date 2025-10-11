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
    
    title = models.CharField(max_length=300)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    content = models.TextField()
    
    submitted_by = models.ForeignKey('staff.User', on_delete=models.CASCADE, related_name='submitted_reports')
    reviewed_by = models.ForeignKey('staff.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_reports')
    
    is_reviewed = models.BooleanField(default=False)
    review_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.get_report_type_display()}"
