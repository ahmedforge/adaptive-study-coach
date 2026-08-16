from fastapi import APIRouter

from app.models.diagnostic import DiagnosticResponse, DiagnosticSubmission
from app.services.diagnostic_service import evaluate_diagnostic


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