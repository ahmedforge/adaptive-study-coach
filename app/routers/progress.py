"""Summaries of sessions the caller can access; no global learner/session listing."""
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.agent_state import AgentState
from app.routers.exams import exam_diagnostic_results
from app.routers.sessions import get_store

router = APIRouter(prefix='/progress', tags=['progress dashboard'])


class SessionReference(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['practice', 'exam']
    token: str | None = Field(default=None, min_length=1, max_length=100)
    id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def one_reference(self):
        if (self.token is None) == (self.id is None):
            raise ValueError('Provide exactly one token or account session ID.')
        return self


class SummaryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    sessions: list[SessionReference] = Field(max_length=50)


@router.post('/summary')
def progress_summary(request: SummaryRequest, store=Depends(get_store)):
    entries, unavailable, seen = [], [], set()
    topics = defaultdict(lambda: {'practice_correct': 0, 'practice_total': 0,
                                  'exam_correct': 0, 'exam_total': 0})
    totals = {'practice_sessions': 0, 'practice_answers': 0, 'practice_correct': 0,
              'exams': 0, 'completed_exams': 0}
    for index, reference in enumerate(request.sessions):
        identity = (reference.kind, reference.token, reference.id)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            record = store.load_owned(reference.id) if reference.id else store.load(reference.token)
        except sqlite3.Error as exc:
            raise HTTPException(503, 'Progress is unavailable. Your saved sessions are unchanged. Please retry.') from exc
        if record is None or (record[1].get('kind') == 'exam') != (reference.kind == 'exam'):
            unavailable.append(index)
            continue
        data = record[1]
        if reference.kind == 'practice':
            state = AgentState.model_validate(data['state'])
            history = data['history']
            correct = sum(attempt['is_correct'] for attempt in history)
            entries.append({'index': index, 'kind': 'practice', 'status': state.status,
                'assessment_source': data.get('assessment_source', 'diagnostic'),
                'timestamp': data['updated_at'], 'timestamp_label': 'Last saved',
                'answers': len(history), 'correct': correct, 'current_topic': state.current_topic,
                'remaining_topics': state.weak_topics, 'correct_streak': state.correct_streak,
                'target_correct': state.target_correct})
            totals['practice_sessions'] += 1
            totals['practice_answers'] += len(history)
            totals['practice_correct'] += correct
            for attempt in history:
                topics[attempt['topic']]['practice_total'] += 1
                topics[attempt['topic']]['practice_correct'] += int(attempt['is_correct'])
        else:
            totals['exams'] += 1
            completed = data['status'] == 'completed'
            expired = not completed and datetime.now(timezone.utc) >= datetime.fromisoformat(data['expires_at'])
            entry = {'index': index, 'kind': 'exam',
                'status': 'completed' if completed else 'time_elapsed' if expired else 'active',
                'timestamp': data['completed_at'] if completed else data['started_at'],
                'timestamp_label': 'Completed' if completed else 'Started',
                'question_count': len(data['questions']), 'answered': len(data['answers']),
                'expires_at': data['expires_at']}
            if completed:
                totals['completed_exams'] += 1
                results = exam_diagnostic_results(data)
                correct = sum(result.is_correct for result in results)
                entry.update(correct=correct, score_percent=round(100 * correct / len(results), 1))
                for result in results:
                    topics[result.topic]['exam_total'] += 1
                    topics[result.topic]['exam_correct'] += int(result.is_correct)
            entries.append(entry)
    entries.sort(key=lambda entry: entry['timestamp'], reverse=True)
    topic_results = [{'topic': topic, **counts} for topic, counts in sorted(topics.items())]
    revisit = sorted(({'topic': row['topic'],
        'missed': row['exam_total'] - row['exam_correct']} for row in topic_results
        if row['exam_total'] > row['exam_correct']), key=lambda row: (-row['missed'], row['topic']))[:5]
    return {'totals': totals, 'sessions': entries, 'unavailable': unavailable,
            'topics': topic_results, 'revisit': revisit}
