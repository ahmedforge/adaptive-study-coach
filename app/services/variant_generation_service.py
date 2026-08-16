import json
import os

from dotenv import load_dotenv
from google import genai

from app.models.generated_question import GeneratedQuestion
from app.models.question import Question


load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
)


def generate_variant(seed_question: Question) -> GeneratedQuestion:
    prompt = f"""
Create ONE new multiple-choice math question based on the seed question below.

Requirements:
- Keep the same topic and mathematical skill.
- Keep roughly the same difficulty.
- Change the numbers and wording.
- Provide exactly 4 options.
- The correct_answer must exactly match one of the options.
- Do not copy the seed question verbatim.
- Return ONLY valid JSON.

JSON format:
{{
  "question": "...",
  "options": ["...", "...", "...", "..."],
  "correct_answer": "...",
  "explanation": "..."
}}

Seed topic: {seed_question.topic}
Seed subtopic: {seed_question.subtopic}
Seed difficulty: {seed_question.difficulty}
Seed question: {seed_question.question}
Seed options: {seed_question.options}
"""

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
    )

    raw_text = response.text.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    data = json.loads(raw_text)

    return GeneratedQuestion(**data)