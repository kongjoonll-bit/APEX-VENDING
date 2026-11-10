# -*- coding: utf-8 -*-
"""구매 완료 / 고객 후기 카드 PNG 렌더러 (Pillow + Pretendard)

Apex Vending 전용으로 이식한 카드 생성기.
- 얇은 테두리 카드 + 상단 옅은 하이라이트
- 좌측 상단 로고 칩(이니셜) + 우측 상태 필
- 금액·상품이 나란히 들어간 히어로 패널
- 얇은 구분선 테이블 + 하단 푸터

Pillow/폰트가 없으면 None 을 돌려주고 호출쪽에서 임베드로 폴백한다.
폰트는 최초 1회 자동 다운로드 후 data/fonts 에 캐시한다.
"""
import io
import math
import os
import re
import threading

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except Exception as _e:  # pragma: no cover
    _PIL_OK = False
    print(f"[card] Pillow 사용 불가: {_e}")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

W = 1200
MARGIN = 34
PAD = 46
CARD_TOP = 28
RADIUS = 24

CARD_BG = (16, 19, 25)
CARD_EDGE = (33, 39, 50)
PANEL_BG = (24, 29, 38)
TXT = (238, 242, 249)
MUTED = (136, 147, 163)
LINE = (32, 38, 48)
SOFT = (206, 214, 226)
STAR = (250, 206, 92)

ACCENT_DEFAULT = (58, 214, 165)   # 민트
REVIEW_ACCENT = (242, 193, 78)    # 앰버

_BASE = "https://raw.githubusercontent.com/orioncactus/pretendard/main/packages/pretendard/dist/public/static/"
_NANUM = "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/"

_FONT_SOURCES = {
    "regular": [("Pretendard-Regular.otf", _BASE + "Pretendard-Regular.otf"),
                ("NanumGothic-Regular.ttf", _NANUM + "NanumGothic-Regular.ttf")],
    "semibold": [("Pretendard-SemiBold.otf", _BASE + "Pretendard-SemiBold.otf"),
                 ("NanumGothic-Bold.ttf", _NANUM + "NanumGothic-Bold.ttf")],
    "bold": [("Pretendard-Bold.otf", _BASE + "Pretendard-Bold.otf"),
             ("NanumGothic-Bold.ttf", _NANUM + "NanumGothic-Bold.ttf")],
    "extra": [("Pretendard-ExtraBold.otf", _BASE + "Pretendard-ExtraBold.otf"),
              ("NanumGothic-Bold.ttf", _NANUM + "NanumGothic-Bold.ttf")],
}

