"""Resumable local study sessions with server-side grading and stale-answer checks."""
import os
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from app.models.agent_state import AgentState
from app.models.diagnostic import DiagnosticSubmission
from app.repositories.progress_repository import ProgressStore
from app.repositories.question_repository import load_questions
from app.services.agent_service import get_practice_question, identify_weak_topics, update_after_practice
from app.services.diagnostic_service import evaluate_diagnostic

router = APIRouter(prefix='/sessions', tags=['saved progress'])
bearer = HTTPBearer()


def get_store():
    try:
        return ProgressStore(os.getenv('STUDY_COACH_DB', 'progress_data/progress.sqlite3'))
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, 'Saved progress is unavailable. Please try again.') from exc


def now():
    return datetime.now(timezone.utc).isoformat()


def read_session(store, token):
    if len(token) > 100:
        raise HTTPException(401, 'Saved session not found. Start a new diagnostic.')
    try:
        record = store.load(token)
    except sqlite3.Error as exc:
        raise HTTPException(503, 'Saved progress is unavailable. Please try again.') from exc
    if record is None:
        raise HTTPException(401, 'Saved session not found. Start a new diagnostic.')
    return record


def question_record(state):
    question = get_practice_question(state)
    if state.status != 'complete' and question is None:
        raise HTTPException(503, 'Practice is unavailable. Your previous progress is unchanged.')
    return ({**question.model_dump(), 'id': uuid4().hex} if question else None)


def public_session(data):
    question = data['question']
    return {
        'state': data['state'],
        'practice_question': ({key: question[key] for key in
            ['id', 'question', 'options', 'generation_source']} if question else None),
        'history': data['history'], 'updated_at': data['updated_at'],
    }


@router.post('', status_code=201)
def create_session(submission: DiagnosticSubmission, store=Depends(get_store)):
    questions = load_questions()[:12]
    expected = {q.id: q for q in questions}
    ids = [answer.question_id for answer in submission.answers]
    if len(ids) != len(expected) or set(ids) != set(expected):
        raise HTTPException(422, 'Submit each diagnostic question exactly once.')
    if any(a.selected_answer is not None and a.selected_answer not in expected[a.question_id].options
           for a in submission.answers):
        raise HTTPException(422, 'Select a listed diagnostic option or leave it unanswered.')
    state = identify_weak_topics(AgentState(diagnostic_results=evaluate_diagnostic(submission)))
    data = {'state': state.model_dump(), 'question': question_record(state),
            'history': [], 'updated_at': now(), 'last_answer': None}
    try:
        token = store.create(data)
    except sqlite3.Error as exc:
        raise HTTPException(503, 'Could not save the session. Please try again.') from exc
    return {'session_token': token, **public_session(data)}


@router.get('/current')
def resume_session(credentials: HTTPAuthorizationCredentials = Depends(bearer), store=Depends(get_store)):
    _, data = read_session(store, credentials.credentials)
    return public_session(data)


class PracticeAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question_id: str = Field(min_length=1, max_length=64)
    selected_answer: str = Field(min_length=1, max_length=300)


@router.post('/current/answers')
def answer_question(answer: PracticeAnswer,
                    credentials: HTTPAuthorizationCredentials = Depends(bearer), store=Depends(get_store)):
    token = credentials.credentials
    version, data = read_session(store, token)
    # A retry after a lost response returns the already-saved result.
    if data['last_answer'] == answer.model_dump():
        return public_session(data)
    question = data['question']
    if question is None or question['id'] != answer.question_id:
        raise HTTPException(409, 'This question has already changed. Resume your saved session.')
    if answer.selected_answer not in question['options']:
        raise HTTPException(422, 'Select one of the listed options.')
    state = AgentState.model_validate(data['state'])
    is_correct = answer.selected_answer == question['correct_answer']
    attempt = {'question_id': question['id'], 'topic': state.current_topic,
        'question': question['question'], 'selected_answer': answer.selected_answer,
        'correct_answer': question['correct_answer'], 'is_correct': is_correct,
        'explanation': question['explanation'], 'answered_at': now()}
    state = update_after_practice(state, is_correct)
    # Model/retrieval work happens before the short optimistic database update.
    data['question'] = question_record(state)
    data['state'] = state.model_dump()
    data['history'].append(attempt)
    data['last_answer'] = answer.model_dump()
    data['updated_at'] = now()
    try:
        saved = store.save(token, version, data)
    except sqlite3.Error as exc:
        raise HTTPException(503, 'Your answer was not saved. Please retry.') from exc
    if not saved:
        _, current = read_session(store, token)
        if current['last_answer'] == answer.model_dump():
            return public_session(current)
        raise HTTPException(409, 'Progress changed in another tab. Resume the saved session.')
    return public_session(data)
