from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
from threading import Event
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import agent, retrieval
from app.services import embedding_service as embeddings
from app.services import retrieval_service as service


def test_startup_and_exams_work_offline_without_loading_model(tmp_path):
    env = dict(os.environ, HF_HOME=str(tmp_path / 'empty-model-cache'), HF_HUB_OFFLINE='1',
        GEMINI_API_KEY='', STUDY_COACH_DB=str(tmp_path / 'progress.sqlite3'),
        MLFLOW_TRACKING_URI='sqlite:///' + str(tmp_path / 'tracking.db'))
    code = '''
import sys
from fastapi.testclient import TestClient
from app.main import app
from app.services.retrieval_service import retriever
with TestClient(app) as client:
    assert client.get('/health').status_code == 200
    assert client.get('/').status_code == 200
    assert client.get('/exam').status_code == 200
    assert len(client.get('/diagnostic/questions').json()['questions']) == 12
    response = client.post('/exams', json={})
    assert response.status_code == 201
    assert len(response.json()['questions']) == 12
assert retriever.index is None
assert 'sentence_transformers' not in sys.modules
print('offline startup passed')
'''
    result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    assert 'offline startup passed' in result.stdout
    assert not (tmp_path / 'empty-model-cache').exists()


def test_model_load_is_shared_between_concurrent_requests(monkeypatch):
    monkeypatch.setattr(embeddings, '_model', None)
    entered, release = Event(), Event()
    calls = []
    model = SimpleNamespace(encode=lambda texts: np.ones((len(texts), 2)))
    def load():
        calls.append('load')
        entered.set()
        assert release.wait(5)
        return model
    monkeypatch.setattr(embeddings, '_load_model', load)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(embeddings.get_model) for _ in range(6)]
        assert entered.wait(5)
        release.set()
        assert all(f.result(timeout=5) is model for f in futures)
    assert calls == ['load']
    assert embeddings.embed_texts(['a', 'b']).shape == (2, 2)
    assert calls == ['load']


def test_model_load_can_retry_after_failure(monkeypatch):
    monkeypatch.setattr(embeddings, '_model', None)
    model = object()
    calls = []
    def load():
        calls.append(1)
        if len(calls) == 1: raise OSError('offline')
        return model
    monkeypatch.setattr(embeddings, '_load_model', load)
    with pytest.raises(OSError): embeddings.get_model()
    assert embeddings._model is None
    assert embeddings.get_model() is model


def tiny_bank():
    return [SimpleNamespace(id=f'q_{i}', topic='algebra', subtopic='addition', question=f'Question {i}')
            for i in range(2)]


def test_index_is_lazy_and_built_once_under_concurrent_search(monkeypatch):
    monkeypatch.setattr(service, 'load_questions', tiny_bank)
    bank_calls = []
    def embed(texts):
        if len(texts) == 2:
            bank_calls.append(1)
            return np.array([[1., 0.], [0., 1.]])
        return np.array([[1., 0.]])
    monkeypatch.setattr(service, 'embed_texts', embed)
    monkeypatch.setattr(service, 'log_retrieval_run', lambda **kwargs: None)
    retriever = service.QuestionRetriever()
    assert bank_calls == [] and retriever.index is None
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: retriever.search('query', top_k=1), range(6)))
    assert bank_calls == [1]
    assert all(result[0]['question'].id == 'q_0' for result in results)


def test_failed_index_build_is_retryable_and_does_not_log_sensitive_details(monkeypatch, caplog):
    monkeypatch.setattr(service, 'load_questions', tiny_bank)
    calls = []
    def embed(texts):
        calls.append(1)
        if len(calls) == 1: raise RuntimeError('private-model-cache-path')
        return np.ones((len(texts), 2))
    monkeypatch.setattr(service, 'embed_texts', embed)
    monkeypatch.setattr(service, 'log_retrieval_run', lambda **kwargs: None)
    retriever = service.QuestionRetriever()
    with pytest.raises(service.RetrievalUnavailable): retriever.search('query')
    assert retriever.index is None
    assert 'private-model-cache-path' not in caplog.text
    assert retriever.search('query')
    assert retriever.index is not None


def test_search_and_legacy_agent_return_safe_unavailable_responses(monkeypatch):
    def fail(*args, **kwargs): raise service.RetrievalUnavailable('private-error')
    monkeypatch.setattr(retrieval, 'retriever', SimpleNamespace(search=fail))
    monkeypatch.setattr(agent, 'get_practice_question', fail)
    with TestClient(app) as client:
        responses = [client.get('/retrieval/search', params={'query': 'math'}),
            client.post('/agent/start', json={'diagnostic_results': []}),
            client.post('/agent/advance?is_correct=true', json={'diagnostic_results': []})]
    assert all(response.status_code == 503 for response in responses)
    assert all('private-error' not in response.text for response in responses)


def test_practice_and_search_use_one_shared_retriever():
    from app.services import agent_service
    assert agent_service.retriever is retrieval.retriever is service.retriever
