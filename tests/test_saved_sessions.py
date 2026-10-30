import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.generated_question import PracticeQuestion
from app.repositories.progress_repository import ProgressStore
from app.repositories.question_repository import load_questions
from app.routers import sessions


@pytest.fixture
def store(tmp_path):
    return ProgressStore(tmp_path / 'progress.sqlite3')


@pytest.fixture
def client(store, monkeypatch):
    def practice(state):
        if state.status == 'complete': return None
        return PracticeQuestion(question='What is 2 + 3?', options=['3', '4', '5', '6'],
            correct_answer='5', explanation='Two plus three equals five.', generation_source='seed_fallback')
    monkeypatch.setattr(sessions, 'get_practice_question', practice)
    app.dependency_overrides[sessions.get_store] = lambda: store
    with TestClient(app) as value: yield value
    app.dependency_overrides.clear()


def diagnostic():
    questions = load_questions()[:12]
    answers = [{'question_id': q.id, 'selected_answer': q.correct_answer} for q in questions]
    answers[0]['selected_answer'] = None
    return {'answers': answers}


def start(client):
    response = client.post('/sessions', json=diagnostic())
    assert response.status_code == 201, response.text
    data = response.json()
    headers = {'Authorization': 'Bearer ' + data['session_token']}
    return data, headers


def test_session_survives_store_restart_and_hides_current_answer(client, store):
    data, headers = start(client)
    assert 'correct_answer' not in data['practice_question']
    assert 'explanation' not in data['practice_question']
    reopened = ProgressStore(store.path)
    app.dependency_overrides[sessions.get_store] = lambda: reopened
    restored = client.get('/sessions/current', headers=headers)
    assert restored.status_code == 200
    assert restored.json()['practice_question'] == data['practice_question']
    assert restored.json()['state'] == data['state']
    assert data['session_token'].encode() not in store.path.read_bytes()


def test_wrong_answer_saves_history_and_keeps_topic(client):
    data, headers = start(client)
    response = client.post('/sessions/current/answers', headers=headers, json={
        'question_id': data['practice_question']['id'], 'selected_answer': '3'})
    assert response.status_code == 200
    saved = response.json()
    assert saved['state']['current_topic'] == data['state']['current_topic']
    assert saved['state']['attempts_on_topic'] == 1
    assert saved['history'][0]['is_correct'] is False
    assert saved['history'][0]['explanation'] == 'Two plus three equals five.'
    assert saved['practice_question']['id'] != data['practice_question']['id']
    assert client.get('/sessions/current', headers=headers).json() == saved


def test_correct_answer_completes_last_topic_and_survives_resume(client):
    data, headers = start(client)
    saved = client.post('/sessions/current/answers', headers=headers, json={
        'question_id': data['practice_question']['id'], 'selected_answer': '5'}).json()
    assert saved['state']['status'] == 'complete'
    assert saved['practice_question'] is None
    assert len(saved['history']) == 1
    assert client.get('/sessions/current', headers=headers).json() == saved


def test_response_loss_retry_does_not_double_count(client):
    data, headers = start(client)
    answer = {'question_id': data['practice_question']['id'], 'selected_answer': '3'}
    first = client.post('/sessions/current/answers', headers=headers, json=answer)
    second = client.post('/sessions/current/answers', headers=headers, json=answer)
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert len(second.json()['history']) == 1


def test_stale_or_changed_answer_is_rejected(client):
    data, headers = start(client)
    answer = {'question_id': data['practice_question']['id'], 'selected_answer': '3'}
    assert client.post('/sessions/current/answers', headers=headers, json=answer).status_code == 200
    answer['selected_answer'] = '4'
    assert client.post('/sessions/current/answers', headers=headers, json=answer).status_code == 409
    assert len(client.get('/sessions/current', headers=headers).json()['history']) == 1


def test_server_rejects_client_grading_and_non_option_answers(client):
    data, headers = start(client)
    answer = {'question_id': data['practice_question']['id'], 'selected_answer': 'not an option'}
    assert client.post('/sessions/current/answers', headers=headers, json=answer).status_code == 422
    answer.update(selected_answer='3', is_correct=True)
    assert client.post('/sessions/current/answers', headers=headers, json=answer).status_code == 422
    assert client.get('/sessions/current', headers=headers).json()['history'] == []


def test_tokens_do_not_access_other_sessions(client):
    first, first_headers = start(client)
    second, second_headers = start(client)
    client.post('/sessions/current/answers', headers=first_headers, json={
        'question_id': first['practice_question']['id'], 'selected_answer': '3'})
    assert client.get('/sessions/current', headers=second_headers).json()['history'] == []
    assert client.get('/sessions/current', headers={'Authorization': 'Bearer invalid'}).status_code == 401
    assert client.get('/sessions/current').status_code in (401, 403)


@pytest.mark.parametrize('mode', ['missing', 'duplicate', 'foreign', 'invalid_option'])
def test_diagnostic_requires_exact_current_question_set(client, mode):
    data = diagnostic()
    if mode == 'missing': data['answers'].pop()
    elif mode == 'duplicate': data['answers'][-1] = data['answers'][0]
    elif mode == 'foreign': data['answers'][0]['question_id'] = 'unknown'
    else: data['answers'][0]['selected_answer'] = 'not an option'
    assert client.post('/sessions', json=data).status_code == 422


def test_save_failure_does_not_report_success_or_lose_old_progress(client, store, monkeypatch):
    data, headers = start(client)
    def fail(*args): raise sqlite3.OperationalError('private-db-path')
    monkeypatch.setattr(store, 'save', fail)
    response = client.post('/sessions/current/answers', headers=headers, json={
        'question_id': data['practice_question']['id'], 'selected_answer': '3'})
    assert response.status_code == 503
    assert 'private-db-path' not in response.text
    old = client.get('/sessions/current', headers=headers).json()
    assert old['practice_question'] == data['practice_question']
    assert old['history'] == []


def test_unavailable_next_question_keeps_previous_state(client, monkeypatch):
    data, headers = start(client)
    monkeypatch.setattr(sessions, 'get_practice_question', lambda state: None)
    result = client.post('/sessions/current/answers', headers=headers, json={
        'question_id': data['practice_question']['id'], 'selected_answer': '3'})
    assert result.status_code == 503
    old = client.get('/sessions/current', headers=headers).json()
    assert old['history'] == []
    assert old['practice_question'] == data['practice_question']


def test_store_rejects_stale_concurrent_version(store):
    token = store.create({'history': []})
    version, _ = store.load(token)
    assert store.save(token, version, {'history': ['first']})
    assert not store.save(token, version, {'history': ['second']})
    assert store.load(token)[1]['history'] == ['first']
