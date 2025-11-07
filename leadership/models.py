from django.db import models

class Zone(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class LGA(models.Model):
    name = models.CharField(max_length=100)
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='lgas')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'LGA'
        verbose_name_plural = 'LGAs'
    
    def __str__(self):
        return f"{self.name} ({self.zone.name})"


class Ward(models.Model):
    name = models.CharField(max_length=200)
    lga = models.ForeignKey(LGA, on_delete=models.CASCADE, related_name='wards')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['lga__name', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.lga.name})"


class RoleDefinition(models.Model):
    TIER_CHOICES = [
        ('STATE', 'State Executive'),
        ('ZONAL', 'Zonal Excos'),
        ('LGA', 'LGA Excos'),
        ('WARD', 'Ward Leaders'),
    ]
    
    title = models.CharField(max_length=200)
    tier = models.CharField(max_length=10, choices=TIER_CHOICES)
    description = models.TextField(blank=True)
    seat_number = models.PositiveIntegerField(help_text="Position number within tier (e.g., 1 for President)")
    
    class Meta:
        ordering = ['tier', 'seat_number']
        unique_together = ['tier', 'title']
    
    def __str__(self):
        return f"{self.title} ({self.get_tier_display()})"
