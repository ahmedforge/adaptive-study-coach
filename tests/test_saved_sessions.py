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
    monkeypatch.delenv('STUDY_COACH_TARGET_CORRECT', raising=False)
    def practice(state, **kwargs):
        if state.status == 'complete': return None
        return PracticeQuestion(question='What is 2 + 3?', options=['3', '4', '5', '6'],
            correct_answer='5', explanation='Two plus three equals five.', generation_source='seed_fallback', seed_question_id='test-seed')
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
    first = client.post('/sessions/current/answers', headers=headers, json={
        'question_id': data['practice_question']['id'], 'selected_answer': '5'}).json()
    assert first['state']['status'] == 'practicing'
    assert first['state']['correct_streak'] == 1
    assert first['state']['target_correct'] == 2
    assert client.get('/sessions/current', headers=headers).json() == first
    saved = client.post('/sessions/current/answers', headers=headers, json={
        'question_id': first['practice_question']['id'], 'selected_answer': '5'}).json()
    assert saved['state']['status'] == 'complete'
    assert saved['practice_question'] is None
    assert len(saved['history']) == 2
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
    monkeypatch.setattr(sessions, 'get_practice_question', lambda state, **kwargs: None)
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


def test_session_records_seed_and_supplies_it_to_next_selection(client, monkeypatch):
    seen = []
    def practice(state, *, recent_question_ids=None):
        seen.append(list(recent_question_ids or []))
        return PracticeQuestion(question='What is 2 + 3?', options=['3', '4', '5', '6'],
            correct_answer='5', explanation='Two plus three equals five.',
            generation_source='seed_fallback', seed_question_id='seed-a')
    monkeypatch.setattr(sessions, 'get_practice_question', practice)
    data, headers = start(client)
    result = client.post('/sessions/current/answers', headers=headers, json={
        'question_id': data['practice_question']['id'], 'selected_answer': '3'})
    assert result.status_code == 200
    assert result.json()['history'][0]['seed_question_id'] == 'seed-a'
    assert seen == [[], ['seed-a']]


def test_old_saved_question_without_seed_id_still_advances(client, store):
    data, headers = start(client)
    token = data['session_token']
    version, payload = store.load(token)
    payload['question'].pop('seed_question_id', None)
    assert store.save(token, version, payload)
    response = client.post('/sessions/current/answers', headers=headers, json={
        'question_id': data['practice_question']['id'], 'selected_answer': '3'})
    assert response.status_code == 200
    assert response.json()['history'][0]['seed_question_id'] is None


@pytest.mark.parametrize('params', [{'query':'x', 'top_k':0}, {'query':'x', 'top_k':21}, {'query':' '}])
def test_search_rejects_invalid_input(client, params):
    assert client.get('/retrieval/search', params=params).status_code == 422


def test_correct_retry_does_not_advance_streak_twice(client):
    data, headers = start(client)
    answer = {'question_id': data['practice_question']['id'], 'selected_answer': '5'}
    first = client.post('/sessions/current/answers', headers=headers, json=answer).json()
    retry = client.post('/sessions/current/answers', headers=headers, json=answer).json()
    assert retry == first
    assert retry['state']['correct_streak'] == 1
    assert retry['state']['status'] == 'practicing'


def test_target_is_snapshotted_and_wrong_answer_resets_saved_streak(client, monkeypatch):
    monkeypatch.setenv('STUDY_COACH_TARGET_CORRECT', '3')
    data, headers = start(client)
    monkeypatch.setenv('STUDY_COACH_TARGET_CORRECT', '1')
    for selected, expected in [('5', 1), ('3', 0), ('5', 1), ('5', 2)]:
        response = client.post('/sessions/current/answers', headers=headers, json={
            'question_id': data['practice_question']['id'], 'selected_answer': selected})
        assert response.status_code == 200
        data = response.json()
        assert data['state']['target_correct'] == 3
        assert data['state']['correct_streak'] == expected
        assert data['state']['status'] == 'practicing'
    final = client.post('/sessions/current/answers', headers=headers, json={
        'question_id': data['practice_question']['id'], 'selected_answer': '5'}).json()
    assert final['state']['status'] == 'complete'
    assert final['state']['correct_streak'] == 0


@pytest.mark.parametrize('target', ['0', '6', 'two', '2.5', ''])
def test_invalid_target_configuration_rejects_new_session(client, monkeypatch, target):
    monkeypatch.setenv('STUDY_COACH_TARGET_CORRECT', target)
    assert client.post('/sessions', json=diagnostic()).status_code == 503


def test_legacy_saved_session_keeps_one_answer_target(client, store, monkeypatch):
    data, headers = start(client)
    token = data['session_token']
    version, payload = store.load(token)
    payload['state'].pop('target_correct')
    payload['state'].pop('correct_streak')
    assert store.save(token, version, payload)
    monkeypatch.setenv('STUDY_COACH_TARGET_CORRECT', '5')
    restored = client.get('/sessions/current', headers=headers).json()
    assert restored['state']['target_correct'] == 1
    assert restored['state']['correct_streak'] == 0
    result = client.post('/sessions/current/answers', headers=headers, json={
        'question_id': data['practice_question']['id'], 'selected_answer': '5'})
    assert result.status_code == 200
    assert result.json()['state']['status'] == 'complete'


def test_diagnostic_review_is_saved_and_does_not_change_during_practice(client):
    questions = load_questions()[:12]
    submission = diagnostic()
    submission['answers'][1]['selected_answer'] = next(
        option for option in questions[1].options if option != questions[1].correct_answer)
    created = client.post('/sessions', json=submission)
    assert created.status_code == 201
    data = created.json()
    headers = {'Authorization': 'Bearer ' + data['session_token']}
    summary = data['diagnostic_summary']
    assert {key: summary[key] for key in ['total', 'correct', 'incorrect', 'unanswered']} == {
        'total': 12, 'correct': 10, 'incorrect': 1, 'unanswered': 1}
    assert summary['topics'][0]['unanswered'] == 1
    assert summary['topics'][1]['incorrect'] == 1
    assert client.get('/sessions/current', headers=headers).json()['diagnostic_summary'] == summary
    updated = client.post('/sessions/current/answers', headers=headers, json={
        'question_id': data['practice_question']['id'], 'selected_answer': '5'})
    assert updated.status_code == 200
    assert updated.json()['diagnostic_summary'] == summary


def test_all_correct_diagnostic_has_review_and_no_practice(client):
    submission = {'answers': [{'question_id': q.id, 'selected_answer': q.correct_answer}
                             for q in load_questions()[:12]]}
    response = client.post('/sessions', json=submission)
    assert response.status_code == 201
    data = response.json()
    assert data['diagnostic_summary']['correct'] == 12
    assert data['diagnostic_summary']['incorrect'] == 0
    assert data['diagnostic_summary']['unanswered'] == 0
    assert data['practice_question'] is None
