# Adaptive AI Study Coach

Adaptive AI Study Coach is a Math-focused exam preparation system that identifies a student's weak topics through a diagnostic test and then generates targeted practice questions using retrieval-augmented generation.

The MVP is designed for FAST-NUCES entry / transfer test preparation and focuses on adaptive practice rather than static question sets.

---

## Problem

Traditional practice books and question banks usually give every student the same questions.

They do not adapt based on:

- weak topics
- repeated mistakes
- individual learning needs

The goal of this project is to create an AI-powered study loop that diagnoses weaknesses and generates targeted practice.

---

## Solution

The system:

1. Gives the student a 12-question Math diagnostic.
2. Grades responses automatically.
3. Detects weak topics.
4. Selects the highest-priority weak topic.
5. Retrieves a semantically relevant seed question using FAISS.
6. Uses Gemini to generate a fresh question variant.
7. Grades the student's practice response.
8. In saved sessions, practices each topic until the consecutive-correct target is reached (two by default). Wrong answers reset the streak.

---

## Technical Flow

```text
Student
   |
   v
12-Question Diagnostic
   |
   v
Deterministic Grading
   |
   v
Weak Topic Detection
   |
   v
Agent State Machine
   |
   v
Weak-Topic Query
   |
   v
SentenceTransformer Embedding
(all-MiniLM-L6-v2)
   |
   v
FAISS Vector Search
   |
   v
Relevant Seed MCQ
   |
   v
Gemini Variant Generation
   |
   v
Student Answers Practice Question
   |
   v
Auto-Grading
   |
   +----------------------+
   |                      |
Incorrect              Correct
   |                      |
Repeat Topic        Check Streak Target
   |                      |
   +------- Agent Loop ----+
```

---

## RAG Pipeline

After a correct answer, saved sessions repeat the topic until the streak target
is reached, then advance to the next weak topic.

The retrieval-augmented generation pipeline has three main stages.

### 1. Retrieval

Each seed question is represented using its topic, subtopic, and question text.

The text is converted into a semantic embedding using:

```text
all-MiniLM-L6-v2
```

The embeddings are normalized and stored in a FAISS index.

When the agent identifies a weak topic, that topic is also embedded and compared with the stored vectors.

FAISS returns the most semantically relevant seed question.

### 2. Augmentation

The retrieved seed MCQ is inserted into the Gemini prompt as grounding context.

### 3. Generation

Gemini generates a new MCQ that keeps the same topic, skill, and approximate difficulty while changing the wording or values.

This avoids simply copying the original seed question.

---

## Agent Logic

The adaptive workflow is controlled by a deterministic state machine.

The agent state tracks:

- diagnostic results
- weak topics
- current topic
- attempts on the current topic
- workflow status

The LLM does not control progression.

Instead:

```text
Wrong answer   -> stay on current topic
Correct answer -> move to next weak topic
No weak topics -> complete
```

This makes the learning flow predictable and easier to test.

---

## Automatic Grading

MCQ grading is deterministic rather than LLM-based.

Responses are classified as:

- `correct`
- `concept_error`
- `unanswered`

Rule-based grading is used because it is cheaper, faster, and more reliable for multiple-choice questions.

---

## Question Bank

The MVP contains approximately:

- 96 Math MCQs
- 12 diagnostic topics
- multiple seed questions per topic

The questions are newly written/adapted based on the concepts, topic structure, and general entry-test style of KIPS preparation material.

They are not a verbatim digitization of the source material.

---

## MLflow Tracking

MLflow is used to track retrieval experiments.

For retrieval runs, the system logs:

- query
- `top_k`
- top similarity score

Run the MLflow interface with:

```bash
mlflow ui
```

Then open:

```text
http://127.0.0.1:5000
```

---

## Tech Stack

### Backend

- Python
- FastAPI
- Pydantic

### AI / Retrieval

- SentenceTransformers
- `all-MiniLM-L6-v2`
- FAISS
- Gemini API

