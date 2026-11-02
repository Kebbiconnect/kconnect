"""Story Intelligence services: Story ID allocation, verification
history, the public story panel, and the emergency redaction workflow.

Design rules (architectural assessment §7.5/§7.7):
- A PUBLISHED article must always carry a Story ID. Allocation happens
  inside the publish transaction; if it fails, the publish rolls back
  and the article stays in its previous, recoverable state.
- Audit and correction records describe editorial ACTIONS only. They
  must never copy confidential source text, personal data, or the
  material that was redacted.
"""
import os

from django.db import transaction
from django.utils import timezone

from .models import (
    Claim, Correction, Promise, PromiseUpdate, StoryAudit, StorySequence,
    StorySourceLink, VerificationEvent,
)

STORY_ID_PREFIX = 'KPN-SI'
REDACTION_MARKER = '[Redacted by the KPN editorial team for privacy and safety reasons.]'

REDACTION_REASON_CATEGORIES = [
    ('PERSONAL_DATA', 'Personal data exposed'),
    ('SAFETY', 'Safety of a person'),
    ('LEGAL', 'Legal requirement'),
    ('CONSENT_WITHDRAWN', 'Consent withdrawn'),
    ('OTHER', 'Other (recorded internally)'),
]


class StoryAllocationError(Exception):
    """Raised when a permanent Story ID cannot be allocated."""


class RedactionError(Exception):
    """Raised when a redaction cannot be completed safely (for example
    when the underlying stored file could not be confirmed removed)."""


class PromiseError(Exception):
    """Raised when a promise status change is not allowed — most
    importantly, when COMPLETED_VERIFIED is attempted without the
    VERIFY_PROMISES capability or without verification evidence."""


class ConsentRequiredError(Exception):
    """Raised when publication is blocked by the Human Impact consent
    guard (Phase 4): the story features identifiable people but no
    consent record is on file. Raised inside the publish transaction,
    so the publish rolls back and the article keeps its prior state."""


# ─── Human Impact consent guard (Phase 4) ─────────────────────────────────────

def consent_block_reason(article):
    """Why publishing this article is blocked by the consent guard —
    or '' when publication may proceed.

    The guard applies ONLY to a Human Impact File (StoryProfile
    kind == 'IMPACT') that an editor has flagged as featuring
    identifiable people. Such a story may not be published until at
    least one live ConsentRecord is on file for it (any basis,
    including an editor-recorded NOT_REQUIRED basis). Anonymised
    impact files (flag off), ordinary stories, and articles with no
    story profile are never blocked. Consent record CONTENTS are
    never read here — only their existence is checked.
    """
    profile = getattr(article, 'story_profile', None)
    if profile is None or not getattr(profile, 'pk', None):
        return ''
    if profile.kind != 'IMPACT' or not profile.features_identifiable_people:
        return ''
    if profile.consent_on_file():
        return ''
    return ('This Human Impact story features identifiable people, but '
            'no consent record is on file for it. Record consent in the '
            'story desk before publishing — or, if the people in the '
            'story cannot be identified, remove the '
            '"features identifiable people" flag on the story profile.')


def ensure_consent_for_publish(article):
    """Raise ConsentRequiredError when the consent guard blocks this
    article. Called inside every publish transaction (newsroom service,
    brain publish, editorial handoff, archive restore) BEFORE the
    article's state changes, so a blocked publish changes nothing."""
    reason = consent_block_reason(article)
    if reason:
        raise ConsentRequiredError(reason)


# ─── Allocation ───────────────────────────────────────────────────────────────

def format_story_id(year, number):
    return f'{STORY_ID_PREFIX}-{year:04d}-{number:05d}'


def allocate_story_id(article, actor=None):
    """Allocate (or return the existing) permanent Story ID for an article.

    MUST be called inside the caller's transaction (all publish paths
    are transactional). Locks the per-year StorySequence row with
    select_for_update() so concurrent publishes serialise on it. The
    caller saves the article; if the save fails (e.g. unique conflict),
    the caller's transaction rolls everything back, including the
    sequence increment, leaving the article unpublished and recoverable.
    """
    if article.story_id:
        return article.story_id
    year = (article.published_at or timezone.now()).year
    StorySequence.objects.get_or_create(year=year)
    sequence = StorySequence.objects.select_for_update().get(year=year)
    sequence.last_number += 1
    sequence.save(update_fields=['last_number'])
    article.story_id = format_story_id(year, sequence.last_number)
    return article.story_id


