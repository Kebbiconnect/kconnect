from django.apps import AppConfig

class EditorialConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'editorial'
    verbose_name = 'KPN Editorial Assistant'

    def ready(self):
        from . import checks
        from . import signals  # noqa: F401