### Experiment Tracking

- MLflow

### Frontend

- HTML
- CSS
- JavaScript

### Testing

- Pytest

### Deployment / Packaging

- Docker

### Version Control

- Git
- GitHub
- Feature branches
- Pull requests
- Meaningful commit messages

---

## Project Structure

```text
adaptive-study-coach/
├── app/
│   ├── data/
│   │   └── questions.json
│   ├── models/
│   ├── repositories/
│   ├── routers/
│   ├── services/
│   ├── static/
│   │   └── index.html
│   └── main.py
├── tests/
├── Dockerfile
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Running Locally

### 1. Clone the repository

```bash
git clone https://github.com/ahmedforge/adaptive-study-coach.git
cd adaptive-study-coach
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

On Windows:

```bash
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Gemini

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key
```

Do not commit the `.env` file.

### 5. Start the application

```bash
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/
```

FastAPI documentation:

```text
http://127.0.0.1:8000/docs
```

---

## Running Tests

```bash
python -m pytest -q
```

Local result (October 30, 2026; no live Gemini calls):

```text
75 passed
```

---

## Docker

Build the image:

```bash
docker build -t adaptive-study-coach .
```

Run the container:

```bash
docker run --env-file .env -p 8000:8000 adaptive-study-coach
```

Then open:

```text
http://127.0.0.1:8000/
```

---

## Current Results

- 96+ Math MCQs
- 12-question diagnostic
- 12 Math topic areas
- Semantic retrieval using FAISS
- Gemini-generated practice variants
- Adaptive state-machine loop
- MLflow retrieval tracking
- 75 automated tests passing
- Dockerized application

---

## Limitations

This is a bootcamp MVP and currently has several limitations:

- Math only
- relatively small local seed bank
- minimal frontend
- generated-question quality depends on the Gemini model
- embedding model may download on first use
- no student authentication
- no persistent learning history
- richer error classification is not yet implemented

---

## Future Work

Future improvements could include:

- more subjects
- larger curated question banks
- automatic difficulty adaptation
- student accounts
- persistent progress tracking
- analytics dashboard
- richer misconception classification
- generation-quality evaluation
- persistent vector database
- improved session management

---

## Key Design Decision

The central design principle is:

> Use AI for semantic retrieval and content generation, but use deterministic code for grading and learning-flow decisions.

This keeps the system adaptive while maintaining predictable behavior.

---

## Capstone Outcome

The final MVP demonstrates an end-to-end adaptive learning pipeline:

```text
Diagnose weakness
      ->
Retrieve relevant content
      ->
Generate targeted practice
      ->
Grade response
      ->
Adapt the learning path
```

---

## Author

Ahmed  
AI Bootcamp Capstone Project
## Validated generation and fallback

Practice variants require a non-empty question and explanation, exactly four
distinct non-empty string options, and an answer key matching an option. Fields
are trimmed, lengths are bounded, unexpected fields are rejected, and a copied
seed prompt is rejected. One outer JSON code fence is accepted.

If the API key is missing, the provider fails, or its response is invalid, practice
uses the retrieved seed question and its existing answer/explanation. The response
marks `generation_source` as `generated` or `seed_fallback`; the practice screen
shows which is being used. The provider request has a 20-second timeout and SDK
retries are disabled. Generated text is rendered as text rather than HTML.

These checks validate structure, not mathematical correctness, semantic option
equivalence, topic alignment, or difficulty. The question bank is not claimed to
be independently audited. No live provider accuracy result is implied by tests.

## Saved local progress

The practice screen now saves a diagnostic, the current question, remaining weak
topics, attempts, answer feedback, and practice history in SQLite. On reload,
choose **Resume saved practice** to continue the same question. **Start new
diagnostic** forgets this browser's resume token; it does not delete the old server
record. Correctness is calculated on the server from the saved question. Current
answer keys are excluded from the session API response until an answer is saved.