# ─── Audit ────────────────────────────────────────────────────────────────────

def log_audit(actor, action, target_type, target_id, detail=None):
    """Write a StoryAudit entry. `detail` must contain identifiers and
    action metadata only — never sensitive content (see module docstring)."""
    return StoryAudit.objects.create(
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action=action, target_type=target_type, target_id=target_id,
        detail=detail or {})


# ─── Verification history (Truth Layers) ──────────────────────────────────────

def record_verification_event(article, new_value, actor, field='article_verification_status',
                              claim=None, old_value='', reason=''):
    return VerificationEvent.objects.create(
        article=article, claim=claim, field=field,
        old_value=old_value or '', new_value=new_value,
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        reason=(reason or '')[:300])


@transaction.atomic
def set_article_verification_status(article, new_status, actor, reason=''):
    from campaigns.models import Campaign
    if new_status not in dict(Campaign.VERIFICATION_STATUS_CHOICES):
        raise ValueError('Unknown verification status.')
    old = article.verification_status
    if old == new_status:
        return article
    article.verification_status = new_status
    article.save(update_fields=['verification_status', 'updated_at'])
    record_verification_event(article, new_status, actor, old_value=old, reason=reason)
    log_audit(actor, 'ARTICLE_VERIFICATION_CHANGED', 'campaign', article.pk,
              {'from': old, 'to': new_status})
    return article


@transaction.atomic
def set_claim_status(claim, new_status, actor, reason=''):
    if new_status not in dict(Claim.STATUS_CHOICES):
        raise ValueError('Unknown claim status.')
    old = claim.status
    if old == new_status:
        return claim
    claim.status = new_status
    claim.save(update_fields=['status', 'updated_at'])
    record_verification_event(
        claim.article, new_status, actor, field='claim_status',
        claim=claim, old_value=old, reason=reason)
    log_audit(actor, 'CLAIM_STATUS_CHANGED', 'claim', claim.pk,
              {'article_id': claim.article_id, 'from': old, 'to': new_status})
    return claim


# ─── Public story panel ───────────────────────────────────────────────────────

def story_panel_context(article):
    """Public, reader-safe story data for the article page.

    Returns None when the article has no story data at all, so the page
    renders exactly as before for ordinary articles. NEVER includes
    consent records, audit entries, draft updates, or private evidence.
    """
    profile = getattr(article, 'story_profile', None)
    if profile is not None and not profile.pk:
        profile = None
    updates = list(article.story_updates.filter(status='PUBLISHED'))
    claims = list(article.claims.all())
    evidence = list(article.evidence_records.filter(is_public=True))
    corrections = list(article.corrections.filter(published=True))
    community_sources = community_attribution(article)
    # Phase 4: a Future Signal links to the published stories it is
    # based on; only PUBLISHED stories are ever linked publicly.
    related_stories = []
    if profile is not None and profile.kind == 'SIGNAL':
        related_stories = list(
            profile.related_stories.filter(status='PUBLISHED')
            .order_by('-published_at'))
    has_profile = bool(profile and profile.has_content())
    if not (article.story_id or has_profile or updates or claims or evidence
            or corrections or community_sources):
        return None
    return {
        'story_id': article.story_id,
        'profile': profile if has_profile else None,
        'updates': updates,
        'claims': claims,
        'evidence': evidence,
        'corrections': corrections,
        'community_sources': community_sources,
        'related_stories': related_stories,
    }


# ─── Emergency redaction ──────────────────────────────────────────────────────

def _cloudinary_public_id(field_file):
    """Public id for a stored file: its storage name minus the extension."""
    name = getattr(field_file, 'name', '') or ''
    root, _ext = os.path.splitext(name)
    return root


def _destroy_cloudinary_object(public_id):
    """Destroy an object in Cloudinary and verify the provider response.

    Returns 'ok' when the provider confirms removal, 'not found' when
    the object was already gone. Raises RedactionError otherwise — a
    redaction must never claim a file is gone when it is not.
    """
    import cloudinary.uploader
    try:
        response = cloudinary.uploader.destroy(public_id)
    except Exception as exc:  # provider unreachable / misconfigured
        raise RedactionError(f'cloudinary_destroy_failed: {exc.__class__.__name__}')
    result = (response or {}).get('result')
    if result in ('ok', 'not found'):
        return result
    raise RedactionError(f'cloudinary_destroy_unverified: {result!r}')


