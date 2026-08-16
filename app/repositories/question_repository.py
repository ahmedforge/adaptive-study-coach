import json
from pathlib import Path

from app.models.question import Question


DATA_PATH = Path("app/data/questions.json")


def load_questions() -> list[Question]:
    with DATA_PATH.open("r", encoding="utf-8") as file:
        raw_questions = json.load(file)

    return [Question(**item) for item in raw_questions]