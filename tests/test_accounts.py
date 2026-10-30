from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.generated_question import PracticeQuestion
from app.repositories.account_repository import AccountRepository
from app.repositories.progress_repository import ProgressStore
from app.routers import sessions
from app.services.account_service import COOKIE

PASSWORD = 'A test passphrase for learners 42!'
REPLACEMENT = 'Another test passphrase for learners 43!'


@pytest.fixture
def account_env(tmp_path, monkeypatch):
    path = tmp_path / 'accounts.sqlite3'
    monkeypatch.setenv('STUDY_COACH_DB', str(path))
    monkeypatch.delenv('STUDY_COACH_COOKIE_SECURE', raising=False)
    app.dependency_overrides.clear()
    def practice(state, **kwargs):
        if state.status == 'complete': return None
        return PracticeQuestion(question='What is 2 + 3?', options=['3','4','5','6'],
            correct_answer='5', explanation='Two plus three equals five.', seed_question_id='test-seed')
    monkeypatch.setattr(sessions, 'get_practice_question', practice)
    with ExitStack() as stack:
        def client(**kwargs):
            return stack.enter_context(TestClient(app, base_url='https://testserver', headers={'X-Study-Coach':'1'}, **kwargs))
        yield client, path
    app.dependency_overrides.clear()


def register(client, username='learner_one'):
    response = client.post('/account/register', json={'username':username, 'password':PASSWORD})
    assert response.status_code == 201, response.text
    return response


def login(client, username='learner_one', password=PASSWORD):
    return client.post('/account/login', json={'username':username, 'password':password})


def exam(client):
    response = client.post('/exams', json={})
    assert response.status_code == 201, response.text
    data = response.json()
    return data, {'Authorization':'Bearer ' + data['exam_token']}


def test_password_hash_cookie_flags_and_no_raw_credentials_stored(account_env):
    make, path = account_env
    client = make()
    response = register(client, '  Learner_One  ')
    assert response.json() == {'authenticated':True, 'username':'learner_one'}
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'secure' in cookie and 'samesite=lax' in cookie
    assert 'max-age=604800' in cookie
    token = client.cookies.get(COOKIE)
    assert token not in response.text and PASSWORD not in response.text
    raw = path.read_bytes()
    assert token.encode() not in raw and PASSWORD.encode() not in raw
    with ProgressStore(path).connect() as db:
        encoded = db.execute('SELECT password_hash FROM accounts').fetchone()[0]
    assert encoded.startswith('$argon2id$')
    assert client.get('/account/me').json()['username'] == 'learner_one'


def test_two_devices_reopen_same_exam_and_share_draft_versions(account_env):
    make, path = account_env
    first, second, stranger = make(), make(), make()
    register(first)
    data, headers = exam(first)
    register(stranger, 'other_learner')
    assert stranger.get('/exams/current', headers=headers).status_code == 401
    assert login(second).status_code == 200
    references = second.get('/account/library').json()['sessions']
    assert len(references) == 1
    ref = references[0]
    opened = second.post('/account/open', json={'id':ref['id']})
    assert opened.status_code == 200
    alias_headers = {'Authorization':'Bearer ' + opened.json()['session_token']}
    resumed = second.get('/exams/current', headers=alias_headers).json()
    assert resumed['questions'] == data['questions']
    assert resumed['expires_at'] == data['expires_at']
    answer = {'question_id':data['questions'][0]['id'], 'selected_answer':data['questions'][0]['options'][0], 'version':0}
    saved = first.put('/exams/current/answers', headers=headers, json=answer)
    assert saved.status_code == 200
    assert second.get('/exams/current', headers=alias_headers).json()['answers'] == saved.json()['answers']
    answer['selected_answer'] = data['questions'][0]['options'][1]
    assert second.put('/exams/current/answers', headers=alias_headers, json=answer).status_code == 409
    assert stranger.post('/account/open', json={'id':ref['id']}).status_code == 404
    summary = stranger.post('/progress/summary', json={'sessions':[ref]}).json()
    assert summary['sessions'] == [] and summary['unavailable'] == [0]


def test_anonymous_token_alone_cannot_access_account_owned_records(account_env):
    make, path = account_env
    owner, anonymous = make(), make()
    register(owner)
    data, headers = exam(owner)
    assert anonymous.get('/exams/current', headers=headers).status_code == 401
    store = ProgressStore(path)
    assert store.load(data['exam_token']) is None
    assert not store.save(data['exam_token'], 0, {})
    assert anonymous.get('/account/library').status_code == 401


def test_logout_revokes_this_device_but_keeps_other_device(account_env):
    make, path = account_env
    first, second = make(), make()
    register(first); assert login(second).status_code == 200
    old = first.cookies.get(COOKIE)
    assert first.post('/account/logout').status_code == 200
    assert first.get('/account/me').json() == {'authenticated':False}
    assert second.get('/account/me').json()['authenticated'] is True
    first.cookies.set(COOKIE, old, domain='testserver.local', path='/')
    assert first.get('/account/me').json()['authenticated'] is False


