from django.apps import AppConfig


class TelegramIntegrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'telegram_integration'
    verbose_name = 'KPN Telegram Integration'

    def ready(self):
        pass  # Signal handlers would be imported here if needed
