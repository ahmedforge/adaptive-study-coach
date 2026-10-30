import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.routers.retrieval import router as retrieval_router
from fastapi.responses import FileResponse
from app.routers.diagnostic import router as diagnostic_router
from app.routers.agent import router as agent_router
from app.routers.sessions import router as sessions_router

from app.routers.exams import router as exams_router
from app.routers.progress import router as progress_router
from app.routers.account import router as account_router

app = FastAPI(
    title="Adaptive AI Study Coach",
    version="0.1.0",
)

app.include_router(diagnostic_router)
app.include_router(retrieval_router)
app.include_router(agent_router)
app.include_router(sessions_router)
app.include_router(exams_router)
app.include_router(progress_router)
app.include_router(account_router)
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


@app.get('/dashboard', include_in_schema=False)
def dashboard_page():
    return FileResponse('app/static/dashboard.html')


@app.get('/account', include_in_schema=False)
def account_page():
    return FileResponse('app/static/account.html')


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc):
    if request.url.path.startswith('/account/'):
        return JSONResponse(status_code=422, content={'detail': 'Check the account fields. Usernames use 3–32 letters, digits, or underscores; passwords use 12–128 characters.'})
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(sqlite3.Error)
async def storage_error(request: Request, exc):
    return JSONResponse(status_code=503, content={'detail': 'Account or progress storage is unavailable. Please retry.'})
