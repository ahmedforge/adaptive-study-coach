def normalize_answer(answer: str) -> str:
    return answer.strip().lower()


def grade_answer(
    selected_answer: str | None,
    correct_answer: str,
) -> dict:
    if selected_answer is None or not selected_answer.strip():
        return {
            "is_correct": False,
            "error_type": "unanswered",
        }

    is_correct = normalize_answer(selected_answer) == normalize_answer(
        correct_answer
    )

    return {
        "is_correct": is_correct,
        "error_type": "correct" if is_correct else "concept_error",
    }