@transaction.atomic
def perform_redaction(*, actor, target_type, target_id, reason_category):
    """Immediately redact sensitive material from one story record.

    target_type: 'article' | 'update' | 'claim' | 'evidence'.
    For records carrying an uploaded file, the underlying Cloudinary
    object is destroyed and the provider response verified BEFORE the
    database is updated; if removal cannot be confirmed, RedactionError
    is raised and nothing is changed. The Correction + StoryAudit
    records describe the action and the reason CATEGORY only — the
    sensitive material itself is never copied into them.
    """
    if reason_category not in dict(REDACTION_REASON_CATEGORIES):
        raise RedactionError('unknown_reason_category')

    from campaigns.models import Campaign
    from .models import EvidenceRecord, StoryUpdate

    article = None
    update = claim = evidence = None
    file_public_id = ''
    if target_type == 'article':
        article = Campaign.objects.get(pk=target_id)
        if article.featured_image:
            file_public_id = _cloudinary_public_id(article.featured_image)
    elif target_type == 'update':
        update = StoryUpdate.objects.select_related('article').get(pk=target_id)
        article = update.article
    elif target_type == 'claim':
        claim = Claim.objects.select_related('article').get(pk=target_id)
        article = claim.article
    elif target_type == 'evidence':
        evidence = EvidenceRecord.objects.select_related('article').get(pk=target_id)
        article = evidence.article
        if evidence.file:
            file_public_id = _cloudinary_public_id(evidence.file)
    else:
        raise RedactionError('unknown_target_type')

    file_result = None
    if file_public_id:
        # Verify removal first: if this raises, the transaction has not
        # changed anything and the record still points at the file.
        file_result = _destroy_cloudinary_object(file_public_id)

    if target_type == 'article':
        article.content = REDACTION_MARKER
        article.content_json = {'blocks': [
            {'type': 'paragraph', 'data': {'text': REDACTION_MARKER}}]}
        fields = ['content', 'content_json', 'updated_at']
        if file_public_id:
            article.featured_image = None
            fields.append('featured_image')
        article.save(update_fields=fields)
    elif target_type == 'update':
        update.body = REDACTION_MARKER
        update.save(update_fields=['body', 'updated_at'])
    elif target_type == 'claim':
        claim.text = REDACTION_MARKER
        claim.save(update_fields=['text', 'updated_at'])
    elif target_type == 'evidence':
        evidence.title = 'Redacted evidence'
        evidence.description = REDACTION_MARKER
        evidence.url = ''
        fields = ['title', 'description', 'url']
        if evidence.file:
            evidence.file = None
            fields.append('file')
        evidence.save(update_fields=fields)

    reason_label = dict(REDACTION_REASON_CATEGORIES)[reason_category]
    correction = Correction.objects.create(
        article=article, update=update, claim=claim,
        kind='REDACTION', published=True, created_by=actor,
        text=(f'Part of this story was removed by the KPN editorial team '
              f'({reason_label.lower()}). The original material is no '
              f'longer published.'))
    log_audit(actor, 'REDACTION_PERFORMED', target_type, target_id, {
        'article_id': article.pk,
        'story_id': article.story_id,
        'reason_category': reason_category,
        'file_removal': file_result,  # 'ok' / 'not found' / None (no file)
        'correction_id': correction.pk,
    })
    return {
        'article_id': article.pk,
        'target_type': target_type,
        'target_id': target_id,
        'file_removal': file_result,
        'correction_id': correction.pk,
    }


# ─── Phase 2: Promise Tracker services ────────────────────────────────────────

def _check_verified_completion(promise, actor, incoming_evidence=False):
    """The COMPLETED_VERIFIED guard, shared by every status path.

    `incoming_evidence` is True when the very update that requests the
    status carries its own evidence link — that evidence counts, so an
    editor can attach proof and mark verified in one step.
    """
    from leadership.capabilities import capabilities_for
    if 'VERIFY_PROMISES' not in capabilities_for(actor):
        raise PromiseError('missing_verify_capability')
    if not (incoming_evidence or promise.has_verification_evidence()):
        raise PromiseError('verified_completion_requires_evidence')


