from fastapi import APIRouter, HTTPException

from app.models.agent_state import AgentState
from app.services.retrieval_service import RetrievalUnavailable
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

    try:
        practice_question = get_practice_question(state)
    except RetrievalUnavailable as exc:
        raise HTTPException(503, 'Practice is temporarily unavailable. Please retry.') from exc

    return {
        "state": state,
        "practice_question": practice_question,
    }


@router.post("/advance")
def advance_agent(state: AgentState, is_correct: bool):
    state = update_after_practice(state, is_correct)

    try:
        practice_question = get_practice_question(state)
    except RetrievalUnavailable as exc:
        raise HTTPException(503, 'Practice is temporarily unavailable. Please retry.') from exc

    return {
        "state": state,
        "practice_question": practice_question,
    }