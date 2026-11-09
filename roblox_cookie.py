# -*- coding: utf-8 -*-
"""로블록스 쿠키(.ROBLOSECURITY) 유효성 검사 유틸

TXT 재고 파일에서 쿠키를 추출하고, Roblox 인증 API로 살아있는지 확인한다.
- 200 : 유효 (id / name 반환)
- 401·403 : 무효 (만료 · 로그아웃 · 정지 등)
- 그 외 : 판단 불가 (None) → 무효 처리하지 않음
"""
import re

import requests

AUTH_URL = 'https://users.roblox.com/v1/users/authenticated'
DEFAULT_TIMEOUT = 10

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

# JSON 형태: {"cookie": "..."} / {"ROBLOSECURITY": "..."}
_RE_JSON = re.compile(r'["\']?(?:_?ROBLOSECURITY|cookie)["\']?\s*[:=]\s*["\']([^"\']+)["\']', re.I)
# .ROBLOSECURITY=... 형태
_RE_ASSIGN = re.compile(r'\.ROBLOSECURITY\s*=\s*([^\s;,\'"]+)', re.I)
# 값만 붙어있는 경우 (로블록스 쿠키는 매우 길다)
_RE_LONG_TOKEN = re.compile(r'([A-Za-z0-9_\-|]{200,})')


def clean_cookie(value):
    """쿠키 문자열 정리 (따옴표/접두사/공백 제거)"""
    v = str(value or '').strip().strip('"').strip("'").strip()
    if v.lower().startswith('.roblosecurity='):
        v = v.split('=', 1)[1]
    v = re.sub(r'\s+', '', v)  # 줄바꿈/공백 제거 (여러 줄로 쪼개진 쿠키 대응)
    return v.strip()


def extract_cookie(text):
    """TXT 내용에서 로블록스 쿠키 추출 (없으면 None)

    핵심 규칙: 파일 안의 `_|WARNING` 문자열부터 **파일 끝까지**를 쿠키로 사용한다.
    (앞쪽에 계정 정보 등이 붙어 있어도 무시)
    쿠키가 아닌 일반 텍스트만 있는 파일은 None 을 돌려주므로 검사 대상에서 제외된다.
    """
    if not text:
        return None
    content = str(text).replace('\ufeff', '')

    # 1) _|WARNING 부터 파일 끝까지 (로블록스 쿠키 표준 형식)
    idx = content.find('_|WARNING')
    if idx >= 0:
        tail = content[idx:].strip()
        # 쿠키는 공백 없이 한 덩어리로 오는 것이 표준 → 첫 토큰을 사용
        token = re.split(r'\s+', tail, 1)[0].strip('"\'<>`') if tail else ''
        if len(token) >= 40:
            return token
        # 줄바꿈으로 쪼개져 있으면 공백을 모두 제거해 이어붙임
        joined = re.sub(r'\s+', '', tail).strip('"\'<>`')
        if len(joined) >= 40:
            return joined

    # 2) .ROBLOSECURITY=... 형태
    m = _RE_ASSIGN.search(content)
    if m:
        cookie = clean_cookie(m.group(1))
        if len(cookie) >= 40:
            return cookie

    # 3) JSON 형태 {"cookie": "..."} / {"ROBLOSECURITY": "..."}
    m = _RE_JSON.search(content)
    if m:
        cookie = clean_cookie(m.group(1))
        if len(cookie) >= 40:
            return cookie

    # 4) 값만 덩그러니 있는 경우 (로블록스 쿠키는 200자 이상)
    m = _RE_LONG_TOKEN.search(content)
    if m:
        return clean_cookie(m.group(1))

    return None


def check_cookie(cookie, timeout=DEFAULT_TIMEOUT):
    """쿠키 유효성 검사

    반환: {
      'valid': True | False | None,   # None = 판단 불가(네트워크/서버 오류)
      'user_id': '1234',
      'username': 'abc',
      'error': '사유',
      'status': 200,
    }
    """
    cookie = clean_cookie(cookie)
    if not cookie:
        return {'valid': None, 'error': '쿠키가 비어 있습니다.', 'status': None}

    headers = {
        'Cookie': '.ROBLOSECURITY=' + cookie,
        'User-Agent': _UA,
        'Accept': 'application/json',
    }
    try:
        resp = requests.get(AUTH_URL, headers=headers, timeout=timeout)
    except Exception as e:
        return {'valid': None, 'error': f'요청 실패: {e}', 'status': None}

    status = resp.status_code
    if status == 200:
        try:
            data = resp.json() or {}
        except Exception:
            data = {}
        return {
            'valid': True,
            'user_id': str(data.get('id') or ''),
            'username': str(data.get('name') or ''),
            'error': '',
            'status': status,
        }
    if status in (401, 403):
        return {
            'valid': False,
            'user_id': '',
            'username': '',
            'error': f'인증 실패 (HTTP {status}) · 만료/로그아웃/정지',
            'status': status,
        }
    return {'valid': None, 'error': f'HTTP {status}', 'status': status}


def cookie_preview(cookie, head=12, tail=6):
    """로그/알림용 마스킹된 쿠키 미리보기"""
    cookie = clean_cookie(cookie)
    if not cookie:
        return ''
    if len(cookie) <= head + tail:
        return cookie[:6] + '…'
    return f'{cookie[:head]}…{cookie[-tail:]}'
