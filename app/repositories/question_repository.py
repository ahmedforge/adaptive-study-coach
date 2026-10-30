from app.models.question import Question
from app.services.question_bank_service import DEFAULT_BANK, read_bank

DATA_PATH = DEFAULT_BANK


def load_questions() -> list[Question]:
    return read_bank(DATA_PATH)
