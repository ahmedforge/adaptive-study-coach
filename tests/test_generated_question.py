import pytest
from pydantic import ValidationError

from app.models.generated_question import GeneratedQuestion


def test_generated_question_accepts_valid_mcq():
    question = GeneratedQuestion(
        question="What is 2 + 2?",
        options=["2", "3", "4", "5"],
        correct_answer="4",
        explanation="2 + 2 = 4.",
    )

    assert question.correct_answer == "4"


def test_generated_question_rejects_invalid_answer():
    with pytest.raises(ValidationError):
        GeneratedQuestion(
            question="What is 2 + 2?",
            options=["2", "3", "4", "5"],
            correct_answer="6",
            explanation="2 + 2 = 4.",
        )