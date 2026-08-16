from fastapi import APIRouter

from app.services.retrieval_service import QuestionRetriever


router = APIRouter(
    prefix="/retrieval",
    tags=["retrieval"],
)

retriever = QuestionRetriever()


@router.get("/search")
def search_questions(query: str, top_k: int = 3):
    results = retriever.search(query, top_k)

    return {
        "results": [
            {
                "id": item["question"].id,
                "topic": item["question"].topic,
                "subtopic": item["question"].subtopic,
                "question": item["question"].question,
                "score": item["score"],
            }
            for item in results
        ]
    }