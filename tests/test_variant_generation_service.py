import json
from types import SimpleNamespace

import pytest

from app.models.question import Question
from app.repositories.question_repository import load_questions
from app.services import variant_generation_service as service


@pytest.fixture
def seed():
    return Question(id="seed", topic="arithmetic", subtopic="addition", difficulty="easy",
                    question="What is 2 + 2?", options=["2", "3", "4", "5"],
                    correct_answer="4", explanation="Adding two and two gives four.", source="test")


@pytest.fixture
def variant():
    return {"question": "What is 3 + 3?", "options": ["3", "5", "6", "9"],
            "correct_answer": "6", "explanation": "Adding three and three gives six."}


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-no-network")


def respond(monkeypatch, text):
    monkeypatch.setattr(service, "_request_variant", lambda prompt: text)


def test_valid_variant_preserves_answer_and_provenance(monkeypatch, seed, variant):
    respond(monkeypatch, json.dumps(variant))
    result = service.generate_variant(seed)
    assert result.question == variant['question']
    assert result.correct_answer == "6"
    assert result.generation_source == "generated"
    assert result.seed_question_id == seed.id


def test_outer_json_fence_is_accepted(monkeypatch, seed, variant):
    respond(monkeypatch, '```json\n' + json.dumps(variant) + '\n```')
    assert service.generate_variant(seed).generation_source == "generated"


@pytest.mark.parametrize('text', [None, '', '   ', 'not JSON', '[]', 'null', '{}', 'x' * 12001])
def test_unusable_response_falls_back(monkeypatch, seed, text):
    respond(monkeypatch, text)
    result = service.generate_variant(seed)
    assert result.generation_source == 'seed_fallback'
    assert result.seed_question_id == seed.id
    assert result.question == seed.question
    assert result.options == seed.options
    assert result.correct_answer == seed.correct_answer
    assert result.explanation == seed.explanation


@pytest.mark.parametrize('changes', [
    {'question': '  '}, {'explanation': ''}, {'options': ['1', '2', '3']},
    {'options': ['3', '5', '6', '6']}, {'options': ['3', '5', '6', '  ']},
    {'options': ['3', '5', '6', 9]}, {'correct_answer': '12'},
    {'generation_source': 'seed_fallback'}, {'question': 'WHAT IS 2 + 2?'},
])
def test_invalid_variant_uses_bank_instead(monkeypatch, seed, variant, changes):
    respond(monkeypatch, json.dumps({**variant, **changes}))
    assert service.generate_variant(seed).generation_source == 'seed_fallback'


def test_missing_key_never_calls_provider(monkeypatch, seed):
    monkeypatch.delenv('GEMINI_API_KEY')
    monkeypatch.setattr(service, '_request_variant', lambda prompt: pytest.fail('provider called'))
    assert service.generate_variant(seed).generation_source == 'seed_fallback'


def test_provider_failure_does_not_leak_details(monkeypatch, seed, caplog):
    def fail(prompt):
        raise RuntimeError('private-key-and-response-content')
    monkeypatch.setattr(service, '_request_variant', fail)
    assert service.generate_variant(seed).generation_source == 'seed_fallback'
    assert 'private-key-and-response-content' not in caplog.text


def test_existing_bank_can_supply_structurally_valid_fallbacks():
    for question in load_questions():
        result = service._fallback(question)
        assert result.correct_answer in result.options


def test_provider_configuration_disables_retries_and_closes_client(monkeypatch):
    calls = {}
    class FakeClient:
        def __init__(self, **kwargs):
            calls.update(kwargs)
            self.models = SimpleNamespace(generate_content=self.generate_content)
        def __enter__(self): return self
        def __exit__(self, *args): calls['closed'] = True
        def generate_content(self, **kwargs):
            calls['request'] = kwargs
            return SimpleNamespace(text='response')
    monkeypatch.setattr(service.genai, 'Client', FakeClient)
    assert service._request_variant('prompt') == 'response'
    assert calls['http_options'].timeout == 20000
    assert calls['http_options'].retry_options.attempts == 1
    assert calls['closed'] is True
