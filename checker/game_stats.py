"""쿠키(.ROBLOSECURITY)만으로 게임별 로벅 지출 / 플레이 기록 수집

사용:
    from game_stats import get_game_stats
    stats = get_game_stats(cookie)
    # {"games": [{"game": "Blox Fruits", "robux_spent": 1250, "purchases": 7,
    #             "playtime_min": 341}], "total_robux_spent": 1250}
"""
from roblox_api import clean_cookie, _session, _get

TX_PAGE_LIMIT = 100
TX_MAX_PAGES = 15          # 최대 1500건까지 수집


def _transactions(s, uid, tx_type='Purchase'):
    """경제 내역 페이지네이션 수집"""
    out, cursor = [], ''
    for _ in range(TX_MAX_PAGES):
        url = (f'https://economy.roblox.com/v2/users/{uid}/transactions'
               f'?limit={TX_PAGE_LIMIT}&transactionType={tx_type}')
        if cursor:
            url += f'&cursor={cursor}'
        data = _get(s, url)
        if not data or not isinstance(data.get('data'), list):
            break
        out.extend(data['data'])
        cursor = data.get('nextPageCursor')
        if not cursor:
            break
    return out


def _universe_names(s, universe_ids):
    """universeId 목록 → 게임 이름"""
    ids = [str(u) for u in universe_ids if u]
    if not ids:
        return {}
    names = {}
    for i in range(0, len(ids), 50):
        chunk = ','.join(ids[i:i + 50])
        data = _get(s, f'https://games.roblox.com/v1/games?universeIds={chunk}')
        for g in (data or {}).get('data', []) or []:
            names[str(g.get('id'))] = g.get('name')
    return names


def _pass_info(s, pass_id, cache):
    """게임패스 상세 (크리에이터명 확인용, 캐싱)"""
    if pass_id in cache:
        return cache[pass_id]
    d = _get(s, f'https://apis.roblox.com/game-passes/v1/game-passes/{pass_id}/product-info')
    cache[pass_id] = d or {}
    return cache[pass_id]


def _playtime_candidates(s):
    """플레이시간 후보 엔드포인트. 공식 공개 API에는 게임별 플레이시간이 없어
    200을 주는 응답이 있을 때만 사용한다."""
    for url, key in (
        ('https://apis.roblox.com/user-profile-api/v1/user/profiles/get-profiles', None),
        ('https://games.roblox.com/v1/games/playtime', 'data'),
    ):
        d = _get(s, url)
        if isinstance(d, dict) and key and isinstance(d.get(key), list):
            return d[key]
    return []


def get_game_stats(raw_cookie: str) -> dict:
    """쿠키 → 게임별 통계 dict"""
    cookie = clean_cookie(raw_cookie)
    if not cookie:
        return {'ok': False, 'error': '쿠키가 비어 있습니다.'}

    s = _session(cookie)
    me = _get(s, 'https://users.roblox.com/v1/users/authenticated')
    if not me or not me.get('id'):
        return {'ok': False, 'error': '쿠키가 유효하지 않거나 만료되었습니다.'}
    uid = me['id']

    # 1) 로벅 지출 (게임패스 / 개발자 상품 구매)
    spent = _transactions(s, uid, 'Purchase')
    games = {}
    cache = {}
    lookups = 0

    for t in spent:
        det = t.get('details') or {}
        amount = abs(int((t.get('currency') or {}).get('amount') or 0))
        if amount <= 0:
            continue

        typ = (det.get('type') or '').strip()
        subtitle = (det.get('subtitle') or '').strip()
        pname = (det.get('name') or '').strip()
        pid = det.get('id')

        if typ == 'Game Pass':
            # subtitle 이 '게임명'이 아니라 '게임패스를 만든 사람 닉네임'인 경우가 있음
            info = {}
            if pid and lookups < 60:
                info = _pass_info(s, pid, cache)
                lookups += 1
            creator = ((info.get('Creator') or {}).get('Name') or '').strip()
            if creator and subtitle and subtitle.lower() == creator.lower():
                key = pname or f'Game Pass #{pid}'
            elif subtitle:
                key = subtitle
            else:
                key = pname or f'Game Pass #{pid}'
        elif typ == 'Developer Product':
            key = subtitle or pname or '알 수 없는 게임'
        else:
            # 에셋·의류 등 게임 소비가 아닌 거래는 게임 집계에서 제외
            continue

        key = key.strip()
        if not key:
            continue
        g = games.setdefault(key, {'game': key, 'robux_spent': 0,
                                   'purchases': 0, 'playtime_min': None})
        g['robux_spent'] += amount
        g['purchases'] += 1

    # 3) 플레이시간 (제공되는 응답이 있을 때만 병합)
    for row in _playtime_candidates(s):
        nm = (row.get('name') or row.get('game') or '').strip()
        minutes = row.get('minutes') or row.get('playtimeMinutes') or row.get('playtime')
        if nm and isinstance(minutes, (int, float)):
            g = games.setdefault(nm, {'game': nm, 'robux_spent': 0,
                                      'purchases': 0, 'playtime_min': None})
            g['playtime_min'] = int(minutes)

    rows = sorted(games.values(), key=lambda x: x['robux_spent'], reverse=True)
    return {
        'ok': True,
        'username': me.get('name'),
        'user_id': uid,
        'games': rows,
        'total_robux_spent': sum(r['robux_spent'] for r in rows),
        'total_purchases': sum(r['purchases'] for r in rows),
        'playtime_available': any(r['playtime_min'] is not None for r in rows),
    }


def build_report(raw_cookie: str) -> dict:
    """쿠키 → web.py / summarize() 가 바로 쓸 수 있는 report dict"""
    from roblox_api import check_cookie
    acct = check_cookie(raw_cookie)
    if not acct.get('valid'):
        return {'ok': False, 'error': acct.get('error') or '쿠키 검사 실패'}

    gs = get_game_stats(raw_cookie)
    if not gs.get('ok'):
        return gs

    games = []
    for g in gs.get('games', []):
        mins = g.get('playtime_min')
        games.append({'name': g['game'],
                      'robux': g.get('robux_spent') or 0,
                      'hours': round(mins / 60, 2) if mins else None,
                      'raw': ''})
    games.sort(key=lambda x: (-(x['robux'] or 0), -(x['hours'] or 0), x['name']))
    played = [g for g in games if (g['robux'] or 0) > 0 or (g['hours'] or 0) > 0]

    account = {
        'Username': acct.get('username'),
        'User ID': acct.get('user_id'),
        'Balance': acct.get('robux'),
        'Donated': sum(g['robux'] or 0 for g in games),
        'RAP': acct.get('rap'),
        'Premium': acct.get('premium'),
        'Badges': acct.get('badges'),
        'Friends': acct.get('friends'),
        'Followers': acct.get('followers'),
        'Groups': acct.get('groups'),
        'Created': acct.get('created'),
        'Age(days)': acct.get('age_days'),
    }
    return {'ok': True, 'report': {
        'account': account, 'games': games, 'played_games': played,
        'stray_numbers': [],
        'total_spent': sum(g['robux'] or 0 for g in games),
    }}


if __name__ == '__main__':
    import json
    import sys
    ck = sys.argv[1] if len(sys.argv) > 1 else input('cookie: ')
    print(json.dumps(get_game_stats(ck), ensure_ascii=False, indent=2))
