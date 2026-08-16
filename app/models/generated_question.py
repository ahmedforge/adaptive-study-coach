from pydantic import BaseModel, model_validator


class GeneratedQuestion(BaseModel):
    question: str
    options: list[str]
    correct_answer: str
    explanation: str

    @model_validator(mode="after")
    def validate_mcq(self):
        if len(self.options) != 4:
            raise ValueError("Generated question must have exactly 4 options")

        if self.correct_answer not in self.options:
            raise ValueError("Correct answer must match one of the options")

        return self