# 시스템에 이미 있는 한글 폰트 (오프라인/다운로드 실패 대비)
_SYSTEM_FONTS = {
    "regular": [
        r"C:\Windows\Fonts\malgun.ttf",
        r"C:\Windows\Fonts\NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ],
    "bold": [
        r"C:\Windows\Fonts\malgunbd.ttf",
        r"C:\Windows\Fonts\NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ],
}

_DL_LOCK = threading.Lock()
_FONT_CACHE = {}
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE00-\uFE0F\u200D\u20E3"
    "\U0001F1E6-\U0001F1FF]")


def _font_dir():
    d = os.path.join(DATA_DIR, 'fonts')
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _download(url, dest):
    try:
        import requests
        r = requests.get(url, timeout=30)
        if r.status_code != 200 or len(r.content) < 5000:
            print(f"[card] font download failed ({r.status_code}) {url}")
            return False
        tmp = dest + ".tmp"
        with open(tmp, "wb") as f:
            f.write(r.content)
        os.replace(tmp, dest)
        return True
    except Exception as e:
        print(f"[card] font download error {url}: {e}")
        return False


def _system_font(weight):
    for p in _SYSTEM_FONTS.get(weight) or _SYSTEM_FONTS.get('regular'):
        try:
            if os.path.exists(p):
                return p
        except Exception:
            continue
    return None


def font_path(weight="regular"):
    alts = _FONT_SOURCES.get(weight) or _FONT_SOURCES["regular"]
    d = _font_dir()
    for name, url in alts:
        p = os.path.join(d, name)
        if os.path.exists(p) and os.path.getsize(p) > 5000:
            return p
        with _DL_LOCK:
            if os.path.exists(p) and os.path.getsize(p) > 5000:
                return p
            if _download(url, p):
                return p
    return _system_font(weight)


def font(weight, size):
    key = (weight, size)
    f = _FONT_CACHE.get(key)
    if f is not None:
        return f
    if not _PIL_OK:
        return None
    p = font_path(weight)
    if not p:
        return None
    try:
        f = ImageFont.truetype(p, size)
    except Exception as e:
        print(f"[card] font load failed: {e}")
        return None
    _FONT_CACHE[key] = f
    return f


def available():
    return _PIL_OK and font("bold", 22) is not None


def clean(text, limit=None):
    t = str(text or "")
    t = _EMOJI_RE.sub("", t).replace("\u200b", "")
    t = re.sub(r"[ \t]+", " ", t).strip()
    if limit and len(t) > limit:
        t = t[: max(0, limit - 1)] + "…"
    return t


def parse_color(value, default=ACCENT_DEFAULT):
    s = str(value or "").strip().lstrip("#")
    if len(s) == 6:
        try:
            return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            pass
    return default


def _lerp(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _star(d, cx, cy, r, color=STAR):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=color)


def _wrap(d, text, f, max_w):
    out = []
    for para in str(text).split("\n"):
        if para == "":
            out.append("")
            continue
        cur = ""
        for ch in para:
            if d.textlength(cur + ch, font=f) <= max_w:
                cur += ch
            else:
                out.append(cur)
                cur = ch
        out.append(cur)
    return out


def _card_bg(img, height, acc):
    from PIL import ImageChops
    box = [MARGIN, CARD_TOP, W - MARGIN, height - CARD_TOP]
    card = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle(box, radius=RADIUS, fill=CARD_BG + (255,))
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=RADIUS, fill=255)

    fade = 170
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for yy in range(box[1], min(box[1] + fade, box[3])):
        t = (yy - box[1]) / fade
        a = int(46 * ((1 - t) ** 1.6))
        if a <= 0:
            continue
        gd.line([(0, yy), (W, yy)], fill=acc + (a,))
    glow.putalpha(ImageChops.multiply(glow.getchannel("A"), mask))
    card = Image.alpha_composite(card, glow)
    img.alpha_composite(card)
    ImageDraw.Draw(img).rounded_rectangle(box, radius=RADIUS, outline=CARD_EDGE + (255,), width=1)


def _draw(d, spec, top, acc=ACCENT_DEFAULT):
    x0 = MARGIN + PAD
    x1 = W - MARGIN - PAD
    y = top

    # 헤더 : 로고 칩 + 브랜드 + 상태 필
    brand = clean(spec.get("brand") or "", 26) or "Apex Bot"
    ls = 40
    d.rounded_rectangle([x0, y - 4, x0 + ls, y + ls - 4], radius=12,
                        fill=_lerp(PANEL_BG, acc, 0.20))
    d.rounded_rectangle([x0, y - 4, x0 + ls, y + ls - 4], radius=12, outline=acc, width=1)
    letter = brand[:1].upper()
    if letter:
        d.text((x0 + ls / 2, y + ls / 2 - 4), letter, font=font("extra", 19),
               fill=acc, anchor="mm")
    d.text((x0 + ls + 14, y + 2), brand, font=font("bold", 25), fill=TXT)

    status = clean(spec.get("status") or "", 16)
    if status:
        fs = font("semibold", 17)
        tw = d.textlength(status, font=fs)
        pw = tw + 44
        px0 = x1 - pw
        d.rounded_rectangle([px0, y - 4, x1, y + 32], radius=18, fill=_lerp(PANEL_BG, acc, 0.16))
        d.ellipse([px0 + 16, y + 11, px0 + 24, y + 19], fill=acc)
        d.text((px0 + 32, y + 3), status, font=fs, fill=acc)
    y += ls + 30

    # 제목 / 부제
    title = clean(spec.get("title") or "", 24)
    if title:
        d.text((x0, y), title, font=font("extra", 50), fill=TXT)
        y += 62
    sub = clean(spec.get("subtitle") or "", 64)
    if sub:
        d.text((x0, y), sub, font=font("regular", 21), fill=MUTED)
        y += 32
    y += 24

    # 히어로 패널 (금액 + 상품 정보)
    hero = spec.get("hero") or {}
    if hero:
        h = 110
        d.rounded_rectangle([x0, y, x1, y + h], radius=18, fill=PANEL_BG)
        d.rounded_rectangle([x0, y + 18, x0 + 4, y + h - 18], radius=2, fill=acc)
        d.text((x0 + 26, y + 18), clean(hero.get("label") or "결제 금액", 18),
               font=font("regular", 18), fill=MUTED)
        value = clean(hero.get("value") or "", 22)
        fv = font("extra", 44)
        d.text((x0 + 26, y + 44), value, font=fv, fill=acc)
        stars = int(hero.get("stars") or 0)
        if stars:
            vw = d.textlength(value, font=fv)
            sx = x0 + 26 + vw + 22
            for i in range(max(1, min(5, stars))):
                _star(d, sx + i * 26, y + 66, 10)
        rt = clean(hero.get("right_title") or "", 26)
        rs = clean(hero.get("right_sub") or "", 40)
        if rt:
            d.text((x1 - 26, y + 26), rt, font=font("bold", 23), fill=TXT, anchor="ra")
        if rs:
            d.text((x1 - 26, y + 64), rs, font=font("regular", 18), fill=MUTED, anchor="ra")
        y += h + 26

    # 항목 테이블 (얇은 구분선)
    rows = spec.get("rows") or []
    if rows:
        fl = font("regular", 21)
        fvb = font("bold", 21)
        for i, (label, value) in enumerate(rows):
            label = clean(label, 22)
            value = clean(value, 42)
            ty = y + 12
            d.text((x0, ty), label, font=fl, fill=MUTED)
            d.text((x1, ty), value, font=fvb, fill=TXT, anchor="ra")
            y += 46
            if i < len(rows) - 1:
                d.line([(x0, y), (x1, y)], fill=LINE, width=1)
            y += 1
        y += 14

    # 본문 (후기)
    body = spec.get("body") or ""
    if body:
        fbd = font("regular", 21)
        lines = _wrap(d, clean(body, 1300), fbd, x1 - x0)
        if len(lines) > 14:
            lines = lines[:14]
            lines[-1] = lines[-1] + " …"
        y += 6
        for ln in lines:
            d.text((x0, y), ln, font=fbd, fill=SOFT)
            y += 33
        y += 6

    # 하단
    if spec.get("footer_left") or spec.get("footer_right"):
        y += 18
        d.line([(x0, y), (x1, y)], fill=LINE, width=1)
        y += 24
        ff = font("regular", 18)
        d.text((x0, y), clean(spec.get("footer_left") or "", 60), font=ff, fill=MUTED)
        d.text((x1, y), clean(spec.get("footer_right") or "", 40), font=ff, fill=MUTED, anchor="ra")
        y += 22
    return y


