from app.services.retrieval_service import QuestionRetriever


def test_retrieval_returns_relevant_question():
    retriever = QuestionRetriever()

    results = retriever.search("quadratic equation roots", top_k=3)

    assert len(results) > 0
    assert results[0]["question"].id == "alg_001"
    assert results[0]["score"] > 0