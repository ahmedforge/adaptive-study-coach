from pydantic import BaseModel


class Question(BaseModel):
    id: str
    topic: str
    subtopic: str
    difficulty: str
    question: str
    options: list[str]
    correct_answer: str
    explanation: str
    source: str