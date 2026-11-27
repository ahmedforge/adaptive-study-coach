import os
from collections import Counter

from app.models.agent_state import AgentState
from app.services.retrieval_service import retriever
from app.services.variant_generation_service import generate_variant


def identify_weak_topics(state: AgentState) -> AgentState:
    mistakes = [
        result.topic
        for result in state.diagnostic_results
        if not result.is_correct
    ]

    topic_counts = Counter(mistakes)

    state.weak_topics = [
        topic
        for topic, _ in topic_counts.most_common()
    ]

    if state.weak_topics:
        state.current_topic = state.weak_topics[0]
        state.status = "practicing"
    else:
        state.current_topic = None
        state.status = "complete"

    return state
def update_after_practice(
    state: AgentState,
    is_correct: bool,
) -> AgentState:
    if state.current_topic is None:
        state.status = "complete"
        return state

    if not is_correct:
        state.correct_streak = 0
        state.attempts_on_topic += 1
        state.status = "practicing"
        return state

    state.correct_streak += 1
    if state.correct_streak < state.target_correct:
        state.status = "practicing"
        return state

    state.correct_streak = 0
    state.attempts_on_topic = 0

    if state.current_topic in state.weak_topics:
        state.weak_topics.remove(state.current_topic)

    if state.weak_topics:
        state.current_topic = state.weak_topics[0]
        state.status = "practicing"
    else:
        state.current_topic = None
        state.status = "complete"

    return state



def get_practice_question(state: AgentState, *, recent_question_ids: list[str] | None = None):
    if state.current_topic is None:
        return None

    seen_ids = [result.question_id for result in state.diagnostic_results] + (recent_question_ids or [])
    if os.getenv("STUDY_COACH_PRACTICE_RETRIEVAL", "bank").lower() != "semantic":
        seen = {question_id: i for i, question_id in enumerate(seen_ids)}
        candidates = (question for question in retriever.questions if question.topic == state.current_topic)
        seed = min(candidates, key=lambda q: seen.get(q.id, -1), default=None)
        return generate_variant(seed) if seed is not None else None

    results = retriever.search(
        query=state.current_topic,
        top_k=1,
        topic=state.current_topic,
        recent_question_ids=seen_ids,
    )

    if not results or results[0]["question"].topic != state.current_topic:
        return None

    seed_question = results[0]["question"]

    return generate_variant(seed_question)