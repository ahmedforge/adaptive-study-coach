# Adaptive AI Study Coach

A FAST-NUCES math exam practice app by Ahmed, built as an AI Bootcamp capstone. Start with a 12-question diagnostic, practice the topics you missed, or take a timed mock exam. The bundled bank has 98 questions across 12 topics. The default app runs locally after installation, including grading, explanations, exam revision, accounts, and saved progress.

## Run on Windows

From the repository folder in a VS Code PowerShell terminal with Python 3.12 installed, run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-core.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [Study Coach](http://127.0.0.1:8000/). Keep the terminal open while studying. Use Ctrl+C to stop. For later sessions, run the last command from the same folder. On macOS or Linux, create the environment with `python3.12 -m venv .venv` and use `.venv/bin/python` for the install and server commands.

| Page | What you can do |
| --- | --- |
| `/` | Review diagnostic results and work through weak topics with explanations and saved answer history. |
| `/exam` | Take a timed mock exam, review its report and turn missed questions into a revision plan. |
| `/dashboard` | Resume practice or exams and compare results by topic. |
| `/account` | Create an account, sign in, or claim earlier sessions from this browser. |
| `/docs` | Explore the FastAPI endpoints. |

New learners can start anonymously. Keep browser storage enabled for anonymous resume links. For a shared server, sign in on each device to reopen owned sessions. Native local progress lives in `progress_data/progress.sqlite3`. Keep this file across upgrades. To back it up locally, stop the app first and copy the progress directory.

## Run with Docker

```sh
docker compose up --build --wait
docker compose logs coach
```

Open the same local URL. `docker compose down` stops the service and preserves the named progress volume. The container stores SQLite at `/data/progress.sqlite3`. For an existing installation, back up the previous database before moving it to this volume with ownership writable by the container user. Local HTTP account changes require a loopback connection on both ends. Where Docker networking presents a bridge address, use the native quickstart for accounts or configure HTTPS at a trusted reverse proxy.

## Optional AI features

The default practice picker selects an unseen question from the exact weak topic, then rotates to the least recently used question when that pool is exhausted. Install `requirements.txt` in the same environment for MiniLM semantic retrieval, Gemini generation and MLflow retrieval tracking.

- Set `STUDY_COACH_PRACTICE_RETRIEVAL=semantic` to use the MiniLM/FAISS picker during practice. The first semantic search needs the model cached locally or network access to download it. The explicit `/retrieval/search` endpoint also uses this index.
- Set `GEMINI_API_KEY` in the environment or a local `.env` to request question variants. Set `GEMINI_MODEL` to choose a model enabled for your account. A missing key or failed generation uses the bank question with its worked solution.
- Use `MLFLOW_TRACKING_URI` to configure tracking for semantic searches. New practice sessions default to two consecutive correct answers per topic. Set `STUDY_COACH_TARGET_CORRECT` to an integer from 1 to 5 to change that target.

## Verify the installation

```sh
python -m pip install -r requirements-test.txt
python -m tools.question_bank validate
python -m tools.question_bank coverage
python -m pytest -q
node --test tests/session-library.test.cjs
```

Use the virtual environment's Python. The real semantic ranking test runs when `sentence-transformers` is installed and requires the MiniLM model. The remaining tests exercise practice, account ownership, saved exams, bank imports, generation fallback and retrieval error handling locally.

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
choose **Resume saved practice** to continue the same question. **Start new diagnostic** keeps the previous session available until the new diagnostic saves. Correctness is calculated on the server from the saved question. Current
answer keys are excluded from the session API response until an answer is saved.

- Default database: `progress_data/progress.sqlite3` (ignored by Git). Override
  with `STUDY_COACH_DB=/absolute/path/progress.sqlite3`.
- The browser keeps one opaque resume token in localStorage. Only a SHA-256 hash
  of that token is stored in the database. Possessing the token grants access to
  anonymous session. Account-owned sessions additionally require the signed-in owner.
- Keep the database file across restarts. Container deployments need a mounted
  persistent directory and the matching `STUDY_COACH_DB` path; otherwise container
  replacement loses saved progress. Compose mounts this directory automatically.
- A stale answer from another tab is rejected. Retrying the most recent identical
  answer after a lost response returns the saved result without counting it twice.
- If preparing the next question or saving fails, the previous saved state remains
  available. Generation takes place outside the short database update.
- Anonymous progress is tied to this server database and browser token. Accounts
  can resume owned progress across devices; password recovery and an automatic
  retention policy are not implemented. Clearing
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

Both practice modes select seeds from the learner's exact current topic. Semantic mode ranks candidates by embedding similarity. Diagnostic question IDs and saved practice seed IDs are treated as
seen: unseen seeds come first. After all seeds in that topic have been seen, the
least recently used one is selected, rather than repeating the top search result
forever. The current bank has 98 questions across 12 topics: nine each in limits and quadratic equations, and eight in each other topic.

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


### Practice history and mistake review

Expand **Practice history** to review all saved practice answers, newest first.
Filter by topic or select **Show incorrect answers only** to focus on mistakes.
Expand an answer to see the original question, your response, the correct answer,
and its explanation. Results appear ten at a time; **Show more answers** reveals
older matches. Filtering and reviewing do not submit answers or change progress.
The history belongs to the current saved session and remains available on resume.
Filters reset when the session view is rendered again. History is still loaded
with the session response; this is browser pagination, not server pagination.


## Timed mock exams

Open `/exam` (linked from the study screen) to take a bank-based mock exam:

- Choose 12 or 24 questions and a 15, 30, 45, or 60 minute limit in the UI.
  The API accepts integer durations from 5 to 120 minutes.
- Topic pools are shuffled and sampled in rounds, giving one or two questions
  from each of the current 12 topics, without duplicate question IDs.
- Select an option to save it immediately. Navigate by question number or with
  Previous/Next, change answers, or clear them. Green navigation buttons indicate
  saved answers. A failed save shows an error; resume to confirm uncertain saves.
- The browser stores an opaque exam token separately from the practice token.
  Reload and select **Resume saved exam** to continue the same paper, answers,
  and deadline. Starting another exam replaces that browser's exam resume link.
- **Review and submit** shows the number of unanswered questions before the final
  **Finish exam now** action. Every correct answer earns one mark; other answers
  earn zero. There is no negative marking.
- Submission reveals a saved score, per-topic correct/incorrect/unanswered counts,
  and expandable solutions for every question. Submitted answers are immutable.

### Exam API and deadline behavior

`POST /exams` creates an exam with `question_count` (12 or 24) and
`duration_minutes`. Other endpoints require `Authorization: Bearer <exam_token>`:

- `GET /exams/current` resumes the saved paper or completed report.
- `PUT /exams/current/answers` accepts `question_id`, `selected_answer` (an option
  or null to clear), and the current integer `version` returned by the server.
- `POST /exams/current/submit` completes and grades the saved answers.

The server snapshots questions and answer keys at creation. Active responses
exclude correct answers, explanations, and scores. Changing the bank later cannot
change an existing paper or its marking. Each draft save uses an optimistic version
check: a stale edit returns 409, while an identical retry returns the saved state.
Exam tokens and practice tokens cannot be interchanged.

The server owns the deadline. Reads, answer saves, and submissions finalize an
expired exam before accepting changes. No background worker is required: if the
browser or server closes, the next request finalizes the saved answers against
the original deadline. Expiry cannot be extended by reloading or changing the
browser clock. The displayed countdown is advisory; late answer requests are
rejected even if a browser timer was paused. Only answers confirmed in server
storage count. The browser checks expiry automatically while the page is open.

Exams share `STUDY_COACH_DB` and its persistence requirements with practice. They
use the curated bank, without AI question generation. Questions may recur across
separate exams. Scores describe a small question sample, not standardized exam
readiness or mastery. As with practice, tokens grant access to local demo data;
account-owned exams additionally require the signed-in owner. Account sign-in
is rate limited, but password recovery, automatic data retention, and broad
public-service abuse controls are not implemented.


### Turn an exam into targeted revision

A completed exam with incorrect or unanswered questions offers **Start or resume
targeted revision**. The server creates a practice plan from the exam's saved
question snapshot and answers, prioritizing topics by missed-question count. It
includes unanswered questions and excludes topics answered entirely correctly.
The existing practice target, saved streaks, seed rotation, answer review, and
history filters work with this plan. Exam seed IDs are passed into practice
selection so unseen seeds are preferred where available.

`POST /exams/current/revision` requires the exam Bearer token. It rejects active
exams (409) and perfect papers (422). An expired exam is finalized first. Repeated
requests return the same revision session and retain any practice progress;
concurrent creation cannot overwrite an existing plan. Tokens are derived with
a domain-separated HMAC from the exam's random secret token, and only token
hashes are stored in SQLite. The exam score and report remain unchanged.

The browser saves the practice token separately from the exam token and opens
`/?resume=1` to resume practice directly. Starting revision replaces the browser's
current practice resume link; it does not delete that earlier session. Storage
must be enabled for this handoff between pages. If storage is blocked, signed-in learners can open the saved plan from the dashboard. Anonymous learners can enable storage and retry the same action. The practice screen
labels the assessment **Mock exam** rather than **Diagnostic**. Older practice
sessions without source metadata retain their diagnostic label.

## Expanding the question bank

The source bank is `app/data/questions.json`. It currently contains 98 questions
across 12 topics. The existing labels are 12 easy, 86 medium, and zero hard; these
are author-provided labels, not calibrated difficulty estimates. Start by filling
skill gaps and adding reviewed questions at varied difficulty within the existing
12 topics. Grow in batches of 5–10 so every answer and explanation can be checked.

### Prepare a reviewed JSON batch

Copy `examples/question_batch.json` to `my_questions.json` and replace the sample
records with your own reviewed questions. Each record needs:

| Field | Format |
| --- | --- |
| `id` | Unique stable lowercase identifier, e.g. `limits_009`; never reuse an existing ID |
| `topic` | Existing topic slug shown in the coverage report |
| `subtopic` | Lowercase skill slug, e.g. `factorization` |
| `difficulty` | `easy`, `medium`, or `hard` |
| `question` | Complete, unambiguous question text |
| `options` | Exactly four distinct non-empty strings |
| `correct_answer` | Exact text of one option |
| `explanation` | Worked solution, including relevant assumptions or restrictions |
| `source` | Provenance, e.g. an original question or a specific document/page reference |

Use original questions or material you have permission to include. Solve each
question independently, check that exactly one option is correct, and review the
distractors and explanation before importing. AI-generated drafts need the same
review; schema checks do not validate mathematics or difficulty. The two supplied
examples have been reviewed and included in the bank. Use their structure for
new questions; replace their IDs and content rather than importing them again.

### Inspect, preview, then import

Run from the repository with its virtual environment activated:

```bash
python -m tools.question_bank validate
python -m tools.question_bank coverage
python -m tools.question_bank import --input my_questions.json
python -m tools.question_bank import --input my_questions.json --write
```

Import defaults to a dry run. `--write` validates the combined bank, rejects
colliding IDs or normalized duplicate question text, then appends records while
preserving the existing order. This matters because the diagnostic uses the first
12 records. An exact original backup is saved under `app/data/bank_backups/`
(ignored by Git); the replacement is staged and written atomically, preserving
file permissions. Review the resulting `git diff` and commit the updated bank.
Rerunning the same batch fails with a duplicate error rather than adding copies.
Use `--bank PATH` before the subcommand to work with a different bank.

**Restart the app after importing** so the in-memory embedding/FAISS indexes pick
up the added questions. Existing mock exams keep their original snapshots. Run
`python -m pytest -q` after changes; bank validation also runs whenever the
application loads questions. Exact-prompt duplicate checks cannot detect every
paraphrased duplicate, ambiguous answer, or mathematical error.

Imports accept existing topics. Adding a new subject or topic requires a separate
change to diagnostic selection, exam size/topic coverage, and tests; adding an
unrecognized topic silently would change the current 12-topic exam design. Avoid
editing the bank concurrently with an import; the write checks for intervening
changes, but this command is intended for one local editor at a time.

## Progress dashboard and saved-session library

Open `/dashboard` from the study or exam screen to review sessions retained by
this browser. The dashboard shows practice answer counts, completed exam scores,
separate practice/exam results by topic, and up to five topics with the most missed
or unanswered questions across completed exams. Different papers and repeated
practice attempts are not comparable mastery measurements.

Session cards show their status and saved timestamps, filter by practice/exam,
and open ten at a time. Opening a card sets the corresponding browser resume
link and resumes that exact session. Expired but ungraded exams are labelled
**Time elapsed**; open their report to finalize saved answers. Merely viewing the
dashboard does not finalize exams or change any practice progress.

A shared browser library remembers up to 50 practice/exam token references,
including new sessions, exam revision plans, and resumed sessions. Current resume
tokens are migrated automatically when loading a page. Earlier overwritten tokens
from before this feature cannot be recovered. Clearing browser storage loses these
links; changing servers/databases can make them unavailable. Database records are
not deleted when a link ages out of the browser library. Storage access must be
enabled for anonymous retention and resume navigation. Signed-in accounts use
a server-side session library and can resume progress across devices.

`POST /progress/summary` accepts `sessions`, an array of up to 50 objects with
`kind` (`practice` or `exam`) and `token`. It looks up only those bearer capabilities
and deduplicates repeated references. Successful summary responses use input indices to identify cards and omit
tokens, questions, answer keys, and active-exam scores. There is no endpoint to enumerate the database's sessions. Per-topic exam
aggregates include completed papers only; practice aggregates include saved
practice attempts only, without counting diagnostics as practice.

GitHub checks cover both dashboard scripts and run the browser-library unit tests
with `node --test tests/session-library.test.cjs`. Python tests cover access
isolation, aggregate counts, legacy records, read-only expiry handling, and storage
failure responses. Browser testing covers the complete dashboard/resume flow.

## Accounts and cross-device progress

Open `/account` to create a username/password account or sign in. Accounts use
usernames (3–32 lowercase letters/digits/underscores, starting with a letter) and
passwords of 12–128 characters. No email is collected. **There is no password-reset
or username-recovery flow**: choose and retain credentials before using an account
for progress you want to keep.

### Learner flow

1. Create an account or sign in. New practice sessions, exams, and revision plans
   are automatically associated with that account.
2. To retain earlier anonymous sessions, use **Import this browser’s progress** on
   the account page. This is explicit because a shared browser may hold another
   person's anonymous links. Sessions already owned by another account cannot be
   imported. Claiming an exam also claims its linked revision plan when available.
3. On another device/browser, open this same server, sign in, and open the
   dashboard. Its account library provides **Open saved practice**, **Continue
   exam**, and **Open exam report** without needing old browser tokens.
4. Account history is paginated in groups of up to 50 sessions, with older/newer
   controls. Dashboard totals and topic aggregates describe the current page.
5. Sign out of this browser or all browsers from the account page. Password changes
   require the current password, revoke other sessions, and keep this browser
   signed in. A failed database transaction rolls back the credential change.

Accounts live in `STUDY_COACH_DB` alongside progress. Retain this database when
restarting/redeploying; signing in against a different database does not recover
accounts from the original server. This is server-backed progress, not a separate
cloud synchronization provider. If browser storage is blocked while login cookies are available, the dashboard can still reopen owned sessions using their account IDs.

### Ownership and token compatibility

The original opaque practice/exam tokens still work for anonymous sessions. Once
a session belongs to an account, possessing a token is insufficient: the owner
must also have a valid login cookie. This includes previously issued anonymous
links and account-issued aliases. Another account receives an unavailable/not-found
response, including when a session ID is known.

The account library lists stable session IDs, not bearer tokens. Opening an owned
session issues a fresh hashed alias pointing to the same canonical database row.
Two devices therefore share optimistic versions, answer history, and the same exam
deadline. Stale edits are rejected rather than overwriting newer work. Exam-to-
revision links are canonical too: reopening an exam through a different alias
resumes the same revision plan. Existing HMAC-derived revision links are adopted
without resetting progress.

Schema changes are additive. Before upgrading a non-empty pre-account database,
the app creates a SQLite snapshot in `account_migration_backups/` beside the DB,
with file mode 0600 on POSIX. On Windows, protect the containing directory with your user account permissions. Backup directories are ignored by Git. Existing anonymous
records are not assigned to an account until explicitly claimed. Use the updated
server consistently after claiming sessions; older server versions do not enforce
account ownership.

### Authentication and deployment

- Passwords are hashed with Argon2id (19 MiB memory, two iterations, one lane) and
  per-password random salts via `argon2-cffi`; raw passwords are never persisted.
- Login sessions use random tokens stored only as SHA-256 hashes. Cookies are
  HttpOnly, host-only, SameSite=Lax, and expire after seven days. Sign-in rotates
  the current browser's login token. Expired/revoked logins cannot silently save
  new anonymous progress while their stale cookie remains present.
- Cookies are Secure when requests use HTTPS. `STUDY_COACH_COOKIE_SECURE=true`
  forces Secure cookies. Public account mutations require HTTPS; HTTP is accepted
  only for loopback-host/loopback-peer development. Behind a reverse proxy,
  configure HTTPS forwarding correctly and trust only your own proxy.
- Browser mutations send `X-Study-Coach: 1`; signed-in mutations and all account
  mutations require it, and reject mismatched Origin headers. The app does not
  enable cross-origin credential sharing.
- Login attempts are reserved atomically before password verification: at most
  ten attempts per username/client in a 15-minute window, with an additional
  100-attempt client cap. Registration and password changes have separate buckets.
  These limits include successful attempts. The SQLite rate limiter is shared
  across this deployment's processes, not a distributed service.
- Invalid credential responses do not distinguish an unknown username from a wrong
  password. Account validation responses omit input values. Authentication payloads
  and account library responses are marked not to be cached where applicable.

This implements core account and ownership behavior; it has no email verification,
MFA, administrative recovery, or automated retention/deletion flow. A public
release still needs deployment verification and operational monitoring. The
password/session choices follow the [OWASP password-storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
and the [Argon2 library API](https://argon2-cffi.readthedocs.io/en/stable/howto.html).

### Account API

- `POST /account/register`, `POST /account/login`: JSON `username`, `password`;
  successful responses set the login cookie.
- `GET /account/me`: current sign-in state; `GET /account/library?limit=50&offset=0`:
  references to the signed-in owner's sessions.
- `POST /account/open`: JSON `id`; returns a short response with a resume token
  and session kind for an owned session.
- `POST /account/claim`: JSON `sessions` containing up to 50 `kind`/`token` pairs.
- `POST /account/password`: `current_password`, `new_password`.
- `POST /account/logout`, `POST /account/logout-all`: revoke the current/all logins.

Use same-origin requests, the cookie, and `X-Study-Coach: 1` for mutations. The
existing practice/exam APIs keep their Bearer resume token contract; account-owned
records additionally require the owner's cookie. `/progress/summary` accepts either
`token` references or owned `id` references, never both on one reference. Anonymous
summaries remain limited to supplied bearer capabilities.

Local automated checks cover multi-device editing, cross-account access rejection,
CSRF and HTTPS checks, rate limiting, expiry, login rotation, logout revocation,
password-change rollback, legacy migration, and shared exam revision plans.
