"""Apex Checker — 쿠키 정보 파서 (로벅 사용 + 플레이타임 동시 지원)"""
from __future__ import annotations
import re
from typing import Any, Dict, List

ACCOUNT_KEYS = {
    'username', 'user id', 'userid', 'balance', 'donated', 'rap', 'rap items',
    'rap items count', 'pending', 'billing', 'cards', 'premium', 'mail',
    'playtime', 'play time', 'badges', 'badges count', 'passes', 'passes count',
    'created', 'age', 'followers', 'following', 'friends', 'groups', 'headless',
    'korblox', 'verified', 'email', '2fa', 'robux', 'limiteds', 'country',
    'last online', 'signup', 'inventory', 'assets',
}

_TIME_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|시간|d|day|days|일|m|min|분)\b', re.I)
_NUM_RE = re.compile(r'-?\d+(?:\.\d+)?')


def _int_or_none(v):
    s = str(v).strip().replace(',', '')
    if s.lower() in ('none', 'no', 'null', '-', ''):
        return None
    if s.lower() in ('yes', 'true'):
        return True
    return int(float(s)) if re.fullmatch(r'-?\d+(\.\d+)?', s) else None


def _hours(text: str):
    m = _TIME_RE.search(text or '')
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).lower()
    if unit in ('m', 'min', '분'):
        return round(val / 60, 2)
    if unit in ('d', 'day', 'days', '일'):
        return round(val * 24, 2)
    return val


def fmt_hours(h):
    if not h:
        return '-'
    return f"{h/24:.1f}일 ({h:.0f}h)" if h >= 24 else f"{h:.1f}h"


def parse_cookie_report(raw: str) -> Dict[str, Any]:
    text = (raw or '').replace('\r', ' ').replace('\n', ' | ')
    parts = [p.strip() for p in text.split('|') if p.strip()]

    account: Dict[str, Any] = {}
    games: List[Dict[str, Any]] = []
    stray_numbers: List[int] = []

    for chunk in parts:
        m = re.match(r'^(.*?)\s*:\s*(.*)$', chunk)
        if m:
            key, val = m.group(1).strip(), m.group(2).strip()
            low = key.lower()
            nums = _NUM_RE.findall(val)

            if low not in ACCOUNT_KEYS and nums:
                hours = _hours(val)
                robux = None
                if hours is not None:
                    rest = _TIME_RE.sub(' ', val)
                    rest_nums = _NUM_RE.findall(rest)
                    robux = int(float(rest_nums[0])) if rest_nums else None
                else:
                    robux = int(float(nums[0]))
                games.append({'name': key, 'robux': robux, 'hours': hours, 'raw': val})
                continue

            num = _int_or_none(val)
            h = _hours(val) if re.search(r'\d\s*(h|시간|일|d\b)', val, re.I) else None
            account[key] = fmt_hours(h) if (h is not None and num is None) else (num if num is not None else val)
            continue

        if re.fullmatch(r'\d+', chunk.replace(',', '')):
            stray_numbers.append(int(chunk.replace(',', '')))
            continue
        account.setdefault('memo', [])
        if isinstance(account['memo'], list):
            account['memo'].append(chunk)

    games.sort(key=lambda g: (-(g['robux'] or 0), -(g['hours'] or 0), g['name']))
    played = [g for g in games if (g['robux'] or 0) > 0 or (g['hours'] or 0) > 0]

    return {
        'account': account,
        'games': games,
        'played_games': played,
        'stray_numbers': stray_numbers,
        'total_spent': stray_numbers[-1] if stray_numbers else None,
    }


def summarize(report: Dict[str, Any]) -> Dict[str, Any]:
    played = report.get('played_games') or []
    by_robux = sorted(played, key=lambda g: -(g['robux'] or 0))
    by_time = sorted(played, key=lambda g: -(g['hours'] or 0))
    total_robux = sum(g['robux'] or 0 for g in played)
    total_hours = round(sum(g['hours'] or 0 for g in played), 2)
    return {
        'username': report['account'].get('Username'),
        'user_id': report['account'].get('User ID'),
        'balance': report['account'].get('Balance'),
        'donated': report['account'].get('Donated'),
        'rap': report['account'].get('RAP'),
        'premium': report['account'].get('Premium'),
        'mail': report['account'].get('Mail'),
        'cards': report['account'].get('Cards'),
        'games_played': len(played),
        'games_total': len(report.get('games') or []),
        'total_robux': total_robux,
        'total_hours': total_hours,
        'total_hours_text': fmt_hours(total_hours),
        'top_robux': by_robux[0] if by_robux else None,
        'top_time': by_time[0] if by_time else None,
        'total_spent': report.get('total_spent'),
    }
