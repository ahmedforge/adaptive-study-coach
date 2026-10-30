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

@pytest.mark.parametrize('changes', [
    {'question': ' '}, {'explanation': '\n'},
    {'options': ['2', '3', '4', '']},
    {'options': ['2', '3', '4', ' 4 ']},
    {'options': ['A', 'a', '4', '5']},
    {'options': ['2', '3', '4', 5]},
    {'correct_answer': '6'}, {'unexpected': True},
])
def test_invalid_mcq_shape_is_rejected(changes):
    with pytest.raises(ValidationError):
        GeneratedQuestion(**{
            'question': 'What is 2 + 2?', 'options': ['2', '3', '4', '5'],
            'correct_answer': '4', 'explanation': 'Two plus two equals four.', **changes,
        })


def test_fields_are_trimmed_before_matching_answer():
    question = GeneratedQuestion(question='  What is 2 + 2? ',
        options=[' 2 ', '3', ' 4 ', '5'], correct_answer=' 4 ', explanation=' Four. ')
    assert question.correct_answer == '4'
    assert question.options == ['2', '3', '4', '5']
    assert question.explanation == 'Four.'