@transaction.atomic
def set_promise_status(promise, new_status, actor, note=''):
    """Change a promise's status, recording the change in history.

    The change is written as a PromiseUpdate row (status_after set) and
    a StoryAudit entry, so the public timeline and the internal audit
    always agree. COMPLETED_VERIFIED is refused — with nothing saved —
    unless the actor holds VERIFY_PROMISES and verification evidence
    is on record (see Promise.has_verification_evidence).
    """
    if new_status not in dict(Promise.STATUS_CHOICES):
        raise PromiseError('unknown_promise_status')
    old = promise.status
    if old == new_status:
        return promise
    if new_status == 'COMPLETED_VERIFIED':
        _check_verified_completion(promise, actor)
    promise.status = new_status
    promise.save(update_fields=['status', 'updated_at'])
    PromiseUpdate.objects.create(
        promise=promise, update_date=timezone.localdate(),
        title=f'Status changed to {promise.get_status_display()}',
        body=(note or '')[:2000], status_after=new_status, author=actor)
    log_audit(actor, 'PROMISE_STATUS_CHANGED', 'promise', promise.pk,
              {'from': old, 'to': new_status})
    return promise


@transaction.atomic
def record_promise_update(promise, actor, *, update_date, title, body='',
                          evidence_title='', evidence_url='', new_status=''):
    """Record a progress update, optionally moving the status.

    When `new_status` is given, the move goes through the same guard
    as set_promise_status (COMPLETED_VERIFIED included) BEFORE
    anything is written; the update row itself then documents the new
    status, so no separate status row is created.
    """
    status_after = ''
    if new_status and new_status != promise.status:
        if new_status not in dict(Promise.STATUS_CHOICES):
            raise PromiseError('unknown_promise_status')
        if new_status == 'COMPLETED_VERIFIED':
            _check_verified_completion(
                promise, actor, incoming_evidence=bool(evidence_url))
        old = promise.status
        promise.status = new_status
        promise.save(update_fields=['status', 'updated_at'])
        status_after = new_status
        log_audit(actor, 'PROMISE_STATUS_CHANGED', 'promise', promise.pk,
                  {'from': old, 'to': new_status, 'via': 'update'})
    update = PromiseUpdate.objects.create(
        promise=promise, update_date=update_date, title=title, body=body,
        status_after=status_after, evidence_title=evidence_title,
        evidence_url=evidence_url, author=actor)
    log_audit(actor, 'PROMISE_UPDATE_ADDED', 'promise_update', update.pk,
              {'promise_id': promise.pk, 'status_after': status_after})
    return update


# ─── Phase 2: Community Radar services ────────────────────────────────────────

@transaction.atomic
def link_report_to_story(report, article, kind, actor):
    """Link a community report to a story (manual, editorial only).

    Linking never changes the report itself, its status, or any claim
    status: a community submission is not a verified claim.
    """
    if kind not in dict(StorySourceLink.KIND_CHOICES):
        raise ValueError('Unknown link kind.')
    link, created = StorySourceLink.objects.get_or_create(
        report=report, article=article,
        defaults={'kind': kind, 'linked_by': actor})
    if created:
        log_audit(actor, 'REPORT_LINKED_TO_STORY', 'story_source_link', link.pk,
                  {'report_id': report.pk, 'article_id': article.pk, 'kind': kind})
    return link, created


@transaction.atomic
def unlink_report_from_story(link, actor):
    report_id, article_id = link.report_id, link.article_id
    link.delete()
    log_audit(actor, 'REPORT_UNLINKED_FROM_STORY', 'story_source_link', None,
              {'report_id': report_id, 'article_id': article_id})


@transaction.atomic
def create_claim_from_report(link, actor):
    """Record a story claim based on a linked community report.

    The claim ALWAYS starts NOT_ESTABLISHED: a community submission
    must never become a verified claim automatically. Editors raise it
    later through the normal claim-status workflow, with evidence.
    """
    report = link.report
    claim = Claim.objects.create(
        article=link.article, text=report.what_happened,
        status='NOT_ESTABLISHED', source_name='KPN community report',
        noted_by=actor)
    log_audit(actor, 'CLAIM_CREATED_FROM_REPORT', 'claim', claim.pk,
              {'article_id': link.article_id, 'report_id': report.pk,
               'status': claim.status})
    return claim


def community_attribution(article):
    """Public-safe attribution labels for a story's community sources.

    Returns geography labels (e.g. an LGA name) for APPROVED linked
    reports only — never a reporter's name, phone number, location
    details or report text.
    """
    labels = []
    links = (StorySourceLink.objects
             .filter(article=article, report__status='APPROVED')
             .select_related('report__lga', 'report__ward__lga', 'report__zone'))
    for link in links:
        report = link.report
        label = None
        if report.lga_id:
            label = report.lga.name
        elif report.ward_id and report.ward.lga_id:
            label = report.ward.lga.name
        elif report.zone_id:
            label = report.zone.name
        if label and label not in labels:
            labels.append(label)
    return labels
