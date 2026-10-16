from django import template
from staff.quick_actions import actions_for

register = template.Library()

@register.inclusion_tag('staff/dashboards/includes/_quick_actions.html', takes_context=True)
def dashboard_quick_actions(context):
    actions = actions_for(context['user'])
    return {'primary_actions': actions[:4], 'more_actions': actions[4:]}


@register.inclusion_tag('telegram_integration/_telegram_status.html', takes_context=True)
def dashboard_telegram_status(context):
    """Display Telegram state without changing dashboard access policy."""
    from telegram_integration.permissions import requires_telegram

    user = context.get('user')
    required = bool(user and user.is_authenticated and requires_telegram(user))
    return {
        'request': context.get('request'),
        'telegram_required': required,
    }
