"""Bank integrity and coverage checks; these do not prove mathematical correctness."""
from collections import Counter
import json
import os
from pathlib import Path
import stat
import tempfile
import unicodedata
from uuid import uuid4

from pydantic import ValidationError

from app.models.question import Question

DEFAULT_BANK = Path(__file__).resolve().parents[1] / 'data' / 'questions.json'


def prompt_key(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def validate_bank(raw):
    if not isinstance(raw, list) or not raw:
        raise ValueError('A bank or batch must be a non-empty JSON array of question objects.')
    questions = []
    ids, prompts = set(), {}
    for index, item in enumerate(raw, 1):
        try:
            question = Question.model_validate(item)
        except ValidationError as exc:
            issues = '; '.join(f"{'.'.join(str(part) for part in error['loc']) or 'question'}: {error['msg']}"
                               for error in exc.errors())
            raise ValueError(f'Question {index}: {issues}') from exc
        if question.id in ids:
            raise ValueError(f'Duplicate question ID: {question.id}')
        key = prompt_key(question.question)
        if key in prompts:
            raise ValueError(f'Duplicate question text: {question.id} repeats {prompts[key]}')
        ids.add(question.id)
        prompts[key] = question.id
        questions.append(question)
    return questions


def read_bank(path=DEFAULT_BANK):
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'Invalid JSON at line {exc.lineno}, column {exc.colno}.') from exc
    return validate_bank(raw)


def coverage(questions):
    topics = {}
    for q in questions:
        row = topics.setdefault(q.topic, {'total': 0, 'easy': 0, 'medium': 0, 'hard': 0, 'subtopics': set()})
        row['total'] += 1
        row[q.difficulty] += 1
        row['subtopics'].add(q.subtopic)
    return {topic: {**row, 'subtopics': len(row['subtopics'])} for topic, row in sorted(topics.items())}


def import_batch(bank_path, batch_path, *, write=False):
    bank_path, batch_path = Path(bank_path), Path(batch_path)
    original = bank_path.read_bytes()
    existing = read_bank(bank_path)
    incoming = read_bank(batch_path)
    known_topics = {q.topic for q in existing}
    unknown = sorted({q.topic for q in incoming} - known_topics)
    if unknown:
        raise ValueError('Unknown topics: ' + ', '.join(unknown) + '. Use existing topic slugs; adding subjects requires updating the diagnostic and exam design.')
    # Validate the combined bank, not just the batch, to catch cross-file duplicates.
    merged = validate_bank([q.model_dump() for q in existing + incoming])
    result = {'added': len(incoming), 'total': len(merged), 'coverage': coverage(merged), 'backup': None}
    if not write:
        return result
    if bank_path.read_bytes() != original:
        raise ValueError('The bank changed while validating. Retry against the latest file.')
    # Preserve the diagnostic order by appending; retain an exact-byte backup.
    backup_dir = bank_path.parent / 'bank_backups'
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / f'{bank_path.stem}-{uuid4().hex}.json'
    with backup.open('xb') as stream:
        stream.write(original)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=bank_path.parent,
                                         prefix='.bank-', suffix='.tmp', delete=False) as stream:
            staged = Path(stream.name)
            text = original.decode('utf-8')
            closing = text.rfind(']')
            additions = json.dumps([q.model_dump() for q in incoming], ensure_ascii=False, indent=2)[1:-1].strip('\n')
            stream.write(text[:closing].rstrip() + ',\n' + additions + '\n]' + text[closing + 1:])
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(staged, stat.S_IMODE(bank_path.stat().st_mode))
        if bank_path.read_bytes() != original:
            raise ValueError('The bank changed before writing. Retry against the latest file.')
        os.replace(staged, bank_path)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    result['backup'] = str(backup)
    return result
