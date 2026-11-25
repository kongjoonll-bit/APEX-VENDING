"""Apex Vending — 구매 후 웹 전달 페이지 (/p/<token>)

- PIN 6자리 보호
- 계정 정보(안내문)는 그대로 표시, 쿠키는 `_|WARNING` 부터 복사
- 모바일/PC 반응형 + 애니메이션
"""
import io
import re

from flask import abort, render_template_string, request, send_file, session

import database as db

CSS = """
:root{--bg:#06080d;--card:#0f1621;--card2:#0b1119;--line:#1d2a3a;--txt:#eef4fb;--sub:#8ea1b8;
--gold:#e0b64a;--gold2:#f7dc94;--green:#31d07b;--red:#ef4444}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--txt);overflow-x:hidden;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
.bg{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none}
.blob{position:absolute;border-radius:50%;filter:blur(90px);opacity:.5;animation:float 18s ease-in-out infinite}
.b1{width:520px;height:520px;left:-140px;top:-160px;background:radial-gradient(circle,#e0b64a55,transparent 65%)}
.b2{width:460px;height:460px;right:-120px;top:8%;background:radial-gradient(circle,#2f6dff44,transparent 65%);animation-delay:-6s}
.b3{width:520px;height:520px;left:20%;bottom:-220px;background:radial-gradient(circle,#31d07b33,transparent 65%);animation-delay:-11s}
@keyframes float{0%,100%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(0,-36px,0) scale(1.07)}}
.grid{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.35;
background-image:linear-gradient(rgba(255,255,255,.028) 1px,transparent 1px),
linear-gradient(90deg,rgba(255,255,255,.028) 1px,transparent 1px);
background-size:44px 44px;mask-image:radial-gradient(circle at 50% 18%,#000 30%,transparent 78%)}
.wrap{position:relative;z-index:2;max-width:920px;margin:0 auto;padding:26px 16px 96px}
.brand{display:flex;align-items:center;gap:10px;font-size:12.5px;letter-spacing:.26em;
color:var(--gold2);font-weight:800;margin-bottom:18px;animation:rise .7s cubic-bezier(.2,.8,.2,1) both}
.brand .dot{width:8px;height:8px;border-radius:50%;background:var(--gold);box-shadow:0 0 14px var(--gold)}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
.card{position:relative;border-radius:24px;border:1px solid var(--line);padding:22px;
background:linear-gradient(160deg,rgba(224,182,74,.07),rgba(15,22,33,.96) 42%,var(--card2));
box-shadow:0 34px 80px -40px rgba(0,0,0,.95),inset 0 1px 0 rgba(255,255,255,.05);
animation:rise .8s .05s cubic-bezier(.2,.8,.2,1) both}
.card:before{content:'';position:absolute;inset:0;border-radius:24px;padding:1px;pointer-events:none;
background:linear-gradient(140deg,rgba(224,182,74,.6),transparent 38%,transparent 62%,rgba(49,208,123,.25));
-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);
-webkit-mask-composite:xor;mask-composite:exclude}
.phead{display:flex;align-items:center;gap:14px;margin-bottom:18px;flex-wrap:wrap}
.mark{width:52px;height:52px;border-radius:16px;display:grid;place-items:center;flex:0 0 auto;
font-weight:900;font-size:22px;color:#20180a;background:linear-gradient(135deg,var(--gold2),var(--gold));
box-shadow:0 12px 26px -12px rgba(224,182,74,.9)}
.ptitle{font-size:19px;font-weight:800;letter-spacing:-.02em;line-height:1.3}
.psub{font-size:12.5px;color:var(--sub);margin-top:4px}
.tag{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:800;letter-spacing:.08em;
padding:5px 10px;border-radius:999px;border:1px solid rgba(49,208,123,.35);color:#7ff0b4;
background:rgba(49,208,123,.1)}
.tag.warn{border-color:rgba(239,68,68,.35);color:#ffb4b4;background:rgba(239,68,68,.1)}
.lock{text-align:center;padding:14px 6px 4px}
.lockicon{width:74px;height:74px;margin:0 auto 16px;border-radius:24px;display:grid;place-items:center;
font-size:30px;background:linear-gradient(150deg,rgba(224,182,74,.16),rgba(15,22,33,.9));
border:1px solid rgba(224,182,74,.3);box-shadow:0 18px 40px -22px rgba(224,182,74,.8);
animation:breathe 3.4s ease-in-out infinite}
@keyframes breathe{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
.lockh{font-size:17px;font-weight:800;margin-bottom:6px}
.locksub{font-size:13px;color:var(--sub);line-height:1.6;margin-bottom:20px}
.pinform{display:flex;flex-direction:column;align-items:center;gap:14px}
.pin{width:100%;max-width:330px;text-align:center;font-size:26px;font-weight:800;letter-spacing:.42em;
padding:16px 10px 16px 22px;border-radius:16px;border:1px solid rgba(224,182,74,.35);
background:rgba(6,10,16,.85);color:var(--gold2);outline:none;
font-family:ui-monospace,SFMono-Regular,Consolas,monospace;transition:.2s}
.pin:focus{border-color:var(--gold);box-shadow:0 0 0 4px rgba(224,182,74,.14);background:rgba(10,16,24,.95)}
.pin::placeholder{color:#4a5a70;letter-spacing:.3em}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:9px;border:0;cursor:pointer;
border-radius:14px;font-weight:800;font-size:14.5px;padding:14px 22px;transition:transform .16s,filter .16s,box-shadow .2s;
font-family:inherit}
.btn:active{transform:scale(.98)}
.btn.gold{width:100%;max-width:330px;color:#20180a;background:linear-gradient(135deg,var(--gold2),var(--gold));
box-shadow:0 16px 34px -16px rgba(224,182,74,.95)}
.btn.gold:hover{filter:brightness(1.07)}
.btn.ghost{background:rgba(255,255,255,.05);color:var(--txt);border:1px solid var(--line)}
.btn.ghost:hover{background:rgba(255,255,255,.1)}
.btn.green{background:linear-gradient(135deg,#4ade80,#22c55e);color:#04210f;
box-shadow:0 14px 30px -14px rgba(34,197,94,.9)}
.err{margin-top:14px;font-size:13px;color:#ffb4b4;background:rgba(239,68,68,.1);
border:1px solid rgba(239,68,68,.32);padding:11px 14px;border-radius:12px}
.shake{animation:shake .42s cubic-bezier(.36,.07,.19,.97) both}
@keyframes shake{10%,90%{transform:translateX(-2px)}20%,80%{transform:translateX(4px)}
30%,50%,70%{transform:translateX(-7px)}40%,60%{transform:translateX(7px)}}
.sect{margin-top:22px}
.sect-h{display:flex;align-items:center;gap:9px;font-size:12px;letter-spacing:.16em;text-transform:uppercase;
color:var(--gold2);font-weight:800;margin-bottom:12px}
.sect-h:before{content:'';width:3px;height:13px;border-radius:2px;background:var(--gold)}
.info{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:9px}
.kv{padding:11px 13px;border-radius:13px;border:1px solid var(--line);background:rgba(255,255,255,.025)}
.kv .k{font-size:11px;color:var(--sub);letter-spacing:.03em}
.kv .v{font-size:14.5px;font-weight:800;margin-top:4px;word-break:break-all;font-variant-numeric:tabular-nums}
.codebox{position:relative;border-radius:16px;border:1px solid var(--line);background:#070b11;overflow:hidden}
.codebox .bar{display:flex;align-items:center;gap:8px;padding:10px 13px;border-bottom:1px solid var(--line);
background:rgba(255,255,255,.03);font-size:11.5px;color:var(--sub);letter-spacing:.05em}
.codebox .bar b{color:var(--gold2);font-weight:800}
.codebox pre{margin:0;padding:15px;max-height:46vh;overflow:auto;white-space:pre-wrap;word-break:break-all;
font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12.5px;line-height:1.65;color:#cfe0f5}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:13px}
.actions .btn{flex:1 1 190px}
.hint{font-size:11.5px;color:var(--sub);line-height:1.7;margin-top:10px}
.foot{margin-top:22px;text-align:center;font-size:11.5px;color:#5b6b80;line-height:1.9;
animation:rise .8s .2s both}
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(20px);
background:rgba(16,26,38,.96);border:1px solid rgba(49,208,123,.4);color:#9df5c4;
padding:13px 20px;border-radius:14px;font-size:13.5px;font-weight:700;z-index:99;
box-shadow:0 20px 50px -20px rgba(0,0,0,.9);opacity:0;pointer-events:none;transition:.3s}
.toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
.copied{background:linear-gradient(135deg,#4ade80,#22c55e)!important;color:#04210f!important;border-color:transparent!important}
@media(max-width:640px){
 .wrap{padding:16px 12px 96px}
 .card{padding:17px;border-radius:20px}
 .ptitle{font-size:16.5px}
 .mark{width:46px;height:46px;border-radius:14px;font-size:19px}
 .pin{font-size:23px;padding:14px 8px 14px 16px}
 .info{grid-template-columns:1fr 1fr}
 .codebox pre{max-height:38vh;font-size:12px}
 .actions{position:sticky;bottom:0;background:linear-gradient(180deg,transparent,rgba(6,8,13,.94) 40%);
 padding-top:10px;margin-top:14px}
}
"""