def render_card(spec):
    """spec -> PNG bytes (실패 시 None)."""
    if not available():
        return None
    spec = spec or {}
    acc = parse_color(spec.get("accent"), ACCENT_DEFAULT)
    try:
        probe = Image.new("RGBA", (W, 6200), (0, 0, 0, 0))
        y_end = _draw(ImageDraw.Draw(probe), spec, CARD_TOP + 50, acc)
        height = int(y_end + 40 + CARD_TOP)
        img = Image.new("RGBA", (W, height), (0, 0, 0, 0))
        _card_bg(img, height, acc)
        _draw(ImageDraw.Draw(img), spec, CARD_TOP + 50, acc)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"[card] render failed: {e}")
        return None


# ============ 카드 스펙 빌더 (Apex Vending) ============
def won(value):
    try:
        return f"{int(value):,}원"
    except Exception:
        return str(value)


def now_text():
    """KST 기준 표시용 시각 문자열"""
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y. %m. %d. %H:%M")


def purchase_ref(order_id, user_id=""):
    """카드에 표시할 구매 ID (주문번호 기반 고정 해시)"""
    import hashlib
    raw = f"{order_id}:{user_id}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:20]


def purchase_spec(brand, product, category, amount, buyer,
                  quantity=1, discount=0, order_id="", user_id="",
                  purchase_id=None, at=None, description=""):
    """구매 완료 카드 스펙"""
    category = (str(category or "").strip() or "기타")
    product = str(product or "상품")
    quantity = max(1, int(quantity or 1))
    try:
        amount = int(amount or 0)
    except Exception:
        amount = 0
    try:
        discount = max(0, int(discount or 0))
    except Exception:
        discount = 0
    purchase_id = purchase_id or purchase_ref(order_id, user_id)
    desc = " ".join(str(description or "").split())
    rows = [
        ("구매자", str(buyer or "구매자")),
        ("카테고리", category),
        ("상품", product),
    ]
    if desc:
        rows.append(("설명", desc))
    rows.extend([
        ("갯수", f"{quantity}개"),
        ("할인", f"-{discount:,}원" if discount else "없음"),
    ])
    return {
        "brand": brand,
        "status": "결제 완료",
        "title": "구매 완료",
        "subtitle": "구매가 정상적으로 완료되었습니다",
        "accent": "#3AD6A5",
        "hero": {
            "label": "결제 금액",
            "value": won(amount),
            "right_title": product,
            "right_sub": f"{category} · {quantity}개",
        },
        "rows": rows,
        "footer_left": f"구매 ID {purchase_id}",
        "footer_right": at or now_text(),
    }


