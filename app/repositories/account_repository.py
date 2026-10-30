import secrets
import time

from app.services.account_service import SESSION_SECONDS


class AccountRepository:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS account_logins (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS user_logins ON account_logins(user_id);
                CREATE TABLE IF NOT EXISTS login_attempts (
                    attempt_key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start REAL NOT NULL);
            ''')

    def create(self, username, encoded):
        user_id = secrets.token_hex(16)
        with self.store.connect() as db:
            db.execute('INSERT INTO accounts VALUES (?,?,?)', (user_id, username, encoded))
        return {'id': user_id, 'username': username}

    def find(self, username):
        with self.store.connect() as db:
            row = db.execute('SELECT id,username,password_hash FROM accounts WHERE username=?', (username,)).fetchone()
        return {'id': row[0], 'username': row[1], 'password_hash': row[2]} if row else None

    def login(self, user_id, old_token=None):
        token = secrets.token_urlsafe(32)
        with self.store.connect() as db:
            db.execute('DELETE FROM account_logins WHERE expires_at<=?', (time.time(),))
            if old_token: db.execute('DELETE FROM account_logins WHERE token_hash=?', (self.store.digest(old_token),))
            db.execute('INSERT INTO account_logins VALUES (?,?,?)',
                       (self.store.digest(token), user_id, time.time() + SESSION_SECONDS))
        return token

    def replace_password(self, user_id, encoded):
        token = secrets.token_urlsafe(32)
        with self.store.connect() as db:
            db.execute('UPDATE accounts SET password_hash=? WHERE id=?', (encoded, user_id))
            db.execute('DELETE FROM account_logins WHERE user_id=?', (user_id,))
            db.execute('INSERT INTO account_logins VALUES (?,?,?)',
                       (self.store.digest(token), user_id, time.time() + SESSION_SECONDS))
        return token

    def authenticate(self, token):
        if not token or len(token) > 100: return None
        with self.store.connect() as db:
            row = db.execute('''SELECT a.id,a.username FROM account_logins s JOIN accounts a ON a.id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>?''', (self.store.digest(token), time.time())).fetchone()
        return {'id': row[0], 'username': row[1]} if row else None

    def logout(self, token):
        if token:
            with self.store.connect() as db:
                db.execute('DELETE FROM account_logins WHERE token_hash=?', (self.store.digest(token),))

    def reserve_attempt(self, key, limit=10):
        """Count attempts before hashing, including concurrent requests."""
        now = time.time()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_attempts WHERE window_start<?', (now - 900,))
            row = db.execute('SELECT attempts FROM login_attempts WHERE attempt_key=?', (key,)).fetchone()
            if row and row[0] >= limit: return False
            db.execute('''INSERT INTO login_attempts VALUES (?,1,?)
                ON CONFLICT(attempt_key) DO UPDATE SET attempts=attempts+1''', (key, now))
        return True
