from app.models.agent_state import AgentState
from app.models.diagnostic import DiagnosticResult
from app.services.agent_service import (
    identify_weak_topics,
    update_after_practice,
)


def test_identify_weak_topics():
    state = AgentState(
        diagnostic_results=[
            DiagnosticResult(
                question_id="q1",
                topic="algebra",
                subtopic="linear_equations",
                is_correct=False,
                error_type="concept_error",
            ),
            DiagnosticResult(
                question_id="q2",
                topic="algebra",
                subtopic="quadratics",
                is_correct=False,
                error_type="concept_error",
            ),
            DiagnosticResult(
                question_id="q3",
                topic="trigonometry",
                subtopic="basic_ratios",
                is_correct=False,
                error_type="concept_error",
            ),
        ]
    )

    state = identify_weak_topics(state)

    assert state.weak_topics == ["algebra", "trigonometry"]
    assert state.current_topic == "algebra"
    assert state.status == "practicing"


def test_wrong_answer_repeats_topic():
    state = AgentState(
        diagnostic_results=[],
        weak_topics=["algebra", "trigonometry"],
        current_topic="algebra",
        status="practicing",
    )

    state = update_after_practice(state, is_correct=False)

    assert state.current_topic == "algebra"
    assert state.attempts_on_topic == 1
    assert state.status == "practicing"


def test_correct_answer_advances_topic():
    state = AgentState(
        diagnostic_results=[],
        weak_topics=["algebra", "trigonometry"],
        current_topic="algebra",
        status="practicing",
    )

    state = update_after_practice(state, is_correct=True)

    assert state.weak_topics == ["trigonometry"]
    assert state.current_topic == "trigonometry"
    assert state.attempts_on_topic == 0


def test_last_topic_complete():
    state = AgentState(
        diagnostic_results=[],
        weak_topics=["algebra"],
        current_topic="algebra",
        status="practicing",
    )

    state = update_after_practice(state, is_correct=True)

    assert state.weak_topics == []
    assert state.current_topic is None
    assert state.status == "complete"

from types import SimpleNamespace
import app.services.agent_service as service


def test_practice_passes_topic_and_seen_diagnostic_and_practice_ids(monkeypatch):
    calls = {}
    seed = SimpleNamespace(id='seed2', topic='algebra')
    def search(**kwargs):
        calls.update(kwargs)
        return [{'question': seed, 'score': .6}]
    monkeypatch.setattr(service, 'retriever', SimpleNamespace(search=search))
    monkeypatch.setattr(service, 'generate_variant', lambda seed: seed.id)
    state = AgentState(diagnostic_results=[DiagnosticResult(question_id='diagnostic-seed',
        topic='algebra', subtopic='addition', is_correct=False, error_type='concept_error')],
        current_topic='algebra', weak_topics=['algebra'], status='practicing')
    assert service.get_practice_question(state, recent_question_ids=['previous-seed']) == 'seed2'
    assert calls['topic'] == 'algebra'
    assert calls['recent_question_ids'] == ['diagnostic-seed', 'previous-seed']


def test_wrong_topic_result_cannot_be_generated(monkeypatch):
    monkeypatch.setattr(service, 'retriever', SimpleNamespace(search=lambda **kwargs:
        [{'question': SimpleNamespace(topic='trigonometry'), 'score': .9}]))
    monkeypatch.setattr(service, 'generate_variant', lambda seed: (_ for _ in ()).throw(AssertionError('must not generate')))
    state = AgentState(diagnostic_results=[], current_topic='algebra')
    assert service.get_practice_question(state) is None


def test_target_requires_consecutive_correct_and_resets_between_topics():
    state = AgentState(diagnostic_results=[], weak_topics=['algebra', 'trigonometry'],
        current_topic='algebra', status='practicing', target_correct=2)
    update_after_practice(state, True)
    assert state.current_topic == 'algebra'
    assert state.correct_streak == 1
    update_after_practice(state, False)
    assert state.correct_streak == 0
    update_after_practice(state, True)
    assert state.current_topic == 'algebra'
    update_after_practice(state, True)
    assert state.current_topic == 'trigonometry'
    assert state.correct_streak == 0
    assert state.attempts_on_topic == 0
    update_after_practice(state, True)
    assert state.status == 'practicing'
    update_after_practice(state, True)
    assert state.status == 'complete'
    assert state.correct_streak == 0