def test_logout_all_and_password_change_revoke_other_sessions(account_env):
    make, path = account_env
    first, second = make(), make()
    register(first); assert login(second).status_code == 200
    rejected = first.post('/account/password', json={'current_password':'wrong', 'new_password':REPLACEMENT})
    assert rejected.status_code == 401
    changed = first.post('/account/password', json={'current_password':PASSWORD, 'new_password':REPLACEMENT})
    assert changed.status_code == 200
    assert first.get('/account/me').json()['authenticated'] is True
    assert second.get('/account/me').json()['authenticated'] is False
    assert login(second).status_code == 401
    assert login(second, password=REPLACEMENT).status_code == 200
    assert first.post('/account/logout-all').status_code == 200
    assert first.get('/account/me').json()['authenticated'] is False
    assert second.get('/account/me').json()['authenticated'] is False


def test_login_rotates_session_and_expiry_blocks_silent_anonymous_writes(account_env):
    make, path = account_env
    client = make(); register(client)
    old = client.cookies.get(COOKIE)
    assert login(client).status_code == 200
    assert client.cookies.get(COOKIE) != old
    with ProgressStore(path).connect() as db:
        assert db.execute('SELECT COUNT(*) FROM account_logins WHERE token_hash=?', (ProgressStore.digest(old),)).fetchone()[0] == 0
        db.execute('UPDATE account_logins SET expires_at=?', (time.time()-1,))
    assert client.get('/account/me').json()['authenticated'] is False
    response = client.post('/exams', json={})
    assert response.status_code == 401
    assert 'expired' in response.text
    assert login(client).status_code == 200


def test_login_errors_generic_rate_limited_and_validation_redacted(account_env):
    make, path = account_env
    client = make(); register(client)
    client.post('/account/logout')
    known = login(client, password='Wrong test passphrase 123').json()
    unknown = login(client, username='unknown_person', password='Wrong test passphrase 123').json()
    assert known == unknown
    invalid = client.post('/account/register', json={'username':'?', 'password':PASSWORD, 'extra':True})
    assert invalid.status_code == 422
    assert PASSWORD not in invalid.text and 'input' not in invalid.text
    for _ in range(9): assert login(client, username='limited_user').status_code == 401
    assert login(client, username='limited_user').status_code == 401
    assert login(client, username='limited_user').status_code == 429
    with ProgressStore(path).connect() as db: db.execute('UPDATE login_attempts SET window_start=0')
    assert login(client, username='limited_user').status_code == 401


@pytest.mark.parametrize('route,payload', [
    ('/account/register', {'username':'another_user','password':PASSWORD}),
    ('/account/login', {'username':'learner_one','password':PASSWORD}),
    ('/account/logout', None), ('/account/logout-all', None),
    ('/exams', {}), ('/progress/summary', {'sessions':[]}),
])
def test_mutations_reject_cross_origin_and_missing_header(account_env, route, payload):
    make, path = account_env
    client = make(); register(client)
    kwargs = {'json':payload} if payload is not None else {}
    assert client.post(route, headers={'Origin':'https://evil.example'}, **kwargs).status_code == 403
    assert client.post(route, headers={'X-Study-Coach':'0'}, **kwargs).status_code == 403


def test_same_origin_mutation_allowed(account_env):
    make, path = account_env
    client = make(); register(client)
    assert client.post('/exams', json={}, headers={'Origin':'https://testserver'}).status_code == 201


def test_claim_anonymous_exam_and_revision_then_resume_on_another_device(account_env):
    make, path = account_env
    old_browser, new_browser = make(), make()
    data, headers = exam(old_browser)
    assert old_browser.post('/exams/current/submit', headers=headers).status_code == 200
    revision = old_browser.post('/exams/current/revision', headers=headers).json()
    assert 'session_token' in revision
    revision_headers = {'Authorization':'Bearer ' + revision['session_token']}
    register(new_browser)
    claim = new_browser.post('/account/claim', json={'sessions':[{'kind':'exam','token':data['exam_token']}]})
    assert claim.json()['available_in_account'] == 1
    assert old_browser.get('/exams/current', headers=headers).status_code == 401
    assert old_browser.get('/sessions/current', headers=revision_headers).status_code == 401
    references = new_browser.get('/account/library').json()['sessions']
    assert {r['kind'] for r in references} == {'practice','exam'}
    other = make(); register(other, 'different_user')
    assert other.post('/account/claim', json={'sessions':[{'kind':'exam','token':data['exam_token']}]}).json()['unavailable'] == 1


