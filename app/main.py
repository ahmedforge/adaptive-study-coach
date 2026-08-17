from fastapi import FastAPI
from app.routers.retrieval import router as retrieval_router

from app.routers.diagnostic import router as diagnostic_router
from app.routers.agent import router as agent_router

app = FastAPI(
    title="Adaptive AI Study Coach",
    version="0.1.0",
)

app.include_router(diagnostic_router)
app.include_router(retrieval_router)
app.include_router(agent_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}