def review_spec(brand, user, product, category, stars, ticket_no, text, at=None):
    """고객 후기 카드 스펙"""
    try:
        stars = max(1, min(5, int(stars or 5)))
    except Exception:
        stars = 5
    category = (str(category or "").strip() or "기타")
    product = str(product or "상품")
    return {
        "brand": brand,
        "status": "후기 등록",
        "title": "고객 후기",
        "subtitle": f"{user} 님이 남긴 후기",
        "accent": "#F2C14E",
        "hero": {
            "label": "별점",
            "value": f"{stars}.0",
            "stars": stars,
            "right_title": product,
            "right_sub": category,
        },
        "rows": [
            ("작성자", str(user or "-")),
            ("카테고리", category),
            ("상품", product),
            ("티켓", f"#{ticket_no}"),
        ],
        "body": str(text or ""),
        "footer_left": f"{brand} · 후기",
        "footer_right": at or now_text(),
    }


def render_stock_board(brand, items, at=None, out_size=1600):
    """재고 보드 전용 렌더러 — 1600x1600 정사각, 2배 슈퍼샘플링(3200→1600)으로 고품질"""
    if not available():
        return None
    items = items or []
    S = 2
    CANVAS = out_size * S
    BG = (10, 14, 20)
    CARD = (19, 25, 34)
    ROW = (25, 32, 42)
    EDGE = (40, 50, 64)
    TXT = (242, 246, 252)
    SUB = (158, 170, 186)
    GREEN = (46, 204, 113)
    PAL = [(88, 166, 255), (46, 204, 113), (241, 196, 15), (167, 139, 250), (255, 138, 128)]

    def F(w, s):
        return font(w, int(s * S))

    groups = {}
    for it in items:
        groups.setdefault((it.get("category") or "기타"), []).append(it)
    for k in groups:
        groups[k].sort(key=lambda x: (-int(x.get("stock") or 0), str(x.get("name"))))
    cats = list(groups.keys())
    total_stock = sum(int(i.get("stock") or 0) for i in items)
    total_rows = sum(len(v) for v in groups.values())

    img = Image.new("RGB", (CANVAS, CANVAS), BG)
    d = ImageDraw.Draw(img)

    def rr(box, **kw):
        d.rounded_rectangle([int(v * S) for v in box], **kw)

    def tx(xy, s, f, fill, anchor=None):
        d.text((int(xy[0] * S), int(xy[1] * S)), s, font=f, fill=fill, anchor=anchor)

    # 바깥 프레임
    rr([40, 40, out_size - 40, out_size - 40], radius=34, fill=CARD, outline=EDGE, width=2 * S)

    # 헤더
    rr([80, 80, 168, 168], radius=22, fill=(31, 42, 54), outline=GREEN, width=2 * S)
    tx((124, 124), (brand or "A")[:1].upper(), F("extra", 46), GREEN, anchor="mm")
    tx((192, 88), brand or "APEX VENDING", F("bold", 42), TXT)
    tx((192, 142), "지금 바로 구매 가능한 상품", F("regular", 27), SUB)

    tx((80, 216), "재고 현황", F("extra", 88), TXT)

    # 요약 박스 2개
    stats = (("판매 가능 상품", f"{len(items)}개", GREEN), ("총 재고 수량", f"{total_stock}개", PAL[0]))
    for i, (label, value, color) in enumerate(stats):
        bx = 80 + i * 372
        rr([bx, 356, bx + 352, 462], radius=18, fill=ROW, outline=(52, 64, 80), width=1 * S)
        tx((bx + 24, 372), label, F("regular", 26), SUB)
        tx((bx + 24, 404), value, F("extra", 46), color)

    # 본문 영역
    top, bottom = 520, 1490
    avail = bottom - top
    sec_h = 86
    row_h = 78
    if total_rows:
        row_h = min(92, max(48, (avail - len(cats) * sec_h) // total_rows))
    content_h = len(cats) * sec_h + total_rows * row_h
    y = top + max(0, (avail - content_h) // 2)

    if not cats:
        rr([80, top + 60, out_size - 80, top + 200], radius=18, fill=ROW)
        tx((112, top + 110), "현재 재고가 없습니다 · 입고를 기다려 주세요", F("bold", 36), SUB)

    for idx, cat in enumerate(cats):
        acc = PAL[idx % len(PAL)]
        rr([80, y + 8, 92, y + 66], radius=6, fill=acc)
        tx((108, y + 8), cat, F("bold", 42), acc)
        tx((out_size - 80, y + 18), f"{len(groups[cat])}개 상품", F("regular", 27), SUB, anchor="ra")
        y += sec_h
        for i, it in enumerate(groups[cat]):
            if i % 2 == 0:
                rr([80, y - 12, out_size - 80, y + row_h - 18], radius=14, fill=ROW)
            name = str(it.get("name"))[:34]
            tx((104, y + 2), name, F("semibold", 37), TXT)
            tx((out_size - 300, y + 4), f"{int(it.get('price') or 0):,}원", F("regular", 34), SUB, anchor="ra")
            rr([out_size - 272, y - 6, out_size - 96, y + row_h - 30], radius=24, fill=(23, 52, 40), outline=acc, width=2 * S)
            tx((out_size - 184, y + (row_h - 36) / 2), f"{int(it.get('stock') or 0)}개", F("bold", 32), acc, anchor="mm")
            y += row_h
        y += 22

    # 푸터
    d.line([(int(80 * S), int(1508 * S)), (int((out_size - 80) * S), int(1508 * S))], fill=EDGE, width=2 * S)
    tx((80, 1528), f"{brand} · 재고 보드 · 30분마다 자동 갱신", F("regular", 26), SUB)
    tx((out_size - 80, 1528), at or now_text(), F("regular", 26), SUB, anchor="ra")

    img = img.resize((out_size, out_size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def stock_board_spec(brand, items, total_products=0, at=None):
    """재고 보드 카드 스펙 — 재고가 있는 상품만 한눈에 보기 좋게 정렬"""
    items = items or []
    total_stock = sum(int(i.get("stock") or 0) for i in items)
    # 재고 많은 순 → 카테고리 → 이름
    ordered = sorted(
        items,
        key=lambda i: (-int(i.get("stock") or 0), str(i.get("category") or ""), str(i.get("name") or ""))
    )
    rows = []
    for it in ordered[:18]:
        name = clean(it.get("name") or "상품", 22)
        price = won(it.get("price") or 0)
        rows.append((name, f"{price}  ·  {int(it.get('stock') or 0)}개"))
    if len(ordered) > 18:
        rows.append(("외 %d개 상품" % (len(ordered) - 18), "재고 있음"))

    stamp = at or now_text()
    return {
        "brand": brand,
        "status": "판매 가능",
        "title": "재고 현황",
        "subtitle": f"지금 바로 구매 가능한 {len(items)}개 상품",
        "accent": "#2ECC71",
        "hero": {
            "label": "재고 보유 상품",
            "value": f"{len(items)}개",
            "right_title": f"{total_stock}개",
            "right_sub": "총 재고 수량",
        },
        "rows": rows if rows else [("재고 없음", "입고 대기중")],
        "footer_left": f"{brand} · 재고 보드 (30분마다 갱신)",
        "footer_right": stamp,
    }


def stock_spec(brand, product, category, price, added, total_stock, at=None, description=""):
    """재고 입고 알림 카드 스펙 (입고 채널용)"""
    product = str(product or "상품")
    category = (str(category or "").strip() or "기타")
    try:
        price = int(price or 0)
    except Exception:
        price = 0
    try:
        added = int(added or 0)
    except Exception:
        added = 0
    try:
        total_stock = int(total_stock or 0)
    except Exception:
        total_stock = 0
    desc = " ".join(str(description or "").split())
    stamp = at or now_text()
    return {
        "brand": brand,
        "status": "입고 완료",
        "title": "재고 입고",
        "subtitle": f"{clean(product, 36)} 재고가 도착했습니다",
        "accent": "#2ECC71",
        "hero": {
            "label": "입고 수량",
            "value": f"+{added}개",
            "right_title": won(price),
            "right_sub": "상품 가격",
        },
        "rows": [
            ("상품", product),
            ("카테고리", category),
            ("현재 재고", f"{total_stock}개"),
            ("입고 시각", stamp),
        ],
        "body": desc,
        "footer_left": f"{brand} · 재고 알림",
        "footer_right": stamp,
    }