def test_revision_stays_one_plan_across_multiple_account_resume_tokens(account_env):
    make, path = account_env
    first, second = make(), make()
    register(first)
    data, headers = exam(first)
    first.post('/exams/current/submit', headers=headers)
    revision = first.post('/exams/current/revision', headers=headers).json()
    assert login(second).status_code == 200
    ref = next(r for r in second.get('/account/library').json()['sessions'] if r['kind']=='exam')
    alias = second.post('/account/open', json={'id':ref['id']}).json()['session_token']
    resumed = second.post('/exams/current/revision', headers={'Authorization':'Bearer '+alias}).json()
    assert resumed['practice_question']['id'] == revision['practice_question']['id']
    answered = second.post('/sessions/current/answers', headers={'Authorization':'Bearer '+resumed['session_token']},
        json={'question_id':resumed['practice_question']['id'],'selected_answer':'5'})
    assert answered.status_code == 200
    original = first.get('/sessions/current', headers={'Authorization':'Bearer '+revision['session_token']}).json()
    assert len(original['history']) == 1
    with ProgressStore(path).connect() as db:
        assert db.execute('SELECT COUNT(*) FROM study_sessions').fetchone()[0] == 2


def test_claim_deduplicates_and_cannot_overwrite_someone_elses_progress(account_env):
    make, path = account_env
    guest, alice, bob = make(), make(), make()
    data, headers = exam(guest)
    register(alice); register(bob, 'learner_bob')
    ref = {'kind':'exam','token':data['exam_token']}
    assert alice.post('/account/claim', json={'sessions':[ref,ref]}).json() == {'available_in_account':1,'unavailable':0}
    assert bob.post('/account/claim', json={'sessions':[ref]}).json() == {'available_in_account':0,'unavailable':1}
    assert len(alice.get('/account/library').json()['sessions']) == 1
    assert bob.get('/account/library').json()['sessions'] == []


def test_library_pagination_is_scoped_to_owner(account_env):
    make, path = account_env
    client = make(); register(client)
    for _ in range(3): exam(client)
    first = client.get('/account/library?limit=2').json()
    second = client.get('/account/library?limit=2&offset=2').json()
    assert first['has_more'] is True and second['has_more'] is False
    assert len(first['sessions']) == 2 and len(second['sessions']) == 1
    assert {r['id'] for r in first['sessions']}.isdisjoint(r['id'] for r in second['sessions'])


def test_attempt_reservations_are_atomic_under_concurrency(tmp_path):
    store = ProgressStore(tmp_path/'throttle.sqlite3')
    repository = AccountRepository(store)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: repository.reserve_attempt('key',limit=3), range(8)))
    assert sum(results) == 3


def test_legacy_revision_without_link_is_imported_with_exam(account_env):
    make, path = account_env
    old, owner = make(), make()
    data, headers = exam(old)
    old.post('/exams/current/submit', headers=headers)
    revision = old.post('/exams/current/revision', headers=headers).json()
    with ProgressStore(path).connect() as db: db.execute('DELETE FROM revision_links')
    register(owner)
    assert owner.post('/account/claim', json={'sessions':[{'kind':'exam','token':data['exam_token']}]}).status_code == 200
    assert len(owner.get('/account/library').json()['sessions']) == 2
    assert old.get('/sessions/current', headers={'Authorization':'Bearer '+revision['session_token']}).status_code == 401


def test_account_mutations_require_https_for_remote_clients(account_env):
    make, path = account_env
    with TestClient(app, base_url='http://public.example', headers={'X-Study-Coach':'1'}) as client:
        response = client.post('/account/register', json={'username':'new_user','password':PASSWORD})
        assert response.status_code == 400 and 'HTTPS' in response.text


def test_atomic_password_change_rolls_back_on_session_insert_failure(account_env):
    make, path = account_env
    client = make(); register(client)
    with ProgressStore(path).connect() as db:
        db.execute("CREATE TRIGGER reject_new_login BEFORE INSERT ON account_logins BEGIN SELECT RAISE(ABORT,'private-storage-details'); END")
    response = client.post('/account/password', json={'current_password':PASSWORD,'new_password':REPLACEMENT})
    assert response.status_code == 503
    assert 'private-storage-details' not in response.text
    assert client.get('/account/me').json()['authenticated'] is True
    with ProgressStore(path).connect() as db: db.execute('DROP TRIGGER reject_new_login')
    second = make()
    assert login(second).status_code == 200
    assert login(second,password=REPLACEMENT).status_code == 401


def test_existing_progress_is_backed_up_before_additive_migration(tmp_path):
    import sqlite3
    path = tmp_path/'old-progress.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE study_sessions(token_hash TEXT PRIMARY KEY,version INTEGER NOT NULL,payload TEXT NOT NULL)')
        db.execute('INSERT INTO study_sessions VALUES (?,0,?)', (ProgressStore.digest('old-token'),json.dumps({'history':['kept']})))
    store = ProgressStore(path)
    assert store.load('old-token')[1]['history'] == ['kept']
    backup = next((tmp_path/'account_migration_backups').glob('*.sqlite3'))
    assert backup.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(backup) as db:
        assert json.loads(db.execute('SELECT payload FROM study_sessions').fetchone()[0])['history'] == ['kept']
    ProgressStore(path)
    assert len(list((tmp_path/'account_migration_backups').glob('*.sqlite3'))) == 1
