from collections import Counter
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.progress_repository import ProgressStore
from app.routers import exams, sessions


@pytest.fixture
def exam_client(tmp_path, monkeypatch):
    store = ProgressStore(tmp_path / 'progress.sqlite3')
    clock = [datetime(2026, 10, 30, 10, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(exams, 'utc_now', lambda: clock[0])
    app.dependency_overrides[sessions.get_store] = lambda: store
    with TestClient(app) as client:
        yield client, store, clock
    app.dependency_overrides.clear()


def start(fixture, **settings):
    client, store, clock = fixture
    response = client.post('/exams', json=settings)
    assert response.status_code == 201, response.text
    data = response.json()
    return data, {'Authorization': 'Bearer ' + data['exam_token']}


def answer(client, data, headers, question=None, selected=None):
    q = question or data['questions'][0]
    return client.put('/exams/current/answers', headers=headers, json={
        'question_id': q['id'], 'selected_answer': selected or q['options'][0], 'version': data['version']})


@pytest.mark.parametrize('size, per_topic', [(12, 1), (24, 2)])
def test_balanced_unique_snapshot_and_no_answer_key(exam_client, size, per_topic):
    data, headers = start(exam_client, question_count=size)
    assert len(data['questions']) == size
    assert len({q['id'] for q in data['questions']}) == size
    assert set(Counter(q['topic'] for q in data['questions']).values()) == {per_topic}
    assert 'results' not in data and 'summary' not in data
    assert all(set(q) == {'id', 'topic', 'question', 'options'} for q in data['questions'])
    assert data['answers'] == {}
    client, store, clock = exam_client
    app.dependency_overrides[sessions.get_store] = lambda: ProgressStore(store.path)
    resumed = client.get('/exams/current', headers=headers).json()
    assert resumed['questions'] == data['questions']
    assert resumed['expires_at'] == data['expires_at']
    assert data['exam_token'].encode() not in store.path.read_bytes()


def test_drafts_change_clear_resume_without_revealing_results(exam_client):
    client, store, clock = exam_client
    data, headers = start(exam_client)
    original_expiry = data['expires_at']
    first = answer(client, data, headers)
    assert first.status_code == 200
    data = first.json()
    q = data['questions'][0]
    assert data['answers'] == {q['id']: q['options'][0]}
    assert 'results' not in data
    data = answer(client, data, headers, selected=q['options'][1]).json()
    assert data['answers'][q['id']] == q['options'][1]
    cleared = client.put('/exams/current/answers', headers=headers, json={
        'question_id': q['id'], 'selected_answer': None, 'version': data['version']})
    assert cleared.status_code == 200
    assert cleared.json()['answers'] == {}
    assert cleared.json()['expires_at'] == original_expiry
    assert client.get('/exams/current', headers=headers).json() == cleared.json()


def test_retry_is_idempotent_and_stale_edit_cannot_overwrite(exam_client):
    client, store, clock = exam_client
    data, headers = start(exam_client)
    saved = answer(client, data, headers)
    retry = answer(client, data, headers)
    assert retry.json() == saved.json()
    stale = answer(client, data, headers, selected=data['questions'][0]['options'][1])
    assert stale.status_code == 409
    assert client.get('/exams/current', headers=headers).json()['answers'] == saved.json()['answers']


def test_submission_scores_saved_answers_and_locks_report(exam_client):
    client, store, clock = exam_client
    data, headers = start(exam_client)
    _, stored = store.load(data['exam_token'])
    first, second = stored['questions'][:2]
    data = answer(client, data, headers, question=first, selected=first['correct_answer']).json()
    wrong = next(o for o in second['options'] if o != second['correct_answer'])
    data = answer(client, data, headers, question=second, selected=wrong).json()
    finished = client.post('/exams/current/submit', headers=headers)
    assert finished.status_code == 200
    report = finished.json()
    assert report['status'] == 'completed'
    assert report['summary']['correct'] == 1
    assert report['summary']['incorrect'] == 1
    assert report['summary']['unanswered'] == 10
    assert report['score_percent'] == 8.3
    assert report['completion_reason'] == 'submitted'
    assert report['results'][0]['explanation'] == first['explanation']
    assert report['results'][0]['is_correct'] is True
    assert report['results'][2]['selected_answer'] is None
    assert client.post('/exams/current/submit', headers=headers).json() == report
    assert answer(client, data, headers).status_code == 409
    assert client.get('/exams/current', headers=headers).json() == report


@pytest.mark.parametrize('trigger', ['resume', 'answer', 'submit'])
def test_server_deadline_finalizes_and_rejects_late_edits(exam_client, trigger):
    client, store, clock = exam_client
    data, headers = start(exam_client, duration_minutes=5)
    data = answer(client, data, headers).json()
    clock[0] += timedelta(minutes=5)
    if trigger == 'answer':
        assert answer(client, data, headers, selected=data['questions'][0]['options'][1]).status_code == 409
    elif trigger == 'submit':
        assert client.post('/exams/current/submit', headers=headers).status_code == 200
    report = client.get('/exams/current', headers=headers).json()
    assert report['status'] == 'completed'
    assert report['completion_reason'] == 'time_expired'
    assert report['completed_at'] == data['expires_at']
    assert report['answers'] == data['answers']
    assert report['summary']['unanswered'] == 11


def test_all_correct_and_all_blank_reports(exam_client):
    client, store, clock = exam_client
    blank, blank_headers = start(exam_client)
    report = client.post('/exams/current/submit', headers=blank_headers).json()
    assert report['summary']['unanswered'] == 12
    assert report['score_percent'] == 0
    data, headers = start(exam_client)
    _, stored = store.load(data['exam_token'])
    for q in stored['questions']:
        response = answer(client, data, headers, question=q, selected=q['correct_answer'])
        assert response.status_code == 200
        data = response.json()
    report = client.post('/exams/current/submit', headers=headers).json()
    assert report['score_percent'] == 100
    assert report['summary']['correct'] == 12
    assert report['summary']['incorrect'] == report['summary']['unanswered'] == 0


@pytest.mark.parametrize('settings', [
    {'question_count': 0}, {'question_count': 13}, {'question_count': '12'},
    {'duration_minutes': 4}, {'duration_minutes': 121}, {'duration_minutes': '30'},
    {'expires_at': '2100-01-01'}, {'duration_minutes': True}])
def test_reject_invalid_settings_and_client_deadlines(exam_client, settings):
    client, _, _ = exam_client
    assert client.post('/exams', json=settings).status_code == 422


@pytest.mark.parametrize('change', [
    {'question_id': 'foreign'}, {'selected_answer': 'not an option'}, {'is_correct': True},
    {'version': -1}, {'version': '0'}, {'selected_answer': 5}])
def test_reject_answer_tampering(exam_client, change):
    client, _, _ = exam_client
    data, headers = start(exam_client)
    payload = {'question_id': data['questions'][0]['id'],
        'selected_answer': data['questions'][0]['options'][0], 'version': data['version']} | change
    assert client.put('/exams/current/answers', headers=headers, json=payload).status_code == 422
    assert client.get('/exams/current', headers=headers).json()['answers'] == {}


def test_tokens_and_modes_are_isolated(exam_client):
    client, store, _ = exam_client
    first, first_headers = start(exam_client)
    second, second_headers = start(exam_client)
    assert answer(client, first, first_headers).status_code == 200
    assert client.get('/exams/current', headers=second_headers).json()['answers'] == {}
    assert client.get('/sessions/current', headers=first_headers).status_code == 401
    study_token = store.create({'state': {}, 'history': []})
    assert client.get('/exams/current', headers={'Authorization': 'Bearer ' + study_token}).status_code == 401
    assert client.get('/exams/current', headers={'Authorization': 'Bearer invalid'}).status_code == 401
    assert client.get('/exams/current').status_code in (401, 403)


def test_failed_save_keeps_previous_draft(exam_client, monkeypatch):
    client, store, _ = exam_client
    data, headers = start(exam_client)
    def fail(*args): raise sqlite3.OperationalError('private-db-details')
    monkeypatch.setattr(store, 'save', fail)
    response = answer(client, data, headers)
    assert response.status_code == 503
    assert 'private-db-details' not in response.text
    assert client.get('/exams/current', headers=headers).json()['answers'] == {}


def test_concurrent_write_returns_conflict(exam_client, monkeypatch):
    client, store, _ = exam_client
    data, headers = start(exam_client)
    monkeypatch.setattr(store, 'save', lambda *args: False)
    assert answer(client, data, headers).status_code == 409


def test_bank_changes_do_not_change_snapshot_or_grading(exam_client, monkeypatch):
    client, store, _ = exam_client
    data, headers = start(exam_client)
    _, stored = store.load(data['exam_token'])
    first = stored['questions'][0]
    monkeypatch.setattr(exams, 'load_questions', lambda: [])
    assert client.get('/exams/current', headers=headers).json()['questions'] == data['questions']
    answer(client, data, headers, question=first, selected=first['correct_answer'])
    assert client.post('/exams/current/submit', headers=headers).json()['summary']['correct'] == 1


def test_insufficient_bank_and_unavailable_create_storage(exam_client, monkeypatch):
    client, store, _ = exam_client
    monkeypatch.setattr(exams, 'load_questions', lambda: [])
    assert client.post('/exams', json={}).status_code == 503


def test_expiry_storage_failure_does_not_reveal_keys_or_accept_late_answer(exam_client, monkeypatch):
    client, store, clock = exam_client
    data, headers = start(exam_client, duration_minutes=5)
    clock[0] += timedelta(minutes=6)
    def fail(*args): raise sqlite3.OperationalError('private-storage-message')
    monkeypatch.setattr(store, 'save', fail)
    response = client.get('/exams/current', headers=headers)
    assert response.status_code == 503
    assert 'correct_answer' not in response.text
    assert 'private-storage-message' not in response.text
    assert answer(client, data, headers).status_code == 503
    assert store.load(data['exam_token'])[1]['answers'] == {}


def test_creation_save_failure_has_safe_error(exam_client, monkeypatch):
    client, store, _ = exam_client
    def fail(*args): raise sqlite3.OperationalError('private-storage-message')
    monkeypatch.setattr(store, 'create', fail)
    response = client.post('/exams', json={})
    assert response.status_code == 503
    assert 'private-storage-message' not in response.text
