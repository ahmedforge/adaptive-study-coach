"""Optional local accounts; browser sessions use HttpOnly expiring cookies."""
import hashlib
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.repositories.account_repository import AccountRepository
from app.routers.sessions import get_store
from app.services.account_service import (COOKIE, DUMMY_HASH, SESSION_SECONDS,
    check_mutation, hasher, secure_cookie, verify_password)

router = APIRouter(prefix='/account', tags=['accounts'])


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    username: str = Field(pattern=r'^[a-z][a-z0-9_]{2,31}$')
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator('username', mode='before')
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class OwnedSession(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(pattern=r'^[a-f0-9]{64}$')


class ClaimReference(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: str = Field(pattern=r'^(practice|exam)$')
    token: str = Field(min_length=1, max_length=100)


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    sessions: list[ClaimReference] = Field(max_length=50)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=12, max_length=128)


def require_account(store):
    if not store.user_id: raise HTTPException(401, 'Sign in to access account progress.')
    return store.user_id


def attempts(request, repository, username, action='login'):
    peer = request.client.host if request.client else 'unknown'
    key = hashlib.sha256(f'{action}:{peer}:{username}'.encode()).hexdigest()
    global_key = hashlib.sha256(f'{action}:{peer}:all'.encode()).hexdigest()
    if not repository.reserve_attempt(global_key, limit=100) or not repository.reserve_attempt(key):
        raise HTTPException(429, 'Too many attempts. Please try again in 15 minutes.')


def set_cookie(request, response, token):
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=secure_cookie(request), samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'


def set_login(request, response, repo, user_id):
    set_cookie(request, response, repo.login(user_id, request.cookies.get(COOKIE)))


@router.get('/me')
def me(response: Response, store=Depends(get_store)):
    response.headers['Cache-Control'] = 'no-store'
    if not store.user_id: return {'authenticated': False}
    with store.connect() as db:
        row = db.execute('SELECT username FROM accounts WHERE id=?', (store.user_id,)).fetchone()
    return {'authenticated': True, 'username': row[0]}


@router.post('/register', status_code=201)
def register(details: Credentials, request: Request, response: Response, store=Depends(get_store)):
    check_mutation(request)
    if store.user_id: raise HTTPException(409, 'Sign out before creating a different account.')
    repo = AccountRepository(store)
    attempts(request, repo, details.username, action='register')
    encoded = hasher.hash(details.password.get_secret_value())
    try:
        user = repo.create(details.username, encoded)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, 'That username is unavailable.') from exc
    set_login(request, response, repo, user['id'])
    return {'authenticated': True, 'username': user['username']}


@router.post('/login')
def login(details: Credentials, request: Request, response: Response, store=Depends(get_store)):
    check_mutation(request)
    repo = AccountRepository(store)
    attempts(request, repo, details.username)
    user = repo.find(details.username)
    valid = verify_password(user['password_hash'] if user else DUMMY_HASH, details.password.get_secret_value())
    if not user or not valid: raise HTTPException(401, 'Username or password is incorrect.')
    if hasher.check_needs_rehash(user['password_hash']):
        with store.connect() as db:
            db.execute('UPDATE accounts SET password_hash=? WHERE id=?',
                       (hasher.hash(details.password.get_secret_value()), user['id']))
    set_login(request, response, repo, user['id'])
    return {'authenticated': True, 'username': user['username']}


@router.post('/logout')
def logout(request: Request, response: Response, store=Depends(get_store)):
    check_mutation(request)
    AccountRepository(store).logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path='/', httponly=True, secure=secure_cookie(request), samesite='lax')
    return {'authenticated': False}


@router.post('/logout-all')
def logout_all(request: Request, response: Response, store=Depends(get_store)):
    check_mutation(request)
    user_id = require_account(store)
    with store.connect() as db: db.execute('DELETE FROM account_logins WHERE user_id=?', (user_id,))
    response.delete_cookie(COOKIE, path='/', httponly=True, secure=secure_cookie(request), samesite='lax')
    return {'authenticated': False}


@router.post('/password')
def change_password(details: PasswordChange, request: Request, response: Response, store=Depends(get_store)):
    check_mutation(request)
    user_id = require_account(store)
    repo = AccountRepository(store)
    attempts(request, repo, user_id, action='password')
    with store.connect() as db:
        encoded = db.execute('SELECT password_hash FROM accounts WHERE id=?', (user_id,)).fetchone()[0]
    if not verify_password(encoded, details.current_password.get_secret_value()):
        raise HTTPException(401, 'Current password is incorrect.')
    replacement = hasher.hash(details.new_password.get_secret_value())
    set_cookie(request, response, repo.replace_password(user_id, replacement))
    return {'changed': True}


@router.get('/library')
def library(response: Response, limit: int = Query(default=50, ge=1, le=50),
            offset: int = Query(default=0, ge=0), store=Depends(get_store)):
    require_account(store)
    response.headers['Cache-Control'] = 'no-store'
    references = store.library(limit + 1, offset)
    return {'sessions': references[:limit], 'has_more': len(references) > limit, 'offset': offset}


@router.post('/open')
def open_session(reference: OwnedSession, request: Request, response: Response, store=Depends(get_store)):
    check_mutation(request)
    require_account(store)
    record = store.load_owned(reference.id)
    if record is None: raise HTTPException(404, 'That session is not available in this account.')
    token = store.issue_alias(reference.id)
    response.headers['Cache-Control'] = 'no-store'
    return {'session_token': token, 'kind': 'exam' if record[1].get('kind') == 'exam' else 'practice'}


@router.post('/claim')
def claim_sessions(details: ClaimRequest, request: Request, store=Depends(get_store)):
    check_mutation(request)
    require_account(store)
    seen, imported, unavailable = set(), 0, 0
    for ref in details.sessions:
        key = (ref.kind, ref.token)
        if key in seen: continue
        seen.add(key)
        if store.claim(ref.token, ref.kind): imported += 1
        else: unavailable += 1
    return {'available_in_account': imported, 'unavailable': unavailable}
