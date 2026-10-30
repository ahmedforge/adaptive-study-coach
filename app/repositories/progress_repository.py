"""Progress, ownership and hashed resume capabilities in one SQLite database."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path


class ProgressStore:
    def __init__(self, path, user_id=None):
        self.path = Path(path)
        self.user_id = user_id
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        with self.connect() as db:
            legacy = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='study_sessions'").fetchone()
            migrated = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='session_owners'").fetchone()
            if legacy and not migrated and db.execute('SELECT 1 FROM study_sessions LIMIT 1').fetchone():
                backup_dir = self.path.parent / 'account_migration_backups'
                backup_dir.mkdir(exist_ok=True, mode=0o700)
                backup = backup_dir / f'{self.path.stem}-{secrets.token_hex(8)}.sqlite3'
                fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                destination = sqlite3.connect(backup)
                try: db.backup(destination)
                finally: destination.close()
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS study_sessions (
                    token_hash TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS session_owners (
                    session_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, saved_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS owner_sessions ON session_owners(user_id, saved_at DESC);
                CREATE TABLE IF NOT EXISTS session_aliases (
                    alias_hash TEXT PRIMARY KEY, session_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revision_links (
                    exam_hash TEXT PRIMARY KEY, revision_hash TEXT NOT NULL);
            ''')

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

    def _canonical(self, db, token):
        key = self.digest(token)
        row = db.execute('SELECT session_hash FROM session_aliases WHERE alias_hash=?', (key,)).fetchone()
        return row[0] if row else key

    def _allowed(self, db, key):
        row = db.execute('SELECT user_id FROM session_owners WHERE session_hash=?', (key,)).fetchone()
        return row is None or row[0] == self.user_id

    def _load(self, db, key):
        if not self._allowed(db, key): return None
        row = db.execute('SELECT version,payload FROM study_sessions WHERE token_hash=?', (key,)).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def _own(self, db, key):
        if self.user_id:
            db.execute('INSERT OR IGNORE INTO session_owners VALUES (?,?,?)', (key, self.user_id, time.time()))

    def create(self, data):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            key = self.digest(token)
            db.execute('INSERT INTO study_sessions VALUES (?,0,?)', (key, json.dumps(data)))
            self._own(db, key)
        return token

    def create_once(self, token, data):
        with self.connect() as db:
            key = self.digest(token)
            result = db.execute('INSERT OR IGNORE INTO study_sessions VALUES (?,0,?)', (key, json.dumps(data)))
            if result.rowcount: self._own(db, key)
        return result.rowcount == 1

    def load(self, token):
        with self.connect() as db:
            return self._load(db, self._canonical(db, token))

    def save(self, token, expected_version, data):
        with self.connect() as db:
            key = self._canonical(db, token)
            if not self._allowed(db, key): return False
            result = db.execute('UPDATE study_sessions SET version=version+1,payload=? WHERE token_hash=? AND version=?',
                                (json.dumps(data), key, expected_version))
            if result.rowcount:
                db.execute('UPDATE session_owners SET saved_at=? WHERE session_hash=?', (time.time(), key))
        return result.rowcount == 1

    def load_owned(self, session_id):
        if not self.user_id: return None
        with self.connect() as db:
            owner = db.execute('SELECT user_id FROM session_owners WHERE session_hash=?', (session_id,)).fetchone()
            return self._load(db, session_id) if owner and owner[0] == self.user_id else None

    def library(self, limit=50, offset=0):
        if not self.user_id: return []
        with self.connect() as db:
            rows = db.execute('''SELECT s.token_hash,s.payload FROM study_sessions s
                JOIN session_owners o ON o.session_hash=s.token_hash WHERE o.user_id=?
                ORDER BY o.saved_at DESC,s.token_hash LIMIT ? OFFSET ?''', (self.user_id, limit, offset)).fetchall()
        return [{'id': key, 'kind': 'exam' if json.loads(payload).get('kind') == 'exam' else 'practice'} for key, payload in rows]

    def issue_alias(self, session_id):
        if self.load_owned(session_id) is None: return None
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('INSERT INTO session_aliases VALUES (?,?)', (self.digest(token), session_id))
        return token

    def claim(self, token, kind):
        if not self.user_id: return False
        with self.connect() as db:
            key = self._canonical(db, token)
            record = self._load(db, key)
            if record is None or (record[1].get('kind') == 'exam') != (kind == 'exam'): return False
            self._own(db, key)
            # Re-check the winner if another account claimed concurrently.
            if not self._allowed(db, key): return False
            if kind == 'exam':
                legacy = hmac.new(token.encode(), b'exam-revision:v1', hashlib.sha256).hexdigest()
                legacy_key = self._canonical(db, legacy)
                if self._load(db, legacy_key):
                    db.execute('INSERT OR IGNORE INTO revision_links VALUES (?,?)', (key, legacy_key))
                link = db.execute('SELECT revision_hash FROM revision_links WHERE exam_hash=?', (key,)).fetchone()
                if link and self._allowed(db, link[0]): self._own(db, link[0])
        return True

    def load_revision(self, exam_token, revision_token):
        with self.connect() as db:
            source = self._canonical(db, exam_token)
            if self._load(db, source) is None: return None
            link = db.execute('SELECT revision_hash FROM revision_links WHERE exam_hash=?', (source,)).fetchone()
            if not link: return None
            record = self._load(db, link[0])
            if record is None: raise PermissionError('Revision is not accessible')
            alias = self.digest(revision_token)
            if alias != link[0]: db.execute('INSERT OR IGNORE INTO session_aliases VALUES (?,?)', (alias, link[0]))
            return record

    def create_revision(self, exam_token, revision_token, data):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            source = self._canonical(db, exam_token)
            if self._load(db, source) is None: raise PermissionError('Exam is not accessible')
            link = db.execute('SELECT revision_hash FROM revision_links WHERE exam_hash=?', (source,)).fetchone()
            candidate = self.digest(revision_token)
            if link:
                target = link[0]
                if self._load(db, target) is None: raise PermissionError('Revision is not accessible')
            else:
                target = candidate
                db.execute('INSERT OR IGNORE INTO study_sessions VALUES (?,0,?)', (target, json.dumps(data)))
                if not self._allowed(db, target): raise PermissionError('Revision is not accessible')
                self._own(db, target)
                db.execute('INSERT INTO revision_links VALUES (?,?)', (source, target))
            if candidate != target:
                db.execute('INSERT OR IGNORE INTO session_aliases VALUES (?,?)', (candidate, target))
