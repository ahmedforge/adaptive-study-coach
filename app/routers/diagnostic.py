from fastapi import APIRouter

from app.models.diagnostic import DiagnosticResponse, DiagnosticSubmission
from app.services.diagnostic_service import evaluate_diagnostic
from app.repositories.question_repository import load_questions

router = APIRouter(
    prefix="/diagnostic",
    tags=["diagnostic"],
)


@router.post("/submit", response_model=DiagnosticResponse)
def submit_diagnostic(
    submission: DiagnosticSubmission,
) -> DiagnosticResponse:
    results = evaluate_diagnostic(submission)

    return DiagnosticResponse(results=results)
@router.get("/questions")
def get_diagnostic_questions():
    questions = load_questions()[:12]

    return {
        "questions": [
            {
                "id": question.id,
                "question": question.question,
                "options": question.options,
            }
            for question in questions
        ]
    }