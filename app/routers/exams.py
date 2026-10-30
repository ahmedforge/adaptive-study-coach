"""Timed, resumable bank-based mock exams; answers stay private until completion."""
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field

from app.models.diagnostic import DiagnosticResult
from app.repositories.question_repository import load_questions
from app.routers.sessions import bearer, get_store
from app.services.diagnostic_service import summarize_diagnostic

router = APIRouter(prefix='/exams', tags=['mock exams'])


def utc_now():
    return datetime.now(timezone.utc)


class ExamSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question_count: Literal[12, 24] = 12
    duration_minutes: int = Field(default=30, ge=5, le=120)


class DraftAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    question_id: str = Field(min_length=1, max_length=100)
    selected_answer: str | None = Field(default=None, max_length=300)
    version: int = Field(ge=0)


def select_questions(count):
    """Round-robin shuffled topic pools give equal coverage without duplicates."""
    rng = random.SystemRandom()
    pools = {}
    for question in load_questions():
        pools.setdefault(question.topic, []).append(question)
    for pool in pools.values():
        rng.shuffle(pool)
    topics = list(pools)
    rng.shuffle(topics)
    selected = []
    while len(selected) < count:
        added = False
        for topic in topics:
            if pools[topic]:
                selected.append(pools[topic].pop().model_dump())
                added = True
                if len(selected) == count:
                    return selected
        if not added:
            raise HTTPException(503, 'The question bank cannot supply this exam size.')
    return selected


def read_exam(store, token):
    if len(token) > 100:
        raise HTTPException(401, 'Exam not found. Start a new mock exam.')
    try:
        record = store.load(token)
    except sqlite3.Error as exc:
        raise HTTPException(503, 'Exam storage is unavailable. Please retry.') from exc
    if record is None or record[1].get('kind') != 'exam':
        raise HTTPException(401, 'Exam not found. Start a new mock exam.')
    return record


def save_exam(store, token, version, data):
    try:
        saved = store.save(token, version, data)
    except sqlite3.Error as exc:
        raise HTTPException(503, 'Exam changes were not confirmed. Resume to check saved answers.') from exc
    if not saved:
        raise HTTPException(409, 'The exam changed in another tab. Resume to load saved answers.')
    return version + 1, data


def finish(data, reason):
    data['status'] = 'completed'
    data['completion_reason'] = reason
    data['completed_at'] = (data['expires_at'] if reason == 'time_expired' else utc_now().isoformat())


def expire_if_needed(store, token, version, data):
    if data['status'] == 'active' and utc_now() >= datetime.fromisoformat(data['expires_at']):
        finish(data, 'time_expired')
        return save_exam(store, token, version, data)
    return version, data


def public_exam(version, data):
    response = {key: data[key] for key in ['status', 'started_at', 'expires_at', 'duration_minutes']}
    response.update(version=version, server_now=utc_now().isoformat(), answers=data['answers'],
        questions=[{key: q[key] for key in ['id', 'topic', 'question', 'options']} for q in data['questions']])
    if data['status'] == 'completed':
        results = []
        diagnostic = []
        for q in data['questions']:
            selected = data['answers'].get(q['id'])
            correct = selected == q['correct_answer']
            results.append({key: q[key] for key in ['id', 'topic', 'question', 'correct_answer', 'explanation']}
                           | {'selected_answer': selected, 'is_correct': correct})
            diagnostic.append(DiagnosticResult(question_id=q['id'], topic=q['topic'],
                subtopic=q['subtopic'], is_correct=correct,
                error_type='correct' if correct else 'unanswered' if selected is None else 'concept_error'))
        summary = summarize_diagnostic(diagnostic)
        response.update(results=results, summary=summary,
            score_percent=round(100 * summary['correct'] / summary['total'], 1),
            completion_reason=data['completion_reason'], completed_at=data['completed_at'])
    return response


@router.post('', status_code=201)
def create_exam(settings: ExamSettings, store=Depends(get_store)):
    started = utc_now()
    data = {'kind': 'exam', 'status': 'active', 'started_at': started.isoformat(),
        'expires_at': (started + timedelta(minutes=settings.duration_minutes)).isoformat(),
        'duration_minutes': settings.duration_minutes, 'questions': select_questions(settings.question_count),
        'answers': {}}
    try:
        token = store.create(data)
    except sqlite3.Error as exc:
        raise HTTPException(503, 'Could not save the exam. Please retry.') from exc
    return {'exam_token': token, **public_exam(0, data)}


@router.get('/current')
def resume_exam(credentials: HTTPAuthorizationCredentials = Depends(bearer), store=Depends(get_store)):
    version, data = read_exam(store, credentials.credentials)
    version, data = expire_if_needed(store, credentials.credentials, version, data)
    return public_exam(version, data)


@router.put('/current/answers')
def save_answer(answer: DraftAnswer, credentials: HTTPAuthorizationCredentials = Depends(bearer),
                store=Depends(get_store)):
    token = credentials.credentials
    version, data = read_exam(store, token)
    version, data = expire_if_needed(store, token, version, data)
    if data['status'] != 'active':
        raise HTTPException(409, 'This exam is complete. Resume to view the report.')
    question = next((q for q in data['questions'] if q['id'] == answer.question_id), None)
    if question is None or (answer.selected_answer is not None and answer.selected_answer not in question['options']):
        raise HTTPException(422, 'Choose a listed exam option or clear the answer.')
    if answer.version != version:
        # An identical retry after response loss is safe; never overwrite newer changes.
        if data['answers'].get(answer.question_id) == answer.selected_answer:
            return public_exam(version, data)
        raise HTTPException(409, 'The exam changed. Resume to load saved answers before editing.')
    if answer.selected_answer is None:
        data['answers'].pop(answer.question_id, None)
    else:
        data['answers'][answer.question_id] = answer.selected_answer
    version, data = save_exam(store, token, version, data)
    return public_exam(version, data)


@router.post('/current/submit')
def submit_exam(credentials: HTTPAuthorizationCredentials = Depends(bearer), store=Depends(get_store)):
    token = credentials.credentials
    version, data = read_exam(store, token)
    version, data = expire_if_needed(store, token, version, data)
    if data['status'] == 'active':
        finish(data, 'submitted')
        version, data = save_exam(store, token, version, data)
    return public_exam(version, data)
