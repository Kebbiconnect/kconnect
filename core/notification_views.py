"""Website notification pages, restricted to the individual recipient."""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_safe
from core.notification_queries import visible_notifications


@login_required
@require_safe
def notification_list(request):
    page = Paginator(visible_notifications(request.user), 25).get_page(request.GET.get('page'))
    return render(request, 'core/notifications.html', {'notification_page': page})


@login_required
@require_safe
def notification_detail(request, pk):
    notice = get_object_or_404(visible_notifications(request.user), pk=pk)
    if request.method == 'GET' and not notice.is_read:
        visible_notifications(request.user).filter(pk=pk).update(is_read=True)
        notice.is_read = True
    link = notice.link.strip()
    related_url = link if (
        link and link != '#'
        and url_has_allowed_host_and_scheme(
            link, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        )
        and (link.startswith('/') or link.startswith('https://') or link.startswith('http://'))
    ) else ''
    return render(request, 'core/notification_detail.html', {
        'notice': notice, 'related_url': related_url,
    })