- Default database: `progress_data/progress.sqlite3` (ignored by Git). Override
  with `STUDY_COACH_DB=/absolute/path/progress.sqlite3`.
- The browser keeps one opaque resume token in localStorage. Only a SHA-256 hash
  of that token is stored in the database. Possessing the token grants access to
  that session; this is a local demo, not an authenticated multi-user service.
- Keep the database file across restarts. Container deployments need a mounted
  persistent directory and the matching `STUDY_COACH_DB` path; otherwise container
  replacement loses saved progress. No deployment or Docker changes are included.
- A stale answer from another tab is rejected. Retrying the most recent identical
  answer after a lost response returns the saved result without counting it twice.
- If preparing the next question or saving fails, the previous saved state remains
  available. Generation takes place outside the short database update.
- Progress is tied to this server database and browser token. There is no account
  recovery, cross-device sync, expiry, or automatic retention policy. Clearing
  browser storage loses the resume token. If storage is blocked, the interface
  explains that access lasts only while the tab retains its token.
- New saved sessions require two consecutive correct answers per topic. Set
  `STUDY_COACH_TARGET_CORRECT` to an integer from 1 to 5 to change the target for
  new sessions. Each session retains its target across restarts and configuration
  changes. Wrong answers reset the current streak; moving to another topic starts
  a fresh streak. The screen shows current progress.
- Older saved sessions without target metadata and the legacy stateless agent API
  retain their one-correct-answer default. Completing a practice cycle is not
  evidence of long-term mastery or improved exam scores.

The new UI uses `POST /sessions`, `GET /sessions/current`, and
`POST /sessions/current/answers`. Resume and answer calls use a Bearer token;
`question_id` binds each answer to its saved question. Legacy `/agent` endpoints
remain stateless for compatibility and are not used for saved practice.

Local validation on October 30, 2026: **60 tests passed**, including restart
recovery, access isolation, server-side grading, response-loss retries, stale
updates, invalid diagnostics, and failed saves. No live Gemini calls were used.

## Topic-safe, varied practice seeds

Practice retrieval ranks the bank but selects seeds only from the learner's exact
current topic. Diagnostic question IDs and saved practice seed IDs are treated as
seen: unseen seeds come first. After all seeds in that topic have been seen, the
least recently used one is selected, rather than repeating the top search result
forever. The current bank has 96 questions across 12 topics, eight per topic.

Each generated or fallback practice question records its `seed_question_id` on
the server. Saved attempts retain that provenance, so selection continues to
rotate after reload. Existing sessions without seed metadata remain readable;
only their newly recorded attempts contribute seed history. Unknown topics
produce no seed rather than silently selecting another topic's question.

The seed's topic is enforced; generated question topic/skill accuracy and
mathematical correctness still require separate evaluation. This change is not
spaced repetition, difficulty adaptation, or a mastery estimate. MLflow tracking
is best effort: a tracking outage does not block a valid retrieval. The general
search API validates query length and requires `top_k` between 1 and 20.

Local selection verification (October 30, 2026): **75 tests passed** with cached embeddings and no live Gemini calls.


### Diagnostic results review

Saved sessions include a diagnostic summary with correct, incorrect, and unanswered
counts overall and per topic. Expand the diagnostic results in the progress panel
to review the evidence behind the practice plan. Unanswered questions are shown
separately from wrong answers; both contribute to the existing practice order.
This summary is computed from the saved diagnostic, so it remains available after
resume and does not change as practice answers accumulate. It also works for older
saved sessions without adding stored fields. A small diagnostic sample does not
establish mastery or identify the cause of an incorrect answer.


### Review before continuing

After a practice answer is saved, the browser shows the result and explanation
before revealing the next question. Select **Continue practice** when ready.
Resuming a session with practice history returns to this review step. The next
question is already prepared and saved by the server; continuing reveals it
without submitting another answer or changing progress. Keyboard focus moves to
the feedback after submission and to the question when continuing. Final answers
still show feedback when the practice cycle is complete.
