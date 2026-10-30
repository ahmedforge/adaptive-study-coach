"""Local progress storage. Only hashes of browser resume tokens are persisted."""
from contextlib import contextmanager
import hashlib
import json
import os
import secrets
import sqlite3
from pathlib import Path


class ProgressStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS study_sessions (
                token_hash TEXT PRIMARY KEY, version INTEGER NOT NULL,
                payload TEXT NOT NULL)''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, data):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('INSERT INTO study_sessions VALUES (?, 0, ?)',
                       (self.digest(token), json.dumps(data)))
        return token

    def load(self, token):
        with self.connect() as db:
            row = db.execute('SELECT version, payload FROM study_sessions WHERE token_hash = ?',
                             (self.digest(token),)).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def save(self, token, expected_version, data):
        with self.connect() as db:
            result = db.execute('''UPDATE study_sessions SET version = version + 1, payload = ?
                WHERE token_hash = ? AND version = ?''',
                (json.dumps(data), self.digest(token), expected_version))
        return result.rowcount == 1
