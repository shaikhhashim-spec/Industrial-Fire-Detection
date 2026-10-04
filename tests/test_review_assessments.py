import json

import pytest
from starlette.testclient import TestClient

from src.review_schema import iso_time, safe_source
from src.server import Backend, create_server
from src.server.security import Actor


def assessment(**overrides):
    return {'status': 'reviewed', 'assessment': 'industrial_heat',
            'supportingSources': ['https://example.org/report', 'Field report 123'],
            'uncertainty': 'Exact combustion source uncertain',
            'assessedAt': '2026-10-03T00:00:00.000Z', **overrides}


def test_review_evidence_persists_with_audit_and_restart(tmp_path):
    path = str(tmp_path / 'reviews.db')
    actor = Actor('admin', 'admin')
    first = Backend(path, admin_username='admin', admin_password='test-only-password-123')
    row = assessment(status='unreviewed')
    try:
        assert first.put_review('india', 'event', actor, {'version': 0, 'review': row})['review'] == row
        with first.db.transaction():
            audit = first.db.execute('SELECT payload FROM audit WHERE event_id=?', ('event',)).fetchone()
        assert json.loads(audit['payload']) == row
    finally:
        first.close()
    second = Backend(path, admin_username='admin', admin_password='test-only-password-123')
    try:
        assert second.get_review('india', 'event')['review'] == row
        legacy = {'status': 'reviewed'}
        assert second.put_review('global', 'old', actor, {'version': 0, 'review': legacy})['review'] == legacy
        assert 'assessment' not in second.get_review('global', 'old')['review']
    finally:
        second.close()


@pytest.mark.parametrize('overrides', [
    {'assessment': 'confirmed'}, {'assessment': None}, {'supportingSources': None},
    {'supportingSources': []}, {'supportingSources': ['javascript:alert(1)']},
    {'supportingSources': ['https://user:pass@example.org']},
    {'supportingSources': ['x' * 2049]}, {'supportingSources': ['report'] * 9},
    {'uncertainty': ''}, {'uncertainty': None}, {'uncertainty': 'x' * 1001},
    {'assessedAt': None}, {'assessedAt': '2026-02-30T00:00:00Z'},
    {'assessedAt': '2026-10-03T00:00:00'}, {'verified': True},
])
def test_api_rejects_bad_assessment_without_writing(tmp_path, overrides):
    backend = Backend(str(tmp_path / 'reviews.db'), admin_username='admin', admin_password='test-only-password-123')
    with TestClient(create_server(backend)) as client:
        token = client.post('/api/auth/login', json={'username': 'admin', 'password': 'test-only-password-123'}).json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        response = client.put('/api/reviews/event', headers=headers, json={'version': 0, 'review': assessment(**overrides)})
        assert response.status_code == 400
        assert client.get('/api/reviews/event', headers=headers).json()['version'] == 0


def test_timestamp_and_source_contract():
    for value in ['2024-02-29T12:30:00.123+05:30', '2026-10-03T00:00:00Z']:
        assert iso_time(value)
    for value in ['2026-02-29T00:00:00Z', '0000-01-01T00:00:00Z', '2026-10-03T24:00:00Z', '2026-10-03T00:00:00+05:99', '2026-10-03T00:00Z']:
        with pytest.raises(ValueError):
            iso_time(value)
    for value in ['https://example.org/report', 'http://example.org', 'Field report <text>', 'https://example.org?q=%20']:
        assert safe_source(value)
    for value in ['javascript:alert(1)', 'data:text/html,x', '//example.org', 'https://user:pass@example.org', 'https://exam ple.org', 'https://example.org:99999', 'https://example.org\n', 'https:\\example.org', '', 'https://%65xample.org', 'https:///example.org', 'https://@example.org', 'report\u0085text', '\U0001f600' * 1025]:
        assert not safe_source(value)
