from app.repositories.question_repository import load_questions


def test_load_questions():
    questions = load_questions()

    assert len(questions) > 0
    assert len({q.id for q in questions}) == len(questions)

    for question in questions:
        assert len(question.options) == 4
        assert question.correct_answer in question.options