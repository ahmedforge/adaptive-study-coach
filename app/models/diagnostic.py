from pydantic import BaseModel


class DiagnosticAnswer(BaseModel):
    question_id: str
    selected_answer: str | None = None


class DiagnosticSubmission(BaseModel):
    answers: list[DiagnosticAnswer]


class DiagnosticResult(BaseModel):
    question_id: str
    topic: str
    subtopic: str
    is_correct: bool
    error_type: str


class DiagnosticResponse(BaseModel):
    results: list[DiagnosticResult]