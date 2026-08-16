from fastapi import FastAPI

app = FastAPI(
    title="Adaptive AI Study Coach",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}