from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.progress_repository import ProgressStore
from app.routers import sessions


@pytest.fixture
def dashboard_client(tmp_path):
    store = ProgressStore(tmp_path / 'progress.sqlite3')
    app.dependency_overrides[sessions.get_store] = lambda: store
    with TestClient(app) as client: yield client, store
    app.dependency_overrides.clear()


def practice(store, *, history=None, topic='algebra', source='diagnostic', date='2026-10-30T10:00:00+00:00'):
    return store.create({'state': {'diagnostic_results': [], 'weak_topics': [topic],
        'current_topic': topic, 'status': 'practicing', 'correct_streak': 1, 'target_correct': 2},
        'history': history if history is not None else [{'topic': topic, 'is_correct': True},
            {'topic': topic, 'is_correct': False}],
        'assessment_source': source, 'updated_at': date})


def summarize(client, refs):
    return client.post('/progress/summary', json={'sessions': refs})


def create_exam(client):
    response = client.post('/exams', json={})
    assert response.status_code == 201
    return response.json()


def test_empty_dashboard_and_page(dashboard_client):
    client, store = dashboard_client
    data = summarize(client, []).json()
    assert data['sessions'] == data['topics'] == data['revisit'] == []
    assert all(value == 0 for value in data['totals'].values())
    assert client.get('/dashboard').status_code == 200


def test_only_provided_tokens_are_read_and_no_tokens_or_answers_leak(dashboard_client):
    client, store = dashboard_client
    mine = practice(store)
    other = practice(store, topic='geometry')
    response = summarize(client, [{'kind': 'practice', 'token': mine}])
    assert response.status_code == 200
    data = response.json()
    assert data['totals']['practice_sessions'] == 1
    assert data['totals']['practice_answers'] == 2
    assert data['totals']['practice_correct'] == 1
    assert data['topics'] == [{'topic': 'algebra', 'practice_correct': 1, 'practice_total': 2,
                              'exam_correct': 0, 'exam_total': 0}]
    assert mine not in response.text and other not in response.text
    assert 'correct_answer' not in response.text
    assert data['sessions'][0]['index'] == 0
    assert data['sessions'][0]['correct_streak'] == 1


def test_duplicates_not_double_counted_and_missing_modes_are_unavailable(dashboard_client):
    client, store = dashboard_client
    token = practice(store)
    data = summarize(client, [{'kind': 'practice', 'token': token},
        {'kind': 'practice', 'token': token}, {'kind': 'exam', 'token': token},
        {'kind': 'practice', 'token': 'missing'}]).json()
    assert data['totals']['practice_sessions'] == 1
    assert len(data['sessions']) == 1
    assert data['unavailable'] == [2, 3]


def test_sessions_sorted_without_revealing_active_exam_scores(dashboard_client):
    client, store = dashboard_client
    old = practice(store, date='2020-01-01T00:00:00+00:00')
    exam = create_exam(client)
    data = summarize(client, [{'kind': 'practice', 'token': old},
        {'kind': 'exam', 'token': exam['exam_token']}]).json()
    assert [s['index'] for s in data['sessions']] == [1, 0]
    assert data['sessions'][0]['status'] == 'active'
    assert 'score_percent' not in data['sessions'][0]
    assert data['totals']['completed_exams'] == 0
    assert data['revisit'] == []


def test_completed_exam_topic_results_and_practice_remain_separate(dashboard_client):
    client, store = dashboard_client
    exam = create_exam(client)
    version, payload = store.load(exam['exam_token'])
    first, second = payload['questions'][:2]
    payload['answers'] = {first['id']: first['correct_answer'],
        second['id']: next(o for o in second['options'] if o != second['correct_answer'])}
    assert store.save(exam['exam_token'], version, payload)
    headers = {'Authorization': 'Bearer ' + exam['exam_token']}
    assert client.post('/exams/current/submit', headers=headers).status_code == 200
    token = practice(store, topic=first['topic'], source='mock_exam')
    data = summarize(client, [{'kind': 'practice', 'token': token},
        {'kind': 'exam', 'token': exam['exam_token']}]).json()
    assert data['totals']['completed_exams'] == 1
    report = next(s for s in data['sessions'] if s['kind'] == 'exam')
    assert report['correct'] == 1 and report['score_percent'] == 8.3
    topic = next(t for t in data['topics'] if t['topic'] == first['topic'])
    assert topic == {'topic': first['topic'], 'practice_correct': 1, 'practice_total': 2,
                     'exam_correct': 1, 'exam_total': 1}
    assert first['topic'] not in [t['topic'] for t in data['revisit']]
    assert len(data['revisit']) == 5
    assert next(s for s in data['sessions'] if s['kind'] == 'practice')['assessment_source'] == 'mock_exam'


def test_expired_exam_summary_is_read_only_and_does_not_expose_grading(dashboard_client):
    client, store = dashboard_client
    exam = create_exam(client)
    version, payload = store.load(exam['exam_token'])
    payload['expires_at'] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert store.save(exam['exam_token'], version, payload)
    before = deepcopy(store.load(exam['exam_token']))
    response = summarize(client, [{'kind': 'exam', 'token': exam['exam_token']}])
    data = response.json()
    assert data['sessions'][0]['status'] == 'time_elapsed'
    assert 'score_percent' not in response.text and 'correct_answer' not in response.text
    assert store.load(exam['exam_token']) == before


def test_legacy_practice_defaults_and_multiple_sessions(dashboard_client):
    client, store = dashboard_client
    first = practice(store)
    version, data = store.load(first)
    data.pop('assessment_source')
    data['state'].pop('target_correct'); data['state'].pop('correct_streak')
    assert store.save(first, version, data)
    second = practice(store, history=[])
    summary = summarize(client, [{'kind': 'practice', 'token': first},
        {'kind': 'practice', 'token': second}]).json()
    legacy = next(s for s in summary['sessions'] if s['index'] == 0)
    assert legacy['target_correct'] == 1 and legacy['assessment_source'] == 'diagnostic'
    assert summary['totals']['practice_sessions'] == 2
    assert summary['totals']['practice_answers'] == 2


@pytest.mark.parametrize('body', [
    {'sessions': [{'kind': 'account', 'token': 'x'}]},
    {'sessions': [{'kind': 'practice', 'token': ''}]},
    {'sessions': [{'kind': 'practice', 'token': 'x' * 101}]},
    {'sessions': [{'kind': 'practice', 'token': 'x'}] * 51},
    {'sessions': [], 'all_users': True},
])
def test_reject_invalid_and_oversized_requests(dashboard_client, body):
    client, store = dashboard_client
    assert client.post('/progress/summary', json=body).status_code == 422


def test_store_failure_safe_and_does_not_mutate_sessions(dashboard_client, monkeypatch):
    client, store = dashboard_client
    token = practice(store)
    def fail(*args): raise sqlite3.OperationalError('private-db-path')
    monkeypatch.setattr(store, 'load', fail)
    response = summarize(client, [{'kind': 'practice', 'token': token}])
    assert response.status_code == 503
    assert 'private-db-path' not in response.text
