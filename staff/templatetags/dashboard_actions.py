from django import template
from staff.quick_actions import actions_for

register = template.Library()

@register.inclusion_tag('staff/dashboards/includes/_quick_actions.html', takes_context=True)
def dashboard_quick_actions(context):
    actions = actions_for(context['user'])
    return {'primary_actions': actions[:4], 'more_actions': actions[4:]}
