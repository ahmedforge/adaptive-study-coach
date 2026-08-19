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
8. Repeats the same topic after a wrong answer or advances after a correct answer.

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
Repeat Topic        Next Weak Topic
   |                      |
   +------- Agent Loop ----+
```

---

## RAG Pipeline

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

Current result:

```text
14 passed
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
- 14 / 14 automated tests passing
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