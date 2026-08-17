from app.services.grading_service import grade_answer


def test_correct_answer():
    result = grade_answer("4 and 5", "4 and 5")

    assert result["is_correct"] is True
    assert result["error_type"] == "correct"


def test_case_and_whitespace_are_ignored():
    result = grade_answer("  CLOSURE PROPERTY  ", "Closure Property")

    assert result["is_correct"] is True


def test_wrong_answer():
    result = grade_answer("3 and 4", "4 and 5")

    assert result["is_correct"] is False
    assert result["error_type"] == "concept_error"


def test_unanswered():
    result = grade_answer(None, "4 and 5")

    assert result["is_correct"] is False
    assert result["error_type"] == "unanswered"