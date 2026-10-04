"""Evidence annotations; workflow status is deliberately outside this schema."""
import re
from datetime import datetime
from urllib.parse import urlsplit

ASSESSMENTS = ('unresolved', 'industrial_heat', 'suspected_fire',
               'agricultural_burning', 'false_positive')
ASSESSMENT_FIELDS = {'assessment', 'supportingSources', 'uncertainty', 'assessedAt'}


def bounded_text(value, limit):
    # Match browser string length, including supplementary Unicode characters.
    return isinstance(value, str) and len(value.encode('utf-16-le', errors='surrogatepass')) // 2 <= limit


def safe_source(value):
    if not bounded_text(value, 2048) or not value.strip():
        return False
    if re.search(r'[\x00-\x1f\x7f-\x9f]', value):
        return False
    source = value.strip()
    if source.startswith('//') or '\\' in source:
        return False
    if not re.match(r'^[a-z][a-z0-9+.-]*:', source, re.I):
        return True
    if not re.match(r'^https?://', source, re.I):
        return False
    try:
        url = urlsplit(source)
        host = url.hostname
        port = url.port
        return bool(host) and not re.search(r'[\s%]', host) and url.username is None and url.password is None and (port is None or 0 <= port <= 65535)
    except ValueError:
        return False


def iso_time(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})', value):
        raise ValueError('Expected timezone-qualified ISO timestamp')
    if value[-1] != 'Z' and (int(value[-5:-3]) >= 24 or int(value[-2:]) >= 60):
        raise ValueError('Invalid timezone offset')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Expected timezone-qualified ISO timestamp')
    return parsed


def validate_assessment(row):
    assessment = row.get('assessment', 'unresolved')
    sources = row.get('supportingSources', [])
    uncertainty = row.get('uncertainty', '')
    assessed_at = row.get('assessedAt')
    if assessment not in ASSESSMENTS or not isinstance(sources, list) or len(sources) > 8:
        raise ValueError('Invalid assessment or supporting sources')
    if not all(safe_source(source) for source in sources):
        raise ValueError('Expected bounded safe source URLs or text')
    if not bounded_text(uncertainty, 1000):
        raise ValueError('Invalid uncertainty')
    if assessed_at is not None:
        iso_time(assessed_at)
    if assessment != 'unresolved' and (not sources or not uncertainty.strip() or assessed_at is None):
        raise ValueError('Assessment requires sources, uncertainty and assessedAt')
