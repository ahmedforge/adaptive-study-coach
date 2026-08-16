from fastapi import FastAPI

from app.routers.diagnostic import router as diagnostic_router


app = FastAPI(
    title="Adaptive AI Study Coach",
    version="0.1.0",
)

app.include_router(diagnostic_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}