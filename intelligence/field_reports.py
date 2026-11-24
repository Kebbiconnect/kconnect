"""Field reporting intake (Phase 7).

A field report becomes a :class:`RawPublication` under the MANUAL
field source, so it is processed, clustered and worked at the
verification desk exactly like monitored material — there is no
separate field-report workflow for the desk to learn. Two facts the
reporter states first-hand are recorded as first-class evidence and
are never left for the engines to guess:

- the LGA — a MANUAL :class:`PublicationLocation` row (the engines
  preserve MANUAL rows verbatim) plus, when the text scan alone
  would miss it, a CONFIRMED classification carrying an attestation
  reason naming the reporter's own recording;
- the category — after processing, the reporter's chosen category
  is the item's primary category link, so the Phase 6 restriction
  rules (which key off the primary category) apply to sensitive
  field reports automatically.

Everything after intake is failure-isolated in the same way as the
collection cycle: a processing error never loses the submission —
the record stays stored and the next cycle's ``process_pending``
picks it up.
"""
from django.db import transaction
from django.utils import timezone

from editorial.models import Source

from .connectors import MAX_TEXT_CHARS, _fingerprint
from .models import (
    FieldReport, IntelligenceAudit, PublicationCategory,
    PublicationLocation, RawPublication,
)

FIELD_SOURCE_NAME = 'Field Reports'

# Reporter-facing wording for the desk states their submission can
# reach. The desk's own vocabulary stays on the desk; reporters see
# the outcome of their report, in plain terms.
STATUS_LABELS = {
    'DISCOVERED': 'Submitted — awaiting review',
    'UNDER_REVIEW': 'In review',
    'VERIFICATION_IN_PROGRESS': 'In review',
    'NEEDS_INFO': 'More evidence requested',
    'VERIFIED': 'Verified',
    'DISPUTED': 'Disputed — under discussion',
    'UNVERIFIED': 'Verification withdrawn',
    'APPROVED': 'Approved — awaiting publication',
    'PUBLISHED': 'Published',
    'REJECTED': 'Not taken forward',
    'DUPLICATE': 'Duplicate of another report',
    'RESTRICTED': 'With the security desk',
    'ARCHIVED': 'Archived',
}


def field_source():
    """The one MANUAL source all field reports are filed under."""
    source, _created = Source.objects.get_or_create(
        name=FIELD_SOURCE_NAME, connector_kind='MANUAL',
        defaults={
            'kind': 'NEWS',
            'url': 'https://www.kpn.com.ng/editorial/intelligence/field/',
            'feed': False,
            'enabled': False,
        })
    return source


def report_desk_state(report):
    """The desk state of the unit a field report belongs to."""
    pub = report.publication
    if pub is None:
        return 'DISCOVERED'
    if pub.cluster_id:
        return pub.cluster.desk_state
    return pub.desk_state


def report_status_label(report):
    return STATUS_LABELS.get(report_desk_state(report),
                             report_desk_state(report))


@transaction.atomic
def _create_records(reporter, *, headline, text, lga, category,
                    occurred_at, photo):
    report = FieldReport.objects.create(
        reporter=reporter, headline=headline[:300], report_text=text,
        lga=lga, category=category, occurred_at=occurred_at, photo=photo)
    pub = RawPublication.objects.create(
        source=field_source(),
        canonical_url=f'field-report:{report.pk}',
        original_url='',
        title=headline[:300],
        summary='',
        text=(text or '')[:MAX_TEXT_CHARS],
        published_at=occurred_at,
        discovered_at=timezone.now(),
        fetch_status='CONTENT',
        content_fingerprint=_fingerprint(headline or '', text or ''),
        raw_metadata={'field_report': True, 'field_report_id': report.pk})
    report.publication = pub
    report.save(update_fields=['publication'])
    # The reporter's own LGA, recorded as manual evidence: the
    # processing engines never delete MANUAL location rows.
    PublicationLocation.objects.create(
        publication=pub, lga=lga, match_kind='MANUAL',
        matched_text='Recorded by the field reporter', confidence=1.0)
    return report, pub


def _make_chosen_category_primary(pub, category):
    """The reporter's chosen category governs the primary link.

    The engines attach their own suggestions during processing; the
    category the reporter selected on the form is a first-hand
    editorial fact, so it becomes (or stays) primary — this is also
    what makes the Phase 6 sensitive-category restriction apply to
    field reports without any special case.
    """
    links = PublicationCategory.objects.filter(publication=pub)
    chosen = links.filter(category=category).first()
    links.exclude(pk=chosen.pk if chosen else None).update(is_primary=False)
    if chosen is None:
        PublicationCategory.objects.create(
            publication=pub, category=category, is_primary=True,
            reason='Category selected by the field reporter.')
    elif not chosen.is_primary:
        chosen.is_primary = True
        chosen.save(update_fields=['is_primary'])


def _apply_attestation(pub, lga):
    """Lift a weak text-only classification on the reporter's word.

    Only ever lifts (NOT_RELEVANT / UNCERTAIN → CONFIRMED): the
    reporter recorded the report in this LGA in person, which is an
    explicit first-hand signal. ``relevance_manual`` is NOT set —
    the engines may still reprocess the item later; the MANUAL
    location row survives regardless.
    """
    if pub.relevance not in ('NOT_RELEVANT', 'UNCERTAIN'):
        return
    reasons = list(pub.relevance_reasons or [])
    reasons.append({
        'rule': 'field_reporter_attestation', 'kind': 'MANUAL',
        'detail': f'The field reporter recorded this report in '
                  f'{lga.name} LGA.',
        'entity_kind': 'LGA', 'entity': str(lga),
        'matched_text': 'Field report', 'where': 'form'})
    pub.relevance = 'CONFIRMED'
    pub.relevance_reasons = reasons
    pub.save(update_fields=['relevance', 'relevance_reasons'])


def _post_process(pub, report):
    """The same downstream steps the collection cycle applies.

    Mirrors ``relevance.process_pending``'s per-item tail: promise
    detection and the sensitive-category alert, each in its own
    isolation boundary so neither can fail the submission.
    """
    try:
        from . import promise_detection
        promise_detection.detect_for_publication(pub)
    except Exception:  # detection must never fail a submission
        pass
    try:
        if pub.relevance == 'CONFIRMED':
            primary = (pub.category_links.filter(is_primary=True)
                       .select_related('category').first())
            if primary is not None and primary.category.is_sensitive:
                from . import alerts as alert_service
                alert_service.fire_sensitive_confirmed(pub)
    except Exception:  # alerting must never fail a submission
        pass


def submit_field_report(reporter, *, headline, text, lga, category,
                        occurred_at, photo=None):
    """File one field report and run it into the pipeline.

    Returns the :class:`FieldReport`. The intake record exists even
    if processing fails — the failure is isolated and the collection
    cycle retries unprocessed items on its own schedule.
    """
    report, pub = _create_records(
        reporter, headline=headline, text=text, lga=lga,
        category=category, occurred_at=occurred_at, photo=photo)
    try:
        from . import relevance as relevance_service
        relevance_service.process_publication(pub)
        pub.refresh_from_db()
        _make_chosen_category_primary(pub, category)
        _apply_attestation(pub, lga)
    except Exception:  # processing is retried by the cycle; never lose intake
        pass
    else:
        _post_process(pub, report)
    IntelligenceAudit.objects.create(
        actor=reporter, action='FIELD_REPORT_SUBMITTED',
        target_type='RawPublication', target_id=pub.pk,
        detail={'field_report_id': report.pk, 'lga_id': lga.pk,
                'category_id': category.pk})
    return report
