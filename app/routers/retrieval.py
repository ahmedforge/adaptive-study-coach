from fastapi import APIRouter, HTTPException, Query

from app.services.retrieval_service import RetrievalUnavailable, retriever


router = APIRouter(
    prefix="/retrieval",
    tags=["retrieval"],
)



@router.get("/search")
def search_questions(query: str = Query(min_length=1, max_length=500),
                     top_k: int = Query(default=3, ge=1, le=20)):
    if not query.strip():
        raise HTTPException(422, "Enter a non-empty search query.")
    try:
        results = retriever.search(query, top_k)
    except RetrievalUnavailable as exc:
        raise HTTPException(503, 'Search is temporarily unavailable. Please retry.') from exc

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