TEMPLATE = """<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{{ d.product_name }} · APEX VENDING</title>
<style>{{ css }}</style></head><body>
<div class="bg"><div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div></div>
<div class="grid"></div>
<div class="wrap">
  <div class="brand"><span class="dot"></span>APEX VENDING · SECURE DELIVERY</div>

  <div class="card">
    <div class="phead">
      <div class="mark">A</div>
      <div style="min-width:0;flex:1">
        <div class="ptitle">{{ d.product_name }}</div>
        <div class="psub">주문 #{{ d.order_id }} · {{ created }} · {{ '{:,}'.format(d.amount or 0) }}P</div>
      </div>
      {% if unlocked %}<span class="tag">● UNLOCKED</span>{% else %}<span class="tag warn">● LOCKED</span>{% endif %}
    </div>

    {% if not unlocked %}
    <div class="lock">
      <div class="lockicon">🔒</div>
      <div class="lockh">전달 페이지 잠금</div>
      <div class="locksub">구매 완료 DM에 표시된 <b>PIN 6자리</b>를 입력해주세요.</div>
      <form class="pinform" method="post">
        <input class="pin{% if shake %} shake{% endif %}" name="pin" inputmode="numeric"
               pattern="[0-9]*" maxlength="6" autocomplete="one-time-code" placeholder="000000"
               value="" autofocus>
        <button class="btn gold" type="submit">잠금 해제</button>
      </form>
      {% if err %}<div class="err">{{ err }}</div>{% endif %}
    </div>
    {% else %}
    {% if info %}
    <div class="sect">
      <div class="sect-h">계정 정보</div>
      <div class="info">
        {% for k, v in info %}
        <div class="kv"><div class="k">{{ k }}</div><div class="v">{{ v or '-' }}</div></div>
        {% endfor %}
      </div>
    </div>
    {% endif %}

    <div class="sect">
      <div class="sect-h">쿠키</div>
      <div class="codebox">
        <div class="bar"><b>_|WARNING</b> 부터 복사 · {{ cookie|length }}자</div>
        <pre id="cookie">{{ cookie }}</pre>
      </div>
      <div class="actions">
        <button class="btn green" onclick="copyCookie(this)">쿠키 복사</button>
        <button class="btn ghost" onclick="copyText(this, document.getElementById('cookie').innerText)">전체 복사</button>
        {% if has_file %}<a class="btn ghost" href="/p/{{ token }}/file">파일 다운로드</a>{% endif %}
      </div>
      <div class="hint">· 붙여넣을 때 <b>앞뒤 공백</b>이 섞이지 않게 해주세요.<br>
        · 위 계정/게임 정보는 참고용이며 지우지 않아도 됩니다.</div>
    </div>
    {% endif %}
  </div>

  <div class="foot">APEX VENDING · 이 링크와 PIN은 타인과 공유하지 마세요.<br>
    문의는 디스코드 자판기의 <b>정보</b> 버튼을 이용해주세요.</div>
</div>

<div class="toast" id="toast"></div>
<script>
function toast(msg){var t=document.getElementById('toast');t.textContent=msg;t.classList.add('on');
clearTimeout(t._h);t._h=setTimeout(function(){t.classList.remove('on')},1900);}
function fb(text){var ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';
ta.style.opacity='0';document.body.appendChild(ta);ta.select();
try{document.execCommand('copy')}catch(e){}document.body.removeChild(ta);}
function copyText(btn,text){
 var done=function(){btn.classList.add('copied');var o=btn.textContent;btn.textContent='복사됨 ✓';
 toast('클립보드에 복사했습니다');setTimeout(function(){btn.classList.remove('copied');btn.textContent=o},1600);};
 if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(text).then(done).catch(function(){fb(text);done();});}
 else{fb(text);done();}
}
function copyCookie(btn){
 var raw=document.getElementById('cookie').innerText||'';
 var i=raw.indexOf('_|WARNING');
 copyText(btn,(i>=0?raw.slice(i):raw).trim());
}
var pin=document.querySelector('.pin');
if(pin){pin.addEventListener('input',function(){this.value=this.value.replace(/\\D/g,'').slice(0,6);});}
</script></body></html>"""


