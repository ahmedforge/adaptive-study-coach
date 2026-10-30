from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_answer: str = Field(min_length=1, max_length=300)
    explanation: str = Field(min_length=1, max_length=4000)

    @field_validator("options")
    @classmethod
    def validate_options(cls, options):
        if any(not option or len(option) > 300 for option in options):
            raise ValueError("Options must contain 1 to 300 characters")
        if len({option.casefold() for option in options}) != 4:
            raise ValueError("Options must be distinct")
        return options

    @model_validator(mode="after")
    def validate_mcq(self):
        if self.correct_answer not in self.options:
            raise ValueError("Correct answer must match one of the options")
        return self


class PracticeQuestion(GeneratedQuestion):
    generation_source: Literal["generated", "seed_fallback"] = "generated"
