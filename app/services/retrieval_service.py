import logging
from threading import Lock

import faiss

from app.services.mlflow_service import log_retrieval_run
from app.repositories.question_repository import load_questions
from app.services.embedding_service import embed_texts

logger = logging.getLogger(__name__)


class RetrievalUnavailable(RuntimeError):
    """The embedding model or retrieval index could not serve this request."""


class QuestionRetriever:
    def __init__(self):
        self.questions = load_questions()
        self.index = None
        self._index_lock = Lock()

    def _ensure_index(self):
        if self.index is not None:
            return
        with self._index_lock:
            if self.index is None:
                texts = [f"{q.topic} {q.subtopic} {q.question}" for q in self.questions]
                embeddings = embed_texts(texts).astype('float32')
                faiss.normalize_L2(embeddings)
                index = faiss.IndexFlatIP(embeddings.shape[1])
                index.add(embeddings)
                # Publish only a fully constructed index; failures can be retried.
                self.index = index

    def search(self, query: str, top_k: int = 3, *, topic: str | None = None,
               recent_question_ids: list[str] | None = None):
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if not self.questions:
            return []
        # Filter after ranking the full small bank, not just the nearest few:
        # otherwise an off-topic nearest neighbour can hide valid topic seeds.
        try:
            self._ensure_index()
            query_embedding = embed_texts([query]).astype('float32')
            faiss.normalize_L2(query_embedding)
            scores, indices = self.index.search(query_embedding, len(self.questions))
        except Exception as exc:
            logger.warning('Question retrieval unavailable (%s)', type(exc).__name__)
            raise RetrievalUnavailable('Question retrieval is temporarily unavailable.') from exc
        results = [
            {"question": self.questions[index], "score": float(score)}
            for score, index in zip(scores[0], indices[0])
            if index >= 0 and (topic is None or self.questions[index].topic == topic)
        ]
        # Stable sorting keeps semantic rank among unseen seeds. Seen seeds are
        # ordered by their most recent occurrence: oldest first, never stuck on
        # the top-ranked seed after the bank has been exhausted.
        seen = {question_id: position for position, question_id in enumerate(recent_question_ids or [])}
        results.sort(key=lambda item: (
            item['question'].id in seen, seen.get(item['question'].id, -1),
        ))
        results = results[:top_k]
        if results:
            try:
                log_retrieval_run(query=query, top_k=top_k, top_score=results[0]['score'])
            except Exception as exc:
                logger.warning('Retrieval tracking unavailable (%s)', type(exc).__name__)
        return results


# Share one lazily built index across practice and search within this process.
retriever = QuestionRetriever()
