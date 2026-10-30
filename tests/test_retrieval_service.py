from app.services.retrieval_service import QuestionRetriever


def test_retrieval_returns_relevant_question():
    retriever = QuestionRetriever()

    results = retriever.search("quadratic equation roots", top_k=3)

    assert len(results) > 0
    assert results[0]["question"].topic == "quadratic_equations"
    assert results[0]["score"] > 0

# Controlled rankings deliberately put the wrong topic first, so these tests
# cannot pass merely because the embedding model happens to rank well.
import numpy as np
import pytest
from types import SimpleNamespace
import app.services.retrieval_service as service


@pytest.fixture
def ranked_retriever(monkeypatch):
    retriever = object.__new__(QuestionRetriever)
    retriever.questions = [
        SimpleNamespace(id='off-topic', topic='trigonometry'),
        SimpleNamespace(id='q1', topic='algebra'),
        SimpleNamespace(id='q2', topic='algebra'),
        SimpleNamespace(id='q3', topic='algebra'),
    ]
    class Index:
        def search(self, query, count):
            assert count == 4
            return np.array([[.99, .8, .7, .6]]), np.array([[0, 1, 2, 3]])
    retriever.index = Index()
    monkeypatch.setattr(service, 'embed_texts', lambda texts: np.array([[1., 0.]]))
    monkeypatch.setattr(service, 'log_retrieval_run', lambda **kwargs: None)
    return retriever


def ids(results):
    return [item['question'].id for item in results]


def test_topic_filter_excludes_higher_ranked_other_topic(ranked_retriever):
    assert ids(ranked_retriever.search('algebra', topic='algebra')) == ['q1', 'q2', 'q3']


def test_unseen_topic_seed_precedes_seen_diagnostic(ranked_retriever):
    assert ids(ranked_retriever.search('algebra', top_k=1, topic='algebra',
        recent_question_ids=['q1'])) == ['q2']


def test_exhausted_pool_reuses_least_recent_seed(ranked_retriever):
    assert ids(ranked_retriever.search('algebra', topic='algebra',
        recent_question_ids=['q1', 'q2', 'q3', 'q1'])) == ['q2', 'q3', 'q1']


def test_single_seed_remains_available_when_seen(ranked_retriever):
    assert ids(ranked_retriever.search('trig', topic='trigonometry',
        recent_question_ids=['off-topic'])) == ['off-topic']


def test_missing_topic_returns_no_wrong_topic_seed(ranked_retriever):
    assert ranked_retriever.search('unknown', topic='unknown') == []


def test_no_filter_preserves_general_search(ranked_retriever):
    assert ids(ranked_retriever.search('query', top_k=2)) == ['off-topic', 'q1']


def test_tracking_outage_does_not_break_practice(ranked_retriever, monkeypatch, caplog):
    def fail(**kwargs): raise RuntimeError('private-tracking-details')
    monkeypatch.setattr(service, 'log_retrieval_run', fail)
    assert ids(ranked_retriever.search('algebra', topic='algebra')) == ['q1', 'q2', 'q3']
    assert 'private-tracking-details' not in caplog.text


def test_invalid_result_count_is_rejected(ranked_retriever):
    with pytest.raises(ValueError): ranked_retriever.search('query', top_k=0)
