from typing import Literal

from pydantic import Field

from app.models.generated_question import GeneratedQuestion


class Question(GeneratedQuestion):
    """A bank MCQ with validated metadata and the shared four-option contract."""
    id: str = Field(min_length=1, max_length=100, pattern=r'^[a-z0-9]+(?:_[a-z0-9]+)*$')
    topic: str = Field(min_length=1, max_length=100, pattern=r'^[a-z0-9]+(?:_[a-z0-9]+)*$')
    subtopic: str = Field(min_length=1, max_length=100, pattern=r'^[a-z0-9]+(?:_[a-z0-9]+)*$')
    difficulty: Literal['easy', 'medium', 'hard']
    source: str = Field(min_length=1, max_length=1000)
