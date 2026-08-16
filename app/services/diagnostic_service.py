from app.models.diagnostic import DiagnosticSubmission, DiagnosticResult
from app.repositories.question_repository import load_questions


def evaluate_diagnostic(
    submission: DiagnosticSubmission,
) -> list[DiagnosticResult]:
    questions = {question.id: question for question in load_questions()}

    results = []

    for answer in submission.answers:
        question = questions.get(answer.question_id)

        if question is None:
            continue

        if answer.selected_answer is None:
            is_correct = False
            error_type = "unanswered"
        else:
            is_correct = answer.selected_answer == question.correct_answer
            error_type = "correct" if is_correct else "concept_error"

        results.append(
            DiagnosticResult(
                question_id=question.id,
                topic=question.topic,
                subtopic=question.subtopic,
                is_correct=is_correct,
                error_type=error_type,
            )
        )

    return results