def split_delivery(content):
    """전달 내용 → (계정정보 [(k,v)], 쿠키 텍스트)

    `_|WARNING` 앞부분은 계정/게임 정보로 표시하고, 쿠키는 그 지점부터 잘라낸다.
    """
    text = content or ''
    idx = text.find('_|WARNING')
    info_part = text[:idx] if idx >= 0 else text
    cookie = text[idx:] if idx >= 0 else ''

    rows = []
    for chunk in re.split(r'[|\n]', info_part):
        chunk = chunk.strip().strip('|').strip()
        if not chunk:
            continue
        if ':' in chunk:
            k, v = chunk.split(':', 1)
            rows.append((k.strip(), v.strip()))
        else:
            rows.append((chunk, ''))
    return rows, cookie.strip()


def register(app):
    """Flask 앱에 전달 페이지 라우트 등록"""

    @app.route('/p/<token>', methods=['GET', 'POST'])
    def apex_delivery(token):
        d = db.get_delivery(token)
        if not d:
            abort(404)

        unlocked = session.get('dl_' + token) is True
        err, shake = None, False
        if request.method == 'POST':
            pin = (request.form.get('pin') or '').strip()
            if pin and pin == str(d.get('pin')):
                session['dl_' + token] = True
                unlocked = True
            else:
                err = 'PIN이 올바르지 않습니다. 다시 확인해주세요.'
                shake = True

        info, cookie = split_delivery(d.get('content') or '')
        return render_template_string(
            TEMPLATE, css=CSS, d=d, token=token, unlocked=unlocked, err=err,
            shake=shake, info=info, cookie=cookie,
            has_file=bool(d.get('file_data')),
            created=str(d.get('created_at') or '')[:16],
        )

    @app.route('/p/<token>/file')
    def apex_delivery_file(token):
        if not session.get('dl_' + token):
            abort(403)
        got = db.get_delivery_file(token)
        if not got:
            abort(404)
        name, data = got
        return send_file(io.BytesIO(data), as_attachment=True, download_name=name)

