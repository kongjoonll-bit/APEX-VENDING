"""Apex Vending — 쿠키 사용법 페이지 (/guide)

구매자가 쿠키를 적용하는 방법(PC/모바일)을 안내한다.
"""
from flask import render_template_string

CSS = """
:root{--bg:#06080d;--card:#0f1621;--card2:#0b1119;--line:#1d2a3a;--txt:#eef4fb;--sub:#8ea1b8;
--gold:#e0b64a;--gold2:#f7dc94;--green:#31d07b;--red:#ef4444;--amber:#f59e0b}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--bg);color:var(--txt);overflow-x:hidden;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
.bg{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none}
.blob{position:absolute;border-radius:50%;filter:blur(90px);opacity:.45;animation:float 20s ease-in-out infinite}
.b1{width:520px;height:520px;left:-150px;top:-170px;background:radial-gradient(circle,#e0b64a55,transparent 65%)}
.b2{width:460px;height:460px;right:-130px;top:12%;background:radial-gradient(circle,#2f6dff44,transparent 65%);animation-delay:-7s}
.b3{width:500px;height:500px;left:25%;bottom:-230px;background:radial-gradient(circle,#31d07b30,transparent 65%);animation-delay:-12s}
@keyframes float{0%,100%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(0,-34px,0) scale(1.06)}}
.grid{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.32;
background-image:linear-gradient(rgba(255,255,255,.026) 1px,transparent 1px),
linear-gradient(90deg,rgba(255,255,255,.026) 1px,transparent 1px);
background-size:44px 44px;mask-image:radial-gradient(circle at 50% 16%,#000 30%,transparent 78%)}
.wrap{position:relative;z-index:2;max-width:880px;margin:0 auto;padding:26px 16px 80px}
.brand{display:flex;align-items:center;gap:10px;font-size:12.5px;letter-spacing:.26em;
color:var(--gold2);font-weight:800;margin-bottom:18px;animation:rise .7s cubic-bezier(.2,.8,.2,1) both}
.brand .dot{width:8px;height:8px;border-radius:50%;background:var(--gold);box-shadow:0 0 14px var(--gold)}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
.hero{position:relative;border-radius:24px;border:1px solid var(--line);padding:24px;
background:linear-gradient(160deg,rgba(224,182,74,.09),rgba(15,22,33,.96) 42%,var(--card2));
box-shadow:0 34px 80px -40px rgba(0,0,0,.95),inset 0 1px 0 rgba(255,255,255,.05);
animation:rise .8s .04s cubic-bezier(.2,.8,.2,1) both;margin-bottom:16px}
.hero h1{font-size:25px;margin:0 0 8px;letter-spacing:-.02em}
.hero p{margin:0;color:var(--sub);font-size:13.5px;line-height:1.7}
.card{border-radius:20px;border:1px solid var(--line);background:rgba(15,22,33,.72);padding:20px;
margin-bottom:14px;animation:rise .8s .08s cubic-bezier(.2,.8,.2,1) both}
.card h2{display:flex;align-items:center;gap:9px;font-size:16px;margin:0 0 14px;letter-spacing:-.01em}
.card h2:before{content:'';width:3px;height:15px;border-radius:2px;background:var(--gold)}
.warn{border-radius:18px;padding:18px;margin-bottom:14px;border:1px solid rgba(245,158,11,.42);
background:linear-gradient(140deg,rgba(245,158,11,.16),rgba(239,68,68,.1) 60%,rgba(15,22,33,.9));
animation:rise .8s .06s cubic-bezier(.2,.8,.2,1) both}
.warn .wt{display:flex;align-items:center;gap:8px;font-size:15.5px;font-weight:900;color:#ffd79a;margin-bottom:10px}
.warn p{margin:0 0 8px;font-size:13.5px;line-height:1.75;color:#ffe9c9}
.warn b{color:#fff}
.steps{display:flex;flex-direction:column;gap:11px}
.step{display:flex;gap:13px;align-items:flex-start;padding:13px 15px;border-radius:14px;
border:1px solid var(--line);background:rgba(255,255,255,.025)}
.num{width:28px;height:28px;flex:0 0 auto;border-radius:9px;display:grid;place-items:center;
font-size:13px;font-weight:900;color:#20180a;background:linear-gradient(135deg,var(--gold2),var(--gold))}
.step .tx{font-size:13.5px;line-height:1.7;color:#dbe6f3;min-width:0}
.step .tx b{color:#fff}
.lnk{color:var(--gold2);text-decoration:none;border-bottom:1px dashed rgba(224,182,74,.5);word-break:break-all}
.lnk:hover{color:#fff;border-bottom-color:#fff}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:12px 18px;border-radius:13px;
font-weight:800;font-size:13.5px;text-decoration:none;transition:transform .16s,filter .16s}
.btn:active{transform:scale(.98)}
.btn.gold{color:#20180a;background:linear-gradient(135deg,var(--gold2),var(--gold));
box-shadow:0 14px 30px -16px rgba(224,182,74,.95)}
.btn.gold:hover{filter:brightness(1.07)}
.btn.red{color:#2a0b0b;background:linear-gradient(135deg,#fca5a5,#ef4444);
box-shadow:0 14px 30px -16px rgba(239,68,68,.9)}
.btn.ghost{color:var(--txt);background:rgba(255,255,255,.06);border:1px solid var(--line)}
.btn.ghost:hover{background:rgba(255,255,255,.12)}
.note{font-size:12.5px;color:var(--sub);line-height:1.8;margin-top:12px}
.note b{color:#fff}
.vid{display:flex;align-items:center;gap:12px;padding:14px;border-radius:14px;margin-top:12px;
border:1px solid rgba(224,182,74,.3);background:linear-gradient(120deg,rgba(224,182,74,.12),rgba(15,22,33,.85));
text-decoration:none;color:var(--txt)}
.vid .play{width:38px;height:38px;border-radius:12px;display:grid;place-items:center;flex:0 0 auto;
background:linear-gradient(135deg,var(--gold2),var(--gold));color:#20180a;font-size:15px}
.vid .vt{font-size:13.5px;font-weight:800}
.vid .vs{font-size:11.5px;color:var(--sub);margin-top:3px}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;background:rgba(255,255,255,.06);
padding:2px 6px;border-radius:6px;color:var(--gold2)}
.foot{margin-top:18px;text-align:center;font-size:11.5px;color:#5b6b80;line-height:1.9}
@media(max-width:640px){
 .wrap{padding:16px 12px 70px}
 .hero{padding:18px;border-radius:20px}
 .hero h1{font-size:21px}
 .card{padding:16px;border-radius:17px}
 .step{padding:11px 12px;gap:10px}
 .step .tx{font-size:13px}
 .btn{width:100%;justify-content:center}
}
"""

