"""ID tag generation rate limit: one tag per account per calendar
month, where the calendar month is reckoned in Africa/Lagos (the
site TIME_ZONE)."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import IdTagGeneration

LAGOS = ZoneInfo('Africa/Lagos')


def current_month_window():
    """(start, end) aware datetimes bounding the current calendar
    month in Africa/Lagos: start is day 1 at 00:00 Lagos, end is the
    first of the next month at 00:00 Lagos (exclusive)."""
    now_local = timezone.now().astimezone(LAGOS)
    start = datetime.combine(
        date(now_local.year, now_local.month, 1), time.min, tzinfo=LAGOS)
    if now_local.month == 12:
        end = datetime.combine(
            date(now_local.year + 1, 1, 1), time.min, tzinfo=LAGOS)
    else:
        end = datetime.combine(
            date(now_local.year, now_local.month + 1, 1), time.min,
            tzinfo=LAGOS)
    return start, end


def generations_this_month(user):
    start, end = current_month_window()
    return IdTagGeneration.objects.filter(
        user=user, generated_at__gte=start, generated_at__lt=end).count()


def id_tag_limit_reached(user):
    return generations_this_month(user) >= 1


def next_available_date():
    """The date (Africa/Lagos) from which a new generation is allowed
    again: the 1st of next month."""
    _, end = current_month_window()
    return end.date()


def limit_message():
    nxt = next_available_date()
    return (
        'You have already generated your ID tag this month. '
        f'You can generate a new one from {nxt.day} '
        f'{nxt.strftime("%B")} {nxt.year}.')


def record_generation(user):
    return IdTagGeneration.objects.create(user=user)
