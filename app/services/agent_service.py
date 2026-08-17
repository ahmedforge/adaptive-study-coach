from collections import Counter

from app.models.agent_state import AgentState
from app.services.retrieval_service import QuestionRetriever
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
        state.attempts_on_topic += 1
        state.status = "practicing"
        return state

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

retriever = QuestionRetriever()


def get_practice_question(state: AgentState):
    if state.current_topic is None:
        return None

    results = retriever.search(
        query=state.current_topic,
        top_k=1,
    )

    if not results:
        return None

    seed_question = results[0]["question"]

    return generate_variant(seed_question)