TEMPLATE = """<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>쿠키 사용법 · APEX VENDING</title>
<style>{{ css }}</style></head><body>
<div class="bg"><div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div></div>
<div class="grid"></div>
<div class="wrap">
  <div class="brand"><span class="dot"></span>APEX VENDING · GUIDE</div>

  <div class="hero">
    <h1>🍪 쿠키 사용법 🍪</h1>
    <p>구매하신 쿠키를 PC·모바일에서 적용하는 방법입니다. 순서대로만 따라 하시면 됩니다.</p>
  </div>

  <div class="warn">
    <div class="wt">⚠️ 중요사항 · IP락 해제</div>
    <p>모든 쿠키는 <b>구매 후 IP락을 해제</b>하셔야 터지지 않습니다.</p>
    <p>IP락 해제 사이트에서 쿠키를 입력하고 <b>BYPASS</b>를 누른 뒤, <b>새로 나온 키를 복사</b>해서 사용하세요.
       (모바일은 아래 영상 참고)</p>
    <p style="color:#ffb4b4"><b>IP락을 풀지 않아 터진 쿠키는 보상이 어렵습니다.</b></p>
    <div class="btns">
      <a class="btn red" href="https://rblxrefresh.net/" target="_blank" rel="noopener">🔓 IP락 해제 사이트 열기</a>
    </div>
  </div>

  <div class="card">
    <h2>📢 PC · Multiroblox로 로그인하는 방법</h2>
    <div class="steps">
      <div class="step"><div class="num">1</div><div class="tx"><b>크롬 브라우저 열기</b><br>컴퓨터에서 구글 크롬을 실행합니다.</div></div>
      <div class="step"><div class="num">2</div><div class="tx"><b>확장 프로그램 설치</b><br>
        Multiroblox 설치 :
        <a class="lnk" href="https://chromewebstore.google.com/detail/multiroblox/clfgjcjkakdagopdhcgloklhakklhkol?hl=ko-kr" target="_blank" rel="noopener">Chrome 웹스토어 링크</a>
        → 설치합니다.</div></div>
      <div class="step"><div class="num">3</div><div class="tx"><b>쿠키 입력하기</b><br>
        프로그램을 열고 <span class="mono">Enter your cookie here</span> 칸에 쿠키를 붙여넣습니다.<br>
        쿠키는 <b><span class="mono">_|WARNING</span> 부터 끝까지</b> 모두 복사하세요.</div></div>
      <div class="step"><div class="num">4</div><div class="tx"><b>캐릭터 클릭</b><br>입력한 쿠키의 캐릭터를 클릭합니다.</div></div>
      <div class="step"><div class="num">5</div><div class="tx"><b>로블록스 사이트 접속</b><br>
        <a class="lnk" href="https://www.roblox.com/ko" target="_blank" rel="noopener">roblox.com/ko</a> 에 들어가면 <b>자동 로그인</b> 완료 🎉</div></div>
    </div>
    <a class="vid" href="https://www.youtube.com/watch?v=YlV4XQFRooQ" target="_blank" rel="noopener">
      <span class="play">▶</span>
      <span><span class="vt">PC 예시 영상 보기</span><span class="vs">YouTube · 클릭하면 재생됩니다</span></span>
    </a>
    <div class="note">💡 정리 : 크롬 열기 → 확장 설치 → 쿠키 입력 → 캐릭터 클릭 → 로블 접속</div>
  </div>

  <div class="card">
    <h2>📱 휴대폰 · Roblox 쿠키 적용 방법</h2>
    <div class="steps">
      <div class="step"><div class="num">1</div><div class="tx"><b>파이어폭스(Firefox) 앱 다운로드</b><br>확장 프로그램을 설치할 수 있는 브라우저입니다.</div></div>
      <div class="step"><div class="num">2</div><div class="tx"><b>Cookies Editor 추가</b><br>아래 링크에서 확장 프로그램을 설치하세요.</div></div>
      <div class="step"><div class="num">3</div><div class="tx"><b>roblox.com</b> 주소창에 입력 후 접속</div></div>
      <div class="step"><div class="num">4</div><div class="tx">오른쪽 상단 <b>점 3개</b> 메뉴 → <b>확장 프로그램</b> → <b>Cookies Editor</b> 실행</div></div>
      <div class="step"><div class="num">5</div><div class="tx"><b>roblox security</b> 관련 기존 쿠키를 모두 삭제</div></div>
      <div class="step"><div class="num">6</div><div class="tx">받은 쿠키를 붙여넣고 <b>✅ (초록 체크)</b> 로 저장</div></div>
      <div class="step"><div class="num">7</div><div class="tx">Roblox 페이지 <b>새로고침</b> → 적용 완료</div></div>
    </div>
    <div class="btns">
      <a class="btn gold" href="https://addons.mozilla.org/ko/firefox/addon/cookie-editor/" target="_blank" rel="noopener">🧩 Cookies Editor 다운로드</a>
    </div>
    <a class="vid" href="https://drive.google.com/file/d/1EgiZm7SIpsimsdFaxfWnc1vKyG6vlKuS/view?usp=drivesdk" target="_blank" rel="noopener">
      <span class="play">▶</span>
      <span><span class="vt">모바일 예시 영상 보기</span><span class="vs">Google Drive · 클릭하면 재생됩니다</span></span>
    </a>
    <div class="note">
      · <b>갤럭시 버전</b>에서 올바른 쿠키라면 새로고침하면 바로 로그인됩니다.<br>
      · <b>아무 계정이나 로그인된 상태</b>에서 영상대로 진행하세요.
    </div>
  </div>

  <div class="card">
    <h2>🆘 사용법이 어려우면</h2>
    <div class="note">디스코드 자판기에서 <b>불량교환</b> 버튼으로 <b>#문의하기</b> 티켓을 열어주세요.
      스크린샷을 함께 남겨주시면 훨씬 빠르게 도와드립니다.</div>
  </div>

  <div class="foot">APEX VENDING · 쿠키는 본인만 사용하세요.</div>
</div>
</body></html>"""


def register(app):
    @app.route('/guide')
    def apex_guide():
        return render_template_string(TEMPLATE, css=CSS)

