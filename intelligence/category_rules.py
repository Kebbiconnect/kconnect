"""Rule-based category suggestions for raw publications (Phase 3).

A deliberately small, auditable keyword table over the blueprint's 22
intelligence categories (Doc 06 Phase 2: "category rules (keyword-based,
multi-category)"). Matching runs on normalised text with word
boundaries. A category is suggested only when the evidence is real:

- a STRONG term hit anywhere, or
- any term hit in the title, or
- two or more distinct term hits in the body.

Otherwise the item is left uncategorised rather than guessed at. The
``other`` category is never auto-suggested: it is a human fallback,
not a rule outcome. Every suggestion stores the terms that fired as
its reason. Title hits score 2, body hits 1; the highest-scoring
suggestion is primary.
"""
from .models import normalize_alias

# slug -> {'strong': [...], 'terms': [...]} (phrases are normalised
# before matching, so write them in plain lowercase words).
RULES = {
    'government-governance': {
        'strong': ['executive council', 'house of assembly'],
        'terms': ['governor', 'government', 'ministry', 'commissioner',
                  'permanent secretary', 'local government chairman',
                  'state government', 'secretary to the state government',
                  'head of service', 'cabinet'],
    },
    'politics-elections': {
        'strong': ['inec', 'election tribunal', 'campaign rally'],
        'terms': ['election', 'candidate', 'campaign', 'ballot', 'voters',
                  'political party', 'primaries', 'apc', 'pdp', 'adc',
                  'senatorial', 'running mate', 'defection', 'ward congress'],
    },
    'security-public-safety': {
        'strong': ['bandits', 'kidnapped', 'kidnapping', 'gunmen', 'nscdc'],
        'terms': ['police', 'abducted', 'abduction', 'army', 'military',
                  'troops', 'attack', 'vigilante', 'dss', 'civil defence',
                  'security operatives', 'rustled', 'cattle rustling',
                  'terrorism', 'insurgency'],
    },
    'education': {
        'strong': ['waec', 'neco', 'jamb', 'subeb'],
        'terms': ['school', 'schools', 'students', 'teachers', 'university',
                  'polytechnic', 'classroom', 'classrooms', 'education board',
                  'pupils', 'lecturers', 'academic', 'examination'],
    },
    'healthcare': {
        'strong': ['cholera', 'immunisation', 'immunization', 'malaria'],
        'terms': ['hospital', 'hospitals', 'vaccine', 'vaccines', 'doctors',
                  'nurses', 'primary healthcare', 'clinic', 'clinics',
                  'disease', 'patients', 'health workers',
                  'medical'],
        # Bare 'outbreak' is deliberately absent: "fire outbreak"
        # stories matched it and picked up a wrong Healthcare
        # suggestion. Disease coverage still fires via 'disease',
        # 'cholera', 'malaria' and 'immunisation'.
    },
    'agriculture-food-security': {
        'strong': ['fertiliser', 'fertilizer', 'dry season farming'],
        'terms': ['farmers', 'crops', 'harvest', 'irrigation', 'livestock',
                  'cattle', 'grains', 'food prices', 'agriculture',
                  'agricultural', 'farmland', 'herders', 'farming'],
    },
    'infrastructure-roads': {
        'strong': ['flyover', 'dualisation', 'dualization'],
        'terms': ['road', 'roads', 'bridge', 'construction', 'contractor',
                  'contractors', 'township roads', 'project commissioning',
                  'infrastructure', 'rehabilitation of', 'flagged off'],
    },
    'water-sanitation': {
        'strong': ['borehole', 'boreholes'],
        'terms': ['water supply', 'sanitation', 'water project',
                  'water scheme', 'reticulation', 'hand pump', 'toilets'],
    },
    'electricity-energy': {
        'strong': ['transformer', 'national grid'],
        'terms': ['electricity', 'power supply', 'solar', 'metering',
                  'disco', 'rural electrification', 'generator'],
    },
    'economy-employment': {
        'strong': ['unemployment rate'],
        'terms': ['jobs', 'employment', 'unemployment', 'traders',
                  'market prices', 'inflation', 'smes', 'business owners',
                  'economic', 'economy', 'internally generated revenue'],
    },
    'business-investment': {
        'strong': ['memorandum of understanding'],
        'terms': ['investment', 'investors', 'investor', 'company', 'factory',
                  'industry', 'industries', 'partnership', 'business summit'],
    },
    'environment-climate': {
        'strong': ['desertification', 'erosion control'],
        'terms': ['climate', 'environment', 'tree planting', 'rainfall',
                  'windstorm', 'erosion', 'waste management', 'sanitation exercise'],
    },
    'community-development': {
        'strong': ['community development'],
        'terms': ['community', 'communities', 'town hall', 'development association',
                  'community leaders', 'youth association', 'cooperative society'],
    },
    'human-rights-justice': {
        'strong': ['arraigned', 'human rights'],
        'terms': ['court', 'judge', 'remand', 'detention', 'prison',
                  'inmates', 'legal aid', 'judiciary', 'magistrate',
                  'high court', 'sharia court'],
    },
    'youth-sports': {
        'strong': ['super eagles', 'football tournament'],
        'terms': ['football', 'match', 'league', 'tournament', 'youth',
                  'youths', 'athletes', 'stadium', 'sports festival',
                  'coaches'],
    },
    'women-social-development': {
        'strong': ['girl child'],
        'terms': ['women', 'widows', 'orphans', 'maternal', 'women groups',
                  'women empowerment', 'female', 'girls'],
    },
    'public-accountability': {
        'strong': ['efcc', 'icpc', 'corruption'],
        'terms': ['audit', 'probe', 'petition', 'accountability',
                  'recovered funds', 'anti corruption', 'transparency',
                  'contract scam', 'diversion', 'allegations'],
    },
    'traditional-institutions': {
        'strong': ['emir', 'turbaning'],
        'terms': ['traditional ruler', 'traditional rulers', 'district head',
                  'palace', 'durbar', 'emirate', 'royal father'],
    },
    'humanitarian-affairs': {
        'strong': ['nema', 'relief materials', 'idp', 'idps'],
        'terms': ['displaced', 'refugees', 'orphanage', 'donations',
                  'humanitarian', 'relief', 'sema', 'vulnerable households'],
    },
    'emergencies-disasters': {
        'strong': ['boat mishap', 'building collapsed', 'fire outbreak'],
        'terms': ['flood', 'flooding', 'accident', 'explosion', 'emergency',
                  'disaster', 'rescue', 'collapsed', 'inferno'],
    },
    'opportunities-scholarships': {
        'strong': ['scholarship', 'scholarships', 'fellowship'],
        'terms': ['grant', 'grants', 'empowerment programme',
                  'empowerment program', 'training programme',
                  'training program', 'recruitment', 'applications are invited',
                  'beneficiaries'],
    },
}


