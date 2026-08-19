import pytest

from app.models.diagnostic import DiagnosticAnswer, DiagnosticSubmission
from app.services.diagnostic_service import evaluate_diagnostic


def test_evaluate_diagnostic():
    submission = DiagnosticSubmission(
        answers=[
            DiagnosticAnswer(
                question_id="num_001",
                selected_answer="Commutative property",
            ),
            DiagnosticAnswer(
                question_id="alg_001",
                selected_answer="3 and 4",
            ),
            DiagnosticAnswer(
                question_id="trig_001",
                selected_answer=None,
            ),
        ]
    )

    results = evaluate_diagnostic(submission)

    assert len(results) == 3

    assert results[0].is_correct is False
    assert results[0].error_type == "concept_error"

    assert results[1].is_correct is True
    assert results[1].error_type == "correct"

    assert results[2].is_correct is False
    assert results[2].error_type == "unanswered"


def test_unknown_question_id_raises_error():
    submission = DiagnosticSubmission(
        answers=[
            DiagnosticAnswer(
                question_id="does_not_exist",
                selected_answer="A",
            )
        ]
    )

    with pytest.raises(ValueError, match="Unknown question_id"):
        evaluate_diagnostic(submission)