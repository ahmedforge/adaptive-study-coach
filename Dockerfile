FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 STUDY_COACH_DB=/data/progress.sqlite3
COPY requirements-core.txt .
RUN pip install --no-cache-dir -r requirements-core.txt \
    && useradd --create-home coach \
    && install -d -o coach -g coach /data
COPY app ./app
USER coach
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
