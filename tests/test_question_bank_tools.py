import json
from pathlib import Path

import pytest

from app.services.question_bank_service import coverage, import_batch, read_bank, validate_bank
from tools.question_bank import main


def sample(id='q_001', text='What is 2 + 3?'):
    return {'id': id, 'topic': 'number_systems', 'subtopic': 'addition', 'difficulty': 'easy',
        'question': text, 'options': ['3', '4', '5', '6'], 'correct_answer': '5',
        'explanation': 'Two plus three is five.', 'source': 'original test question'}


def write(path, questions):
    path.write_text(json.dumps(questions), encoding='utf-8')
    return path


@pytest.mark.parametrize('change', [
    {'options': ['a', 'b', 'c']}, {'options': ['a', 'a', 'c', 'd']},
    {'options': ['', '4', '5', '6']}, {'correct_answer': '7'}, {'explanation': ''},
    {'source': ''}, {'difficulty': 'expert'}, {'topic': 'Number Systems'},
    {'id': 'invalid id'}, {'question': 23}, {'unexpected': True},
])
def test_reject_invalid_question_contract(change):
    with pytest.raises(ValueError, match='Question 1:'):
        validate_bank([sample() | change])


@pytest.mark.parametrize('raw', [[], {}, None, 'question'])
def test_reject_invalid_bank_shape(raw):
    with pytest.raises(ValueError, match='non-empty JSON array'):
        validate_bank(raw)


def test_reject_duplicate_ids_and_normalized_prompts():
    with pytest.raises(ValueError, match='Duplicate question ID'):
        validate_bank([sample(), sample(text='A different question?')])
    with pytest.raises(ValueError, match='Duplicate question text'):
        validate_bank([sample(), sample('q_002', '  WHAT is 2 + 3?  ')])


def test_coverage_counts_difficulties_and_distinct_subtopics():
    qs = validate_bank([sample(), sample('q_002', 'Second?') | {'difficulty': 'hard'},
                        sample('q_003', 'Third?') | {'difficulty': 'medium', 'subtopic': 'division'}])
    assert coverage(qs) == {'number_systems': {
        'total': 3, 'easy': 1, 'medium': 1, 'hard': 1, 'subtopics': 2}}


def test_dry_run_does_not_change_files_or_create_backup(tmp_path):
    bank = write(tmp_path / 'bank.json', [sample()])
    batch = write(tmp_path / 'batch.json', [sample('q_002', 'What is 3 + 2?')])
    before = bank.read_bytes()
    result = import_batch(bank, batch)
    assert result['added'] == 1 and result['total'] == 2
    assert result['backup'] is None
    assert bank.read_bytes() == before
    assert not (tmp_path / 'bank_backups').exists()


def test_append_preserves_order_exact_backup_and_permissions(tmp_path):
    original = [sample(f'q_{i:03}', f'Question {i}?') for i in range(16)]
    bank = write(tmp_path / 'bank.json', original)
    bank.chmod(0o644)
    batch = write(tmp_path / 'batch.json', [sample('new_001', 'New question?')])
    before = bank.read_bytes()
    result = import_batch(bank, batch, write=True)
    merged = read_bank(bank)
    assert [q.id for q in merged[:16]] == [q['id'] for q in original]
    assert merged[-1].id == 'new_001'
    assert Path(result['backup']).read_bytes() == before
    assert bank.stat().st_mode & 0o777 == 0o644
    assert not list(tmp_path.glob('.bank-*.tmp'))


@pytest.mark.parametrize('new_question', [sample(), sample('q_002'),
    sample('q_002', 'New?') | {'topic': 'unknown_topic'}])
def test_invalid_import_never_changes_bank(tmp_path, new_question):
    bank = write(tmp_path / 'bank.json', [sample()])
    batch = write(tmp_path / 'batch.json', [new_question])
    before = bank.read_bytes()
    with pytest.raises(ValueError): import_batch(bank, batch, write=True)
    assert bank.read_bytes() == before
    assert not (tmp_path / 'bank_backups').exists()


def test_atomic_replace_failure_keeps_original_and_removes_temp(tmp_path, monkeypatch):
    import app.services.question_bank_service as service
    bank = write(tmp_path / 'bank.json', [sample()])
    batch = write(tmp_path / 'batch.json', [sample('q_002', 'New question?')])
    before = bank.read_bytes()
    def fail(*args): raise OSError('simulated disk error')
    monkeypatch.setattr(service.os, 'replace', fail)
    with pytest.raises(OSError): import_batch(bank, batch, write=True)
    assert bank.read_bytes() == before
    assert not list(tmp_path.glob('.bank-*.tmp'))
    assert next((tmp_path / 'bank_backups').glob('*.json')).read_bytes() == before


def test_cli_validate_coverage_dry_run_and_error_exit(tmp_path, capsys):
    bank = write(tmp_path / 'bank.json', [sample()])
    batch = write(tmp_path / 'batch.json', [sample('q_002', 'New question?')])
    assert main(['--bank', str(bank), 'coverage']) == 0
    assert 'number_systems' in capsys.readouterr().out
    assert main(['--bank', str(bank), 'validate']) == 0
    assert 'Valid bank: 1' in capsys.readouterr().out
    assert main(['--bank', str(bank), 'import', '--input', str(batch)]) == 0
    assert 'No files changed' in capsys.readouterr().out
    assert len(read_bank(bank)) == 1
    assert main(['--bank', str(bank), 'import', '--input', str(batch), '--write']) == 0
    assert len(read_bank(bank)) == 2
    capsys.readouterr()
    assert main(['--bank', str(bank), 'import', '--input', str(batch), '--write']) == 1
    assert 'Duplicate' in capsys.readouterr().err


def test_invalid_json_has_line_number_and_no_traceback(tmp_path, capsys):
    bank = tmp_path / 'bank.json'
    bank.write_text('[{')
    assert main(['--bank', str(bank), 'validate']) == 1
    error = capsys.readouterr().err
    assert 'Invalid JSON at line' in error and 'Traceback' not in error


def test_repository_rejects_invalid_bank_and_allows_more_than_150_questions(tmp_path, monkeypatch):
    from app.repositories import question_repository
    bank = write(tmp_path / 'bank.json', [sample(f'q_{i:03}', f'Question {i}?') for i in range(151)])
    monkeypatch.setattr(question_repository, 'DATA_PATH', bank)
    assert len(question_repository.load_questions()) == 151
    write(bank, [sample() | {'correct_answer': 'invalid'}])
    with pytest.raises(ValueError): question_repository.load_questions()
