from app.models.diagnostic import DiagnosticSubmission, DiagnosticResult
from app.repositories.question_repository import load_questions
from app.services.grading_service import grade_answer


def evaluate_diagnostic(
    submission: DiagnosticSubmission,
) -> list[DiagnosticResult]:
    questions = {question.id: question for question in load_questions()}

    results = []

    for answer in submission.answers:
        question = questions.get(answer.question_id)

        if question is None:
            raise ValueError(f"Unknown question_id: {answer.question_id}")

        grade = grade_answer(
            selected_answer=answer.selected_answer,
            correct_answer=question.correct_answer,
        )

        results.append(
            DiagnosticResult(
                question_id=question.id,
                topic=question.topic,
                subtopic=question.subtopic,
                is_correct=grade["is_correct"],
                error_type=grade["error_type"],
            )
        )

    return results



def summarize_diagnostic(results: list[DiagnosticResult]) -> dict:
    """Describe this diagnostic sample without inferring mastery or error causes."""
    totals = {'total': len(results), 'correct': 0, 'incorrect': 0, 'unanswered': 0}
    topics = {}
    for result in results:
        topic = topics.setdefault(result.topic, {
            'topic': result.topic, 'total': 0, 'correct': 0, 'incorrect': 0, 'unanswered': 0})
        category = ('correct' if result.is_correct else
                    'unanswered' if result.error_type == 'unanswered' else 'incorrect')
        totals[category] += 1
        topic['total'] += 1
        topic[category] += 1
    return {**totals, 'topics': list(topics.values())}
