from pydantic import BaseModel

from app.models.diagnostic import DiagnosticResult


class AgentState(BaseModel):
    diagnostic_results: list[DiagnosticResult]
    weak_topics: list[str] = []
    current_topic: str | None = None
    attempts_on_topic: int = 0
    status: str = "diagnosing"