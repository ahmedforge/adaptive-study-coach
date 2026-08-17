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