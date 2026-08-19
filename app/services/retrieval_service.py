import faiss
import numpy as np
from app.services.mlflow_service import log_retrieval_run
from app.repositories.question_repository import load_questions
from app.services.embedding_service import embed_texts


class QuestionRetriever:
    def __init__(self):
        self.questions = load_questions()

        texts = [
            f"{question.topic} {question.subtopic} {question.question}"
            for question in self.questions
        ]

        embeddings = embed_texts(texts).astype("float32")

        faiss.normalize_L2(embeddings)

        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings)

    def search(self, query: str, top_k: int = 3):
        query_embedding = embed_texts([query]).astype("float32")
        faiss.normalize_L2(query_embedding)

        scores, indices = self.index.search(query_embedding, top_k)

        results = []

        for score, index in zip(scores[0], indices[0]):
            if index == -1:
                continue

            results.append(
                {
                    "question": self.questions[index],
                    "score": float(score),
                }
            )
        if results:
            log_retrieval_run(
            query=query,
            top_k=top_k,
            top_score=results[0]["score"],
            )
        return results