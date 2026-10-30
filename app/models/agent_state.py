from pydantic import BaseModel, Field

from app.models.diagnostic import DiagnosticResult


class AgentState(BaseModel):
    diagnostic_results: list[DiagnosticResult]
    weak_topics: list[str] = []
    current_topic: str | None = None
    attempts_on_topic: int = 0
    # Defaults preserve sessions created before practice targets were introduced.
    target_correct: int = Field(default=1, ge=1, le=5)
    correct_streak: int = Field(default=0, ge=0)
    status: str = "diagnosing"
