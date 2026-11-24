"""Server-rendered chart data for authenticated dashboards
(Consistency Completion Rounds C+D).

Every figure here is computed from records the viewing role already
accesses on the page that renders the chart — these helpers only shape
querysets the caller passes in; they never widen data access. Charts
are inline SVG built in the templates from the dicts below: no
JavaScript chart libraries (low-bandwidth rule), no invented numbers.

- ``bar_rows``   — horizontal bars: label, value, % of the max value.
- ``donut_rows`` — donut segments with precomputed SVG stroke geometry.
- ``member_lga_map`` — the viewing member's own LGA on the validated
  HDX Kebbi geometry (``intelligence.map_data``), neighbours pale.
"""
import math

from django.db.models import Count

# Brand palette for chart series (kpn-design tokens).
PALETTE = (
    '#176b36',  # action green
    '#28a745',  # brand green
    '#d99a16',  # restrained gold
    '#57bd78',  # light green
    '#6b7280',  # muted grey
    '#c2410c',  # warm rust (small residual slices only)
)


def bar_rows(pairs):
    """Shape ``[(label, value), ...]`` into horizontal-bar rows."""
    pairs = [(label, int(value)) for label, value in pairs]
    top = max((value for _, value in pairs), default=0)
    return [
        {
            'label': label,
            'value': value,
            'pct': round(value * 100 / top) if top else 0,
        }
        for label, value in pairs
    ]


def donut_rows(pairs, radius=40):
    """Shape ``[(label, value), ...]`` into SVG donut segments.

    Segments use stroke-dasharray on a circle; offsets accumulate so
    each segment starts where the previous ended. Zero-value pairs are
    kept in the legend (honest zeros) but draw nothing.
    """
    pairs = [(label, int(value)) for label, value in pairs]
    total = sum(value for _, value in pairs)
    circumference = 2 * math.pi * radius
    rows = []
    offset = circumference * 0.25  # start at twelve o'clock
    for index, (label, value) in enumerate(pairs):
        length = circumference * value / total if total else 0
        rows.append({
            'label': label,
            'value': value,
            'pct': round(value * 100 / total) if total else 0,
            'color': PALETTE[index % len(PALETTE)],
            'dash': f'{length:.2f} {circumference - length:.2f}',
            'offset': f'{-offset:.2f}',
            'circumference': f'{circumference:.2f}',
        })
        offset += length
    return {'total': total, 'rows': rows}


def count_by(qs, field, choices=None):
    """``[(label, count), ...]`` for ``field`` over ``qs``.

    With ``choices`` given, every choice appears (zero-filled, in
    choice order); otherwise only present values, largest first.
    """
    counts = {
        row[field]: row['n']
        for row in qs.values(field).annotate(n=Count('id'))
    }
    if choices:
        return [(label, counts.get(value, 0)) for value, label in choices]
    return sorted(counts.items(), key=lambda pair: -pair[1])


def member_lga_map(user):
    """The member's own LGA geometry for the single-LGA highlight map.

    Returns None when the member has no LGA on record or the LGA has
    no validated geometry. Neighbour paths are drawn pale so the
    member can place their LGA inside Kebbi State.
    """
    lga = getattr(user, 'lga', None)
    if lga is None:
        return None
    from intelligence.map_data import LGA_GEOMETRY, VIEWBOX

    own = LGA_GEOMETRY.get(lga.name)
    if own is None:
        return None
    return {
        'viewbox': VIEWBOX,
        'own': own,
        'own_name': lga.name,
        'neighbours': [
            {'name': name, 'd': geom['d']}
            for name, geom in LGA_GEOMETRY.items()
            if name != lga.name
        ],
    }
