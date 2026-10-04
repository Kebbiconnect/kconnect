from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from leadership.roles import EDITOR_ROLES
from core.notifications import notify

def title(user): return getattr(getattr(user,'role_definition',None),'title','')
def require_editor(user):
    if user.status!='VERIFIED' or title(user) not in EDITOR_ROLES: raise PermissionDenied('Editorial permission required.')

@transaction.atomic
def submit(article, actor):
    if article.author_id!=actor.id: raise PermissionDenied('You may submit only your own draft.')
    if article.status!='DRAFT': raise ValidationError({'status':'Only drafts can be submitted.'})
    if not article.content and not article.content_json: raise ValidationError({'content':'Article body is required.'})
    article.status='PENDING'; article.save(update_fields=['status']); return article

@transaction.atomic
def decide(article, actor, decision, note=''):
    require_editor(actor)
    if article.status!='PENDING': raise ValidationError({'status':'Only pending articles can be reviewed.'})
    if decision=='publish':
        article.status='PUBLISHED'; article.approved_by=actor; article.published_at=timezone.now(); article.rejection_note=''
        event='ARTICLE_PUBLISHED'
    elif decision=='return':
        article.status='REJECTED'; article.rejection_note=note; event='ARTICLE_RETURNED'
    else: raise ValidationError({'decision':'Use publish or return.'})
    article.save()
    notify(article.author,'SUCCESS' if decision=='publish' else 'ACTION','Article Published' if decision=='publish' else 'Article Returned',f'“{article.title}” was {"published" if decision=="publish" else "returned for revision"}.','/campaigns/my-articles/',event=event)
    return article