def _hits(padded_title, padded_body, phrases):
    found = []
    for phrase in phrases:
        term = normalize_alias(phrase)
        if not term:
            continue
        if f' {term} ' in padded_title:
            found.append((phrase, 'title'))
        elif f' {term} ' in padded_body:
            found.append((phrase, 'body'))
    return found


def suggest_categories(title, summary, text):
    """Return [{slug, score, reason}] for the categories the rules support."""
    padded_title = f' {normalize_alias(title)} '
    padded_body = f' {normalize_alias(f"{summary} {text}")} '
    suggestions = []
    for slug, rule in RULES.items():
        strong = _hits(padded_title, padded_body, rule.get('strong', []))
        terms = _hits(padded_title, padded_body, rule.get('terms', []))
        title_hits = [h for h in strong + terms if h[1] == 'title']
        body_hits = [h for h in strong + terms if h[1] == 'body']
        qualifies = bool(strong) or bool(title_hits) or len(body_hits) >= 2
        if not qualifies:
            continue
        score = 2 * len(title_hits) + len(body_hits) + 2 * len(strong)
        fired = ', '.join(
            f"'{phrase}' ({where})" for phrase, where in strong + terms)
        suggestions.append({
            'slug': slug, 'score': score,
            'reason': f'Keywords matched: {fired}'[:300],
        })
    suggestions.sort(key=lambda s: (-s['score'], s['slug']))
    return suggestions
