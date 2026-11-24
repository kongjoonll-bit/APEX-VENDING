"""Roblox 쿠키(.ROBLOSECURITY)만으로 계정 정보 조회"""
import re
import requests

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


def clean_cookie(raw: str) -> str:
    c = (raw or '').strip().strip('"').strip()
    m = re.search(r'_\|WARNING[^;]*', c)
    if m:
        c = m.group(0)
    c = c.replace('.ROBLOSECURITY=', '').strip()
    return c


def _session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Accept': 'application/json'})
    s.cookies.set('.ROBLOSECURITY', cookie, domain='.roblox.com')
    return s


def _get(s, url, **kw):
    try:
        r = s.get(url, timeout=15, **kw)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def check_cookie(raw_cookie: str) -> dict:
    """쿠키 → 계정 리포트 dict (실패 시 {'valid': False, ...})"""
    cookie = clean_cookie(raw_cookie)
    if not cookie:
        return {'valid': False, 'error': '쿠키가 비어 있습니다.'}

    s = _session(cookie)
    me = _get(s, 'https://users.roblox.com/v1/users/authenticated')
    if not me or not me.get('id'):
        return {'valid': False, 'error': '쿠키가 유효하지 않거나 만료되었습니다.'}

    uid = me['id']
    acct = {
        'valid': True,
        'username': me.get('name'),
        'display_name': me.get('displayName'),
        'user_id': uid,
        'created': None, 'age_days': None,
        'robux': None, 'premium': None, 'rap': None, 'rap_items': None,
        'badges': None, 'groups': None, 'friends': None, 'followers': None,
        'inventory': None,
    }

    # 생성일
    info = _get(s, f'https://users.roblox.com/v1/users/{uid}')
    if info and info.get('created'):
        acct['created'] = str(info['created'])[:10]
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(str(info['created']).replace('Z', '+00:00'))
            acct['age_days'] = (datetime.now(timezone.utc) - dt).days
        except Exception:
            pass

    # 로벅 / 프리미엄
    cur = _get(s, 'https://economy.roblox.com/v1/user/currency')
    if cur and 'robux' in cur:
        acct['robux'] = cur['robux']
    mob = _get(s, 'https://www.roblox.com/mobileapi/userinfo')
    if mob:
        if acct['robux'] is None:
            acct['robux'] = mob.get('RobuxBalance')
        acct['premium'] = 'Yes' if mob.get('IsPremium') else 'No'

    # RAP (한정판)
    coll = _get(s, f'https://inventory.roblox.com/v1/users/{uid}/assets/collectibles?limit=100&sortOrder=Desc')
    if coll and isinstance(coll.get('data'), list):
        items = coll['data']
        acct['rap_items'] = coll.get('total') if coll.get('total') is not None else len(items)
        acct['rap'] = sum(int(i.get('recentAveragePrice') or 0) for i in items)

    # 배지 / 친구 / 팔로워
    b = _get(s, f'https://badges.roblox.com/v1/users/{uid}/badges?limit=1')
    if b and 'total' in b:
        acct['badges'] = b['total']
    fr = _get(s, f'https://friends.roblox.com/v1/users/{uid}/friends/count')
    if fr:
        acct['friends'] = fr.get('count')
    fo = _get(s, f'https://friends.roblox.com/v1/users/{uid}/followers/count')
    if fo:
        acct['followers'] = fo.get('count')

    # 그룹 수
    g = _get(s, f'https://groups.roblox.com/v1/users/{uid}/groups/roles')
    if g and isinstance(g.get('data'), list):
        acct['groups'] = len(g['data'])

    return acct
