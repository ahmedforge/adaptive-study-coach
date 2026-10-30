import json
import logging
import os
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.models.generated_question import GeneratedQuestion, PracticeQuestion
from app.models.question import Question


load_dotenv()
logger = logging.getLogger(__name__)
MAX_RESPONSE_CHARS = 12000


def _request_variant(prompt: str) -> str | None:
    # Initialize only when needed: a missing key must not prevent app startup.
    with genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(
            timeout=20000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    ) as client:
        return client.models.generate_content(
            model="gemini-3-flash-preview", contents=prompt,
        ).text


def _parse_variant(raw_text: str | None, seed: Question) -> GeneratedQuestion:
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ValueError("No question text returned")
    if len(raw_text) > MAX_RESPONSE_CHARS:
        raise ValueError("Question response is too large")
    text = raw_text.strip()
    # Accept one outer Markdown fence; never strip arbitrary content internally.
    fence = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    data = json.loads(text)
    question = GeneratedQuestion.model_validate(data)
    if " ".join(question.question.casefold().split()) == " ".join(seed.question.casefold().split()):
        raise ValueError("Generated question copies the seed")
    return question


def _fallback(seed: Question) -> PracticeQuestion:
    # Apply the same structural checks to the bank question; never invent an answer.
    return PracticeQuestion(
        question=seed.question, options=seed.options,
        correct_answer=seed.correct_answer, explanation=seed.explanation,
        generation_source="seed_fallback",
    )


def generate_variant(seed_question: Question) -> PracticeQuestion:
    fallback = _fallback(seed_question)
    if not os.getenv("GEMINI_API_KEY", "").strip():
        return fallback

    prompt = f"""
Create ONE new multiple-choice math question based on the seed question below.

Requirements:
- Keep the same topic, mathematical skill, and approximate difficulty.
- Change the numbers and wording; do not copy the seed question.
- Provide exactly four distinct, non-empty options.
- The correct_answer must exactly match one of the options.
- Include a non-empty explanation showing the solution steps.
- Return ONLY one JSON object with question, options, correct_answer, explanation.

Seed topic: {seed_question.topic}
Seed subtopic: {seed_question.subtopic}
Seed difficulty: {seed_question.difficulty}
Seed question: {seed_question.question}
Seed options: {seed_question.options}
"""
    try:
        raw_text = _request_variant(prompt)
    except Exception as exc:
        # External client failures should not break practice. Do not log prompts,
        # response bodies, credentials, or SDK exception messages.
        logger.warning("Question provider failed (%s); using seed fallback", type(exc).__name__)
        return fallback

    try:
        question = _parse_variant(raw_text, seed_question)
    except (ValueError, TypeError):
        logger.warning("Question provider returned an invalid variant; using seed fallback")
        return fallback
    return PracticeQuestion(**question.model_dump(), generation_source="generated")
