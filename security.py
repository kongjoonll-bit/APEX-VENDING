"""Apex Vending — 보안 유틸 (비밀번호 해시 · 세션키 · 레이트리밋 · 보안 헤더)"""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict

import database as db

PBKDF2_ROUNDS = 200_000


# ---------- 비밀번호 ----------
def hash_password(password: str) -> str:
    """PBKDF2-SHA256 해시 (salt$hash 형식)"""
    password = password or ''
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                             salt.encode('utf-8'), PBKDF2_ROUNDS)
    return f'pbkdf2${PBKDF2_ROUNDS}${salt}${dk.hex()}'


def verify_password(stored: str, password: str) -> bool:
    stored = stored or ''
    if not stored.startswith('pbkdf2$'):
        # 예전 평문 비밀번호와 비교 (마이그레이션용)
        return hmac.compare_digest(stored, password or '')
    try:
        _, rounds, salt, hexhash = stored.split('$', 3)
        dk = hashlib.pbkdf2_hmac('sha256', (password or '').encode('utf-8'),
                                 salt.encode('utf-8'), int(rounds))
        return hmac.compare_digest(dk.hex(), hexhash)
    except Exception:
        return False


def is_hashed(stored: str) -> bool:
    return bool(stored) and stored.startswith('pbkdf2$')


# ---------- 시크릿 ----------
def get_secret_key() -> str:
    """세션 서명키 — DB에 저장된 랜덤값 사용(없으면 생성)"""
    key = (db.get_setting('flask_secret_key', '') or '').strip()
    if len(key) < 40:
        key = secrets.token_urlsafe(48)
        db.set_setting('flask_secret_key', key)
    return key


def ensure_admin_path() -> str:
    """관리자 패널 비밀 경로 (예: console-3f9a1c2b)"""
    path = (db.get_setting('admin_path', '') or '').strip()
    if not path or len(path) < 8:
        path = 'console-' + secrets.token_hex(6)
        db.set_setting('admin_path', path)
    return path


def ensure_webhook_key() -> str:
    key = (db.get_setting('deposit_webhook_key', '') or '').strip()
    if len(key) < 16:
        key = secrets.token_hex(24)
        db.set_setting('deposit_webhook_key', key)
    return key


# ---------- 레이트리밋 (메모리) ----------
class RateLimiter:
    """간단한 실패 횟수 제한기 (프로세스 메모리 기반)"""

    def __init__(self, max_hits: int = 5, window: int = 900):
        self.max_hits = max_hits
        self.window = window
        self._hits = defaultdict(list)

    def _prune(self, key):
        now = time.time()
        self._hits[key] = [t for t in self._hits[key] if now - t < self.window]

    def blocked(self, key: str) -> bool:
        self._prune(key)
        return len(self._hits[key]) >= self.max_hits

    def hit(self, key: str):
        self._prune(key)
        self._hits[key].append(time.time())

    def reset(self, key: str):
        self._hits.pop(key, None)

    def remaining(self, key: str) -> int:
        self._prune(key)
        return max(0, self.max_hits - len(self._hits[key]))


login_limiter = RateLimiter(max_hits=5, window=900)      # 로그인 5회/15분
pin_limiter = RateLimiter(max_hits=6, window=600)        # 전달페이지 PIN 6회/10분
webhook_limiter = RateLimiter(max_hits=120, window=60)   # 웹훅 분당 제한


# ---------- 헤더/검증 ----------
SECURITY_HEADERS = {
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'X-XSS-Protection': '1; mode=block',
    'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
    'Content-Security-Policy': (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'"
    ),
}


def add_security_headers(app):
    @app.after_request
    def _headers(resp):
        for k, v in SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        resp.headers['Server'] = 'APEX'
        return resp


def same_origin(request) -> bool:
    """POST 요청 출처 검증 (프록시 환경 Host 불일치 허용)"""
    import os
    from urllib.parse import urlparse

    origin = (request.headers.get('Origin') or '').strip()
    referer = (request.headers.get('Referer') or '').strip()
    target = origin or referer
    if not target:
        return True  # Origin/Referer 없는 요청은 통과(웹훅은 키로 별도 검증)

    netloc = urlparse(target).netloc.lower()
    if not netloc:
        return True

    if netloc == (request.host or '').lower():
        return True

    allowed = set()
    try:
        base = (db.get_setting('dashboard_url', '') or '').strip()
        if base:
            allowed.add(urlparse(base).netloc.lower())
    except Exception:
        pass
    env_host = (os.environ.get('RENDER_EXTERNAL_HOSTNAME') or '').strip().lower()
    if env_host:
        allowed.add(env_host)

    return netloc in allowed


def mask(value: str, keep: int = 4) -> str:
    """민감값 마스킹 (앞 keep자만 노출)"""
    v = str(value or '')
    if len(v) <= keep:
        return '*' * len(v)
    return v[:keep] + '*' * (len(v) - keep)
