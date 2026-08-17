from fastapi import APIRouter

from app.models.agent_state import AgentState
from app.services.agent_service import (
    get_practice_question,
    identify_weak_topics,
    update_after_practice,
)


router = APIRouter(
    prefix="/agent",
    tags=["agent"],
)


@router.post("/start")
def start_agent(state: AgentState):
    state = identify_weak_topics(state)

    practice_question = get_practice_question(state)

    return {
        "state": state,
        "practice_question": practice_question,
    }


@router.post("/advance")
def advance_agent(state: AgentState, is_correct: bool):
    state = update_after_practice(state, is_correct)

    practice_question = get_practice_question(state)

    return {
        "state": state,
        "practice_question": practice_question,
    }