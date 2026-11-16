"""Apex Checker — 결과 웹페이지 (모바일/PC 반응형)"""
import os
from flask import Flask, render_template_string, abort
import database as db
from cookie_parser import summarize, fmt_hours

app = Flask(__name__)
db.init()

TPL = """<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ s.username or '쿠키 리포트' }} · Apex Checker</title>
<style>
:root{--bg:#0b0f14;--card:#151c26;--line:#26313f;--txt:#eef3f9;--sub:#93a3b8;--acc:#2ecc71;--warn:#f2c14e;--blue:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Malgun Gothic",sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:20px}
header{display:flex;align-items:center;gap:12px;margin:8px 0 20px}
.logo{width:44px;height:44px;border-radius:12px;background:#1b2532;border:2px solid var(--acc);display:grid;place-items:center;color:var(--acc);font-weight:800}
h1{font-size:22px;margin:0}small{color:var(--sub)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.stat .k{font-size:12px;color:var(--sub)}.stat .v{font-size:20px;font-weight:700;margin-top:4px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;margin-bottom:18px}
.card h2{font-size:15px;margin:0 0 12px;color:var(--blue)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:9px 6px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--sub);font-weight:600;font-size:12px}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.bar{height:6px;background:#20303f;border-radius:4px;overflow:hidden;margin-top:6px}
.bar>i{display:block;height:100%;background:var(--acc)}
.pill{display:inline-block;font-size:12px;padding:3px 9px;border-radius:999px;background:#1d2a38;color:var(--acc);border:1px solid #2b3d4f}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.grid2{grid-template-columns:1fr}.wrap{padding:14px}h1{font-size:19px}}
.kv{display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid var(--line);font-size:14px}
.kv span:first-child{color:var(--sub)}
footer{color:var(--sub);font-size:12px;text-align:center;padding:14px 0}
</style></head><body><div class="wrap">
<header><div class="logo">A</div><div><h1>{{ s.username or '알 수 없음' }} <span class="pill">{{ s.premium|yesno }}</span></h1>
<small>User ID {{ s.user_id or '-' }} · {{ created }}</small></div></header>

<div class="grid">
  <div class="stat"><div class="k">로벅 잔액</div><div class="v">{{ s.balance if s.balance is not none else '-' }}</div></div>
  <div class="stat"><div class="k">기부(Donated)</div><div class="v">{{ s.donated if s.donated is not none else '-' }}</div></div>
  <div class="stat"><div class="k">RAP</div><div class="v">{{ s.rap if s.rap is not none else '-' }}</div></div>
  <div class="stat"><div class="k">플레이 게임</div><div class="v">{{ s.games_played }} / {{ s.games_total }}</div></div>
  <div class="stat"><div class="k">게임 로벅 합계</div><div class="v">{{ '{:,}'.format(s.total_robux) }}</div></div>
  <div class="stat"><div class="k">총 플레이타임</div><div class="v">{{ s.total_hours_text }}</div></div>
</div>

<div class="card">
  <h2>로벅을 가장 많이 쓴 게임 (전체)</h2>
  <table><thead><tr><th>#</th><th>게임</th><th class="num">로벅 사용</th><th class="num">플레이시간</th></tr></thead><tbody>
  {% for g in games %}
  <tr><td>{{ loop.index }}</td><td>{{ g.name }}<div class="bar"><i style="width:{{ pct(g.robux) }}%"></i></div></td>
  <td class="num">{{ '{:,}'.format(g.robux or 0) }}</td><td class="num">{{ hh(g.hours) }}</td></tr>
  {% else %}<tr><td colspan="4" style="color:#93a3b8">데이터 없음</td></tr>{% endfor %}
  </tbody></table>
</div>

<div class="grid2">
  <div class="card"><h2>계정 정보</h2>
    {% for k,v in account.items() %}
      {% if k != 'memo' %}<div class="kv"><span>{{ k }}</span><span>{{ v }}</span></div>{% endif %}
    {% endfor %}
  </div>
  <div class="card"><h2>요약</h2>
    <div class="kv"><span>최다 로벅 게임</span><span>{{ s.top_robux.name if s.top_robux else '-' }}</span></div>
    <div class="kv"><span>최장 플레이 게임</span><span>{{ s.top_time.name if s.top_time else '-' }}</span></div>
    <div class="kv"><span>총 사용(추정)</span><span>{{ '{:,}'.format(s.total_spent) if s.total_spent else '-' }}</span></div>
    <div class="kv"><span>메일 인증</span><span>{{ s.mail }}</span></div>
    <div class="kv"><span>카드 등록</span><span>{{ s.cards }}</span></div>
  </div>
</div>
<footer>APEX CHECKER · {{ created }} · 이 페이지 링크를 아는 사람만 열람할 수 있습니다.</footer>
</div></body></html>"""


@app.template_filter('yesno')
def yesno(v):
    if v is True or str(v).lower() in ('yes', 'true'):
        return 'PREMIUM'
    return '일반'


@app.route('/c/<token>')
def view(token):
    row = db.get(token)
    if not row:
        abort(404)
    rep = row['report']
    s = summarize(rep)
    games = rep.get('played_games') or []
    top = max([(g['robux'] or 0) for g in games], default=1) or 1
    import datetime
    return render_template_string(
        TPL, s=s, games=games, account=rep['account'],
        created=datetime.datetime.utcfromtimestamp(row['created_at']).strftime('%Y-%m-%d %H:%M UTC'),
        pct=lambda v: round(((v or 0) / top) * 100, 1), hh=fmt_hours)


@app.route('/ping')
def ping():
    return {'status': 'ok'}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)))
