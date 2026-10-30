"""Password hashing, expiring sessions, and same-origin mutation checks."""
import os
import ipaddress
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException

COOKIE = 'study_coach_login'
SESSION_SECONDS = 7 * 24 * 60 * 60
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
# Matching-cost verification for unknown users prevents a cheap username timing oracle.
DUMMY_HASH = hasher.hash('not-a-real-account-password')


def verify_password(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def check_mutation(request):
    if request.url.scheme != 'https':
        try:
            local_peer = ipaddress.ip_address(request.client.host).is_loopback
        except (ValueError, AttributeError):
            local_peer = False
        if request.url.hostname not in ('localhost', '127.0.0.1', '::1') or not local_peer:
            raise HTTPException(400, 'Accounts require HTTPS outside local development.')
    if request.headers.get('x-study-coach') != '1':
        raise HTTPException(403, 'Refresh this page before submitting changes.')
    origin = request.headers.get('origin')
    if origin:
        source = urlsplit(origin)
        if source.scheme != request.url.scheme or source.netloc.lower() != request.url.netloc.lower():
            raise HTTPException(403, 'Cross-site changes are not allowed.')


def secure_cookie(request):
    configured = os.getenv('STUDY_COACH_COOKIE_SECURE')
    return configured.lower() not in ('0', 'false') if configured is not None else request.url.scheme == 'https'
