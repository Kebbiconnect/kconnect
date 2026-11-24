from django.apps import AppConfig


class IntelligenceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'intelligence'
    verbose_name = 'KPN Statewide Intelligence'

    def ready(self):
        from django.apps import apps
        from django.db.models.signals import post_save

        from .signals import sync_intelligence_units

        post_save.connect(
            sync_intelligence_units,
            sender=apps.get_model('campaigns', 'Campaign'),
            dispatch_uid='intelligence_sync_published_units')
