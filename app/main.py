from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routers.retrieval import router as retrieval_router
from fastapi.responses import FileResponse
from app.routers.diagnostic import router as diagnostic_router
from app.routers.agent import router as agent_router
from app.routers.sessions import router as sessions_router

from app.routers.exams import router as exams_router

app = FastAPI(
    title="Adaptive AI Study Coach",
    version="0.1.0",
)

app.include_router(diagnostic_router)
app.include_router(retrieval_router)
app.include_router(agent_router)
app.include_router(sessions_router)
app.include_router(exams_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
def health_check():
    return {"status": "ok"}
@app.get("/", include_in_schema=False)
def home():
    return FileResponse("app/static/index.html")

@app.get('/exam', include_in_schema=False)
def exam_page():
    return FileResponse('app/static/exam.html')
