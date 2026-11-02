"""Newsroom services (KPN Media Phase 1, v2.5.0).

publish_campaign() is the single publishing service used by the web
review queue and the REST API decision endpoint. It enforces the Phase 1
invariant — no article reaches PUBLISHED without a permanent Story ID —
inside one transaction: if Story ID allocation fails, the transaction
rolls back and the article stays in its previous state (recoverable).

archive/restore/delete guards implement the owner's Phase 1 rule:
published articles, articles with a Story ID, and articles with
dependent story records are never hard-deleted; they are archived
(status ARCHIVED, which every public queryset already excludes) and can
be restored with their Story ID and history intact. Ordinary drafts
with no ID and no story records keep the previous delete behaviour.
"""
from django.db import transaction
from django.utils import timezone


class ProtectedArticleError(Exception):
    """Raised when a hard delete is attempted on a protected article."""


@transaction.atomic
def publish_campaign(article, actor):
    """Publish one article, allocating its permanent Story ID first.

    Mirrors the field changes the web and API publish paths have always
    made (status, approved_by, published_at, cleared rejection note).

    Phase 4: the Human Impact consent guard runs first — a story that
    features identifiable people cannot publish without a consent
    record on file. ConsentRequiredError aborts the transaction, so
    the article stays in its previous state, unpublished and intact.
    """
    from story_intelligence.services import (
        allocate_story_id, ensure_consent_for_publish)
    ensure_consent_for_publish(article)
    if not article.story_id:
        allocate_story_id(article, actor=actor)
    article.status = 'PUBLISHED'
    article.approved_by = actor
    article.published_at = timezone.now()
    article.rejection_note = ''
    article.save(update_fields=[
        'story_id', 'status', 'approved_by', 'published_at',
        'rejection_note', 'updated_at'])
    return article


def article_has_story_dependents(article):
    """True when story records hang off this article."""
    from story_intelligence.models import (
        ConsentRecord, Correction, Claim, EvidenceRecord, StoryUpdate,
    )
    if StoryUpdate.objects.filter(article_id=article.pk).exists():
        return True
    if Claim.objects.filter(article_id=article.pk).exists():
        return True
    if EvidenceRecord.objects.filter(article_id=article.pk).exists():
        return True
    if Correction.objects.filter(article_id=article.pk).exists():
        return True
    if ConsentRecord.objects.filter(article_id=article.pk).exists():
        return True
    profile = getattr(article, 'story_profile', None)
    return bool(profile is not None and profile.pk)


def article_is_protected(article):
    """Articles that must be archived, never hard-deleted."""
    if article.status in ('PUBLISHED', 'ARCHIVED'):
        return True
    if article.story_id:
        return True
    return article_has_story_dependents(article)


@transaction.atomic
def archive_campaign(article, actor=None):
    """Remove an article from public view while preserving the record,
    its Story ID and all story history."""
    from story_intelligence.services import log_audit
    article.status = 'ARCHIVED'
    article.save(update_fields=['status', 'updated_at'])
    log_audit(actor, 'ARTICLE_ARCHIVED', 'campaign', article.pk,
              {'story_id': article.story_id})
    return article


@transaction.atomic
def restore_campaign(article, actor=None):
    """Restore an archived article to PUBLISHED, preserving its Story ID
    and history. An archived article always already has a Story ID (it
    was published before), but allocate defensively if one is missing.
    Restoring is a re-publication, so the Phase 4 consent guard applies
    exactly as it does to a first publication."""
    from story_intelligence.services import (
        allocate_story_id, ensure_consent_for_publish, log_audit)
    ensure_consent_for_publish(article)
    if not article.story_id:
        allocate_story_id(article, actor=actor)
    article.status = 'PUBLISHED'
    if not article.published_at:
        article.published_at = timezone.now()
    article.save(update_fields=['story_id', 'status', 'published_at', 'updated_at'])
    log_audit(actor, 'ARTICLE_RESTORED', 'campaign', article.pk,
              {'story_id': article.story_id})
    return article


def delete_campaign(article):
    """Hard-delete an article only when it is not protected.

    Raises ProtectedArticleError for published / ID-bearing /
    dependent-bearing articles — callers should direct the editor to
    archive instead. (story_intelligence FKs are also PROTECT, so the
    ORM collector independently blocks deleting articles with story
    records.)
    """
    if article_is_protected(article):
        raise ProtectedArticleError(
            'This article is part of the permanent story archive and '
            'cannot be deleted. Archive it instead.')
    article.delete()
