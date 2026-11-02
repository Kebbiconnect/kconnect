from django.apps import AppConfig


class StoryIntelligenceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'story_intelligence'
    verbose_name = 'KPN Story Intelligence'

    def ready(self):
        from . import signals  # noqa: F401  (backstop anomaly audit only)
