from datetime import datetime
import discord
from discord import ui
from discord.ext import commands
from discord import app_commands
import asyncio
import hashlib
import io
import logging
import os
import re
import threading
import time

import database as db
import card_render as cards
import roblox_cookie as cookie_util

logger = logging.getLogger(__name__)

BOT_VERSION = 'v1.0'  # APEX VENDING 리브랜드 (랭킹/출석 제거 + UI 전면 리디자인)

# ============ APEX VENDING BRAND SYSTEM ============
BOT_NAME = 'APEX VENDING'
BRAND_TAGLINE = 'PREMIUM DIGITAL KEY STORE'
BRAND_FOOTER = 'APEX VENDING · 24/7 AUTO DISPENSER'

COLOR_MAIN = 0xF0B429     # Apex Gold  - 기본 강조색
COLOR_INFO = 0x5AA9FF     # Apex Blue
COLOR_SUCCESS = 0x3DDC97  # Apex Mint
COLOR_ERROR = 0xFF5C6C    # Apex Coral
COLOR_WARN = 0xFFA726     # Apex Amber
COLOR_DARK = 0x1B2130     # Apex Graphite

_PALETTE = {
    'main': COLOR_MAIN,
    'info': COLOR_INFO,
    'success': COLOR_SUCCESS,
    'error': COLOR_ERROR,
    'warn': COLOR_WARN,
    'dark': COLOR_DARK,
}


def brand_color(kind='main'):
    '''Apex Vending 브랜드 색상 반환'''
    return discord.Color(_PALETTE.get(kind, COLOR_MAIN))


def brand_embed(title, description=None, kind='main', footer=None):
    '''브랜드 색상 + 푸터가 자동 적용된 임베드 생성'''
    embed = discord.Embed(
        title=title,
        description=description,
        color=brand_color(kind),
    )
    embed.set_footer(text='%s · %s' % (BOT_NAME, footer) if footer else BRAND_FOOTER)
    return embed


def brand_tag(text):
    '''푸터/문구용 브랜드 접두어'''
    return '%s · %s' % (BOT_NAME, text)


# 판매 가능한 재고가 없을 때 안내 (만료/검사 대기 구분)
NO_STOCK_TEXT = (
    "지금 구매 가능한 재고가 없습니다.\n"
    "-# 만료된 쿠키이거나 유효성 검사 중일 수 있습니다. 잠시 후 다시 시도해주세요."
)


def product_desc(product, limit=90):
    '''상품 설명을 한 줄로 정리 (없으면 빈 문자열)'''
    if not product:
        return ''
    text = str(product.get('description') or '').strip()
    text = ' '.join(text.split())
    if not text:
        return ''
    return text[:limit] + ('…' if len(text) > limit else '')


# ============ 재고 전달 (텍스트 키 / 파일) ============
MAX_KEY_FILE_BYTES = 8 * 1024 * 1024  # 재고 파일 1개 최대 8MB


# ============ 버튼 아이콘 (커스텀 이미지 이모지) ============
# assets/icons/*.png 를 봇 시작 시 애플리케이션 이모지로 업로드해서 버튼에 사용한다.
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'icons')
EMOJI_ASSETS = {
    'cart': 'cart.png',    # 구매
    'box': 'box.png',      # 제품
    'card': 'card.png',    # 충전
    'info': 'info.png',    # 정보
    'mail': 'mail.png',    # 문의
    'refund': 'refund.png'  # 환불
}


def app_emoji(key):
    '''버튼용 커스텀 이모지 (아직 업로드되지 않았으면 None)'''
    name = 'apex_' + key
    raw = str(db.get_setting('emoji_' + name, '') or '').strip()
    if not raw.isdigit():
        return None
    return discord.PartialEmoji(name=name, id=int(raw))


def _env_flag(name, default=False):
    '''환경변수 boolean 플래그'''
    raw = os.environ.get(name, '')
    if not str(raw).strip():
        return default
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on', 'y')


def human_size(num):
    '''바이트 → 사람이 읽기 쉬운 크기 문자열'''
    try:
        num = int(num or 0)
    except (TypeError, ValueError):
        return '0 B'
    if num >= 1024 * 1024:
        return '%.1f MB' % (num / (1024 * 1024))
    if num >= 1024:
        return '%.1f KB' % (num / 1024)
    return '%d B' % num


def now_iso_utc():
    '''현재 시각 (UTC ISO 문자열)'''
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _parse_utc(value):
    '''ISO 문자열 → timezone aware datetime (실패 시 None)'''
    from datetime import datetime, timezone
    if not value:
        return None
    raw = str(value).strip()
    try:
        if raw.endswith('Z'):
            raw = raw[:-1]
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def relative_time_text(value):
    '''ISO 시각 → "18초 전 / 3분 전 / 2시간 전" 형태 (텍스트)'''
    from datetime import datetime, timezone
    dt = _parse_utc(value)
    if dt is None:
        return '기록 없음'
    seconds = int(max(0, (datetime.now(timezone.utc) - dt).total_seconds()))
    if seconds < 60:
        return '%d초 전' % seconds
    if seconds < 3600:
        return '%d분 전' % (seconds // 60)
    if seconds < 86400:
        return '%d시간 전' % (seconds // 3600)
    return '%d일 전' % (seconds // 86400)


def discord_ts(value, style='R'):
    '''ISO 시각 → Discord 동적 타임스탬프

    <t:...:R> 은 디스코드 클라이언트가 1초마다 "18초 전" 처럼 자동 갱신하고,
    마우스를 올리면 사용자 로컬 시간대(예: KST)로 정확히 표시한다.
    '''
    dt = _parse_utc(value)
    if dt is None:
        return None
    return '<t:%d:%s>' % (int(dt.timestamp()), style)


def build_key_attachment(key):
    '''재고(키)에 첨부된 파일을 discord.File 로 변환 (파일 재고가 아니면 None)'''
    if not key:
        return None
    data = key.get('file_data')
    if not data:
        return None
    name = (key.get('file_name') or '').strip() or 'APEX-%s.txt' % key.get('id', 'file')
    return discord.File(io.BytesIO(bytes(data)), filename=name)


def add_key_fields_to_embed(embed, key):
    '''임베드에 전달 내용(텍스트 키 또는 파일) 필드 추가 → discord.File 반환'''
    key_file = build_key_attachment(key)
    if key_file:
        embed.add_field(
            name="전달 파일",
            value=f"`{key.get('file_name') or 'file'}` · {human_size(key.get('file_size'))}",
            inline=False
        )
        if (key.get('key_value') or '').strip():
            embed.add_field(name="KEY", value=f"```\n{key['key_value']}\n```", inline=False)
        return key_file
    embed.add_field(name="YOUR KEY", value=f"```\n{key.get('key_value') or ''}\n```", inline=False)
    return None


# ============ 카드 이미지 (구매 완료 / 고객 후기) ============
def card_image_enabled():
    '''구매·후기 카드 이미지 사용 여부 (대시보드/DB 설정, 기본 사용)'''
    return str(db.get_setting('card_image_enabled', 'true')).strip().lower() != 'false'


async def render_purchase_card(product_name, category, amount, buyer, order_id, user_id,
                               discount=0, description=''):
    '''구매 완료 카드 PNG bytes (실패 시 None → 임베드 폴백)'''
    if not card_image_enabled():
        return None
    try:
        spec = cards.purchase_spec(
            brand=BOT_NAME,
            product=product_name,
            category=category,
            amount=amount,
            buyer=buyer,
            quantity=1,
            discount=discount,
            order_id=order_id,
            user_id=user_id,
            description=description,
        )
        return await asyncio.to_thread(cards.render_card, spec)
    except Exception as e:
        logger.warning(f"[카드] 구매 카드 렌더 실패: {e}")
        return None


async def render_review_card(user_name, product_name, category, stars, ticket_no, text):
    '''고객 후기 카드 PNG bytes (실패 시 None → 임베드 폴백)'''
    if not card_image_enabled():
        return None
    try:
        spec = cards.review_spec(
            brand=BOT_NAME,
            user=user_name,
            product=product_name,
            category=category,
            stars=stars,
            ticket_no=ticket_no,
            text=text,
        )
        return await asyncio.to_thread(cards.render_card, spec)
    except Exception as e:
        logger.warning(f"[카드] 후기 카드 렌더 실패: {e}")
        return None


def _vending_content_signature():
    """자판기 메시지 내용이 실제로 바뀌었는지 판별하는 서명 생성

    레이트리밋(429) 예방 핵심: 상품/재고/설정이 안 바뀌었으면
    Discord API 호출(fetch+edit) 자체를 생략한다.
    """
    parts = []
    for key in ('vending_title', 'vending_desc', 'vending_footer', 'vending_footer_channel_id',
                'vending_color', 'vending_banner_url', 'use_categories', 'cookie_last_check_at'):
        parts.append(f"{key}={db.get_setting(key, '')}")
    for p in db.get_products(active_only=True):
        parts.append(
            f"p={p['id']}|{p['name']}|{p['price']}|{p.get('category', '')}|{db.count_available_keys(p['id'])}"
        )
    for cat in db.get_categories():
        parts.append(f"c={cat}|{len(db.get_products_by_category(cat, active_only=True))}")
    cookie_stats = db.count_cookie_status()
    parts.append('ck=%s|%s|%s|%s' % (cookie_stats['total'], cookie_stats['valid'],
                                     cookie_stats['invalid'], cookie_stats['sellable']))
    # 버튼 아이콘(커스텀 이모지) ID — 업로드/변경 시 패널 갱신
    parts.append('emoji=' + ','.join(
        str(db.get_setting('emoji_apex_' + k, '')) for k in ('cart', 'card', 'info', 'mail')
    ))
    # UI 포맷 버전 (렌더링 방식이 바뀌면 1회 강제 갱신)
    parts.append('ui=2')
    raw = '||'.join(parts)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def _message_has_vending_components(msg):
    """메시지에 자판기 전용 버튼(vending_products)이 포함되어 있는지 재귀 검사"""
    if not getattr(msg, 'components', None):
        return False
    stack = list(msg.components)
    while stack:
        comp = stack.pop()
        cid = getattr(comp, 'custom_id', None)
        if cid == 'vending_products':
            return True
        children = getattr(comp, 'children', None)
        if children:
            stack.extend(children)
    return False

class VendingBot(commands.Bot):
    def __init__(self):
        # 특권 인텐트(Message Content / Members)는 기본적으로 사용하지 않는다.
        # → Discord 개발자 포털에서 아무것도 켜지 않아도 바로 동작.
        #   (필요하면 환경변수로 켤 수 있음: ENABLE_MESSAGE_CONTENT_INTENT=true / ENABLE_MEMBERS_INTENT=true)
        intents = discord.Intents.default()
        intents.message_content = _env_flag('ENABLE_MESSAGE_CONTENT_INTENT')
        intents.members = _env_flag('ENABLE_MEMBERS_INTENT')
        super().__init__(command_prefix='!', intents=intents)
        self.deposit_callback = None
        self.ready_event = asyncio.Event()
        self.vending_messages = {}
        # ---- 레이트리밋(429) 방지 상태 ----
        self._rate_limited_until = 0.0        # time.monotonic() 기준 전역 429 블록 해제 시각
        self._rate_limit_streak = 0            # 연속 429 횟수 (백오프 지수 증가용)
        self._channel_cache = {}               # 채널 객체 캐시 (fetch_channel 호출 최소화)
        self._refresh_lock = asyncio.Lock()   # 자판기 새로고침 중복 실행 방지
        self._refresh_tick = 0                # 주기적 메시지 실존 확인용 카운터

    def _clear_rate_limit(self):
        """정상 응답을 받으면 백오프 단계 초기화"""
        if time.monotonic() >= self._rate_limited_until:
            self._rate_limit_streak = 0

    def _is_rate_limited(self):
        """Discord API 전역 레이트리밋(429) 백오프 중인지 여부"""
        return time.monotonic() < self._rate_limited_until

    def _note_rate_limit(self, err):
        """429 응답 기록 - 지정 시간 동안 Discord API 요청을 멈춘다 (악순환 차단)

        - 일반 429: retry_after 기반
        - Cloudflare 1015(IP 차단): HTML 응답이라 retry_after 가 없으므로 2분부터
          지수적으로 늘려 최대 30분까지 차단한다.
        """
        text = str(err)
        cf_block = ('1015' in text) or ('Cloudflare' in text) or ('Access denied' in text)

        retry_after = 10.0  # 최소 10초 백오프
        exc_retry = getattr(err, 'retry_after', None)
        if exc_retry:
            try:
                retry_after = max(retry_after, float(exc_retry) + 1.0)
            except (TypeError, ValueError):
                pass
        else:
            # 예외 메시지에서 retry_after 값 파싱 (버전별 호환)
            m = re.search(r'retry_after["\s:]+([\d.]+)', text)
            if m:
                try:
                    retry_after = max(retry_after, float(m.group(1)) + 1.0)
                except (TypeError, ValueError):
                    pass

        # 연속 429 → 지수 백오프 (최대 30분)
        self._rate_limit_streak = getattr(self, '_rate_limit_streak', 0) + 1
        if cf_block:
            retry_after = max(retry_after, 120.0)
        retry_after = min(1800.0, retry_after * (2 ** (self._rate_limit_streak - 1)))

        self._rate_limited_until = max(self._rate_limited_until, time.monotonic() + retry_after)
        return retry_after
    
    async def setup_hook(self):
        self.bot_loop = asyncio.get_running_loop()
        await self.add_cog(VendingCommands(self))
        # 앱 커맨드 전역 에러 핸들러 등록
        # → 배포 겹침(구/신 인스턴스 동시 접속)이나 중복 실행 시 발생하는
        #   NotFound(10062, Unknown interaction)가 트레이스백으로 터지지 않게 한다.
        self.tree.on_error = self.on_app_command_error
        # 커맨드 구성이 바뀌지 않았다면 sync 를 건너뛴다 (부팅 시 API 호출 절감 → 429 예방)
        try:
            import time as _t
            last_sync = float(db.get_setting('last_tree_sync', '0') or 0)
            if _t.time() - last_sync > 300:
                await self.tree.sync()
                db.set_setting('last_tree_sync', str(int(_t.time())))
                logger.info("[SYNC] 슬래시 커맨드 동기화 완료")
            else:
                logger.info("[SYNC] 최근 6시간 내 동기화됨 - 생략 (API 호출 절감)")
        except Exception as e:
            logger.warning(f"[SYNC] 동기화 확인 실패, 강제 동기화: {e}")
            try:
                await self.tree.sync()
            except Exception:
                pass
        logger.info(f"========== 봇 버전 {BOT_VERSION} 로드 완료 (자판기 오류 수정본 배포 확인용) ==========")

    async def on_app_command_error(self, interaction: discord.Interaction, error):
        """앱 슬래시 커맨드 전역 에러 처리"""
        original = getattr(error, 'original', error)
        cmd = getattr(getattr(interaction, 'command', None), 'qualified_name', '?')
        # 10062: 이미 만료/소비된 상호작용 (다른 인스턴스가 먼저 응답한 경우)
        if isinstance(original, discord.NotFound) and getattr(original, 'code', None) == 10062:
            logger.warning(f"[CMD] /{cmd} - 상호작용 만료(10062). 다른 인스턴스(로컬/이전 배포)가 먼저 응답했을 수 있습니다.")
            return
        if isinstance(original, discord.NotFound):
            logger.warning(f"[CMD] /{cmd} - 대상 없음(404): {original}")
            return
        logger.error(f"[CMD] /{cmd} 처리 중 오류: {original!r}")
    
    async def on_ready(self):
        logger.info(f"Bot logged in as {self.user} (ID: {self.user.id})")
        try:
            db.set_setting('bot_heartbeat', str(int(time.time())))
            self.bot_loop = asyncio.get_running_loop()
        except Exception:
            pass
        self.ready_event.set()
        await self.change_presence(activity=discord.Game(name=f"{BOT_NAME} | v{BOT_VERSION}"))
        await self.restore_vending_machines()
        # 5분 핑 자동 전송 시작 (중복 방지)
        if not getattr(self, '_ping_task_started', False):
            self._ping_task_started = True
            self.loop.create_task(self.ping_loop())
        # 자동 충전 리마인더 루프 시작 (중복 방지)
        if not getattr(self, '_reminder_task_started', False):
            self._reminder_task_started = True
            self.loop.create_task(self.charge_reminder_loop())
        # 카드 렌더러 사전 준비 (첫 구매 시 폰트 다운로드 지연 방지)
        if not getattr(self, '_card_warm_started', False):
            self._card_warm_started = True
            self.loop.create_task(self._warm_card_fonts())
        # 로블록스 쿠키 자동 검사 루프 (기본 3분 간격)
        if not getattr(self, '_cookie_task_started', False):
            self._cookie_task_started = True
            self.loop.create_task(self.cookie_check_loop())
        # 재고 보드 30분 주기 갱신
        if not getattr(self, '_stock_board_started', False):
            self._stock_board_started = True
            self.loop.create_task(self.stock_board_loop())
        # 버튼 아이콘(애플리케이션 이모지) 동기화
        if not getattr(self, '_emoji_sync_started', False):
            self._emoji_sync_started = True
            self.loop.create_task(self.sync_app_emojis())

    async def _warm_card_fonts(self):
        """구매/후기 카드용 폰트를 백그라운드에서 미리 준비"""
        try:
            ok = await asyncio.to_thread(cards.available)
            logger.info(f"[카드] 렌더러 준비 완료: {ok}")
        except Exception as e:
            logger.warning(f"[카드] 렌더러 준비 실패: {e}")

    # ============ 버튼 아이콘 (커스텀 이미지 이모지) ============
    async def sync_app_emojis(self):
        """assets/icons/*.png 를 애플리케이션 이모지로 업로드하고 ID를 DB에 저장

        이미 업로드된 이모지는 재사용한다. 실패하면 아이콘 없이(텍스트만) 동작한다.
        """
        try:
            emojis = await self.fetch_application_emojis()
        except Exception as e:
            logger.warning(f"[이모지] 애플리케이션 이모지 조회 실패: {e}")
            return

        existing = {getattr(e, 'name', ''): e for e in emojis}
        changed = False
        for key, filename in EMOJI_ASSETS.items():
            name = 'apex_' + key
            emoji = existing.get(name)
            if emoji is None:
                path = os.path.join(ICON_DIR, filename)
                if not os.path.exists(path):
                    continue
                try:
                    with open(path, 'rb') as f:
                        data = f.read()
                    emoji = await self.create_application_emoji(name=name, image=data)
                    logger.info(f"[이모지] 업로드: {name} (id={emoji.id})")
                except Exception as e:
                    logger.warning(f"[이모지] 업로드 실패 {name}: {e}")
                    continue
            if str(db.get_setting('emoji_' + name, '')) != str(emoji.id):
                db.set_setting('emoji_' + name, str(emoji.id))
                changed = True

        if changed:
            logger.info("[이모지] 버튼 아이콘 동기화 완료 - 자판기 패널 갱신")
            try:
                await self.refresh_vending_machines(force_edit=True)
            except Exception as e:
                logger.warning(f"[이모지] 패널 갱신 실패: {e}")

    # ============ 로블록스 쿠키 유효성 자동 검사 ============
    def _cookie_check_enabled(self):
        """쿠키 자동 검사 사용 여부"""
        return str(db.get_setting('cookie_check_enabled', 'true')).strip().lower() != 'false'

    def _cookie_check_interval_seconds(self):
        """검사 주기(초) - 기본 3분 (DB 설정 cookie_check_minutes)"""
        try:
            minutes = float(str(db.get_setting('cookie_check_minutes', '3')).strip() or 3)
        except (TypeError, ValueError):
            minutes = 3.0
        minutes = max(1.0, min(minutes, 1440.0))
        return minutes * 60

    def _cookie_check_batch(self):
        try:
            n = int(str(db.get_setting('cookie_check_batch', '60')).strip() or 60)
        except (TypeError, ValueError):
            n = 60
        return max(1, min(n, 200))

    async def cookie_check_loop(self):
        """설정 주기(기본 3분)마다 파일 재고의 로블록스 쿠키를 검사"""
        await asyncio.sleep(20)  # 봇 초기화 여유
        logger.info("[쿠키검사] 자동 검사 루프 시작")
        while True:
            try:
                if self.is_ready() and self._cookie_check_enabled():
                    await self.check_all_cookies()
            except Exception as e:
                logger.error(f"[쿠키검사] 루프 오류: {e}")
            await asyncio.sleep(self._cookie_check_interval_seconds())

    async def check_all_cookies(self, limit=None):
        """미사용 파일 재고의 쿠키 유효성 검사 → 결과 요약 dict"""
        limit = limit or self._cookie_check_batch()
        items = db.get_unused_file_keys(limit=limit)
        stats = {'total': len(items), 'checked': 0, 'valid': 0, 'invalid': 0,
                 'unknown': 0, 'newly_invalid': []}
        if not items:
            return stats

        for item in items:
            raw = item.get('file_data')
            try:
                text = bytes(raw).decode('utf-8', 'ignore') if raw else ''
            except Exception:
                text = ''

            cookie_value = cookie_util.extract_cookie(text)
            if not cookie_value:
                # 쿠키 상품이 아니면 상태만 기록 (판매에는 영향 없음)
                db.set_key_cookie_status(item['id'], None, error='쿠키 없음', not_cookie=True)
                stats['unknown'] += 1
                continue

            result = await asyncio.to_thread(cookie_util.check_cookie, cookie_value)
            valid = result.get('valid')
            db.set_key_cookie_status(
                item['id'],
                valid,
                username=result.get('username', ''),
                user_id=result.get('user_id', ''),
                error=result.get('error', ''),
                # 판단 불가(네트워크 오류)면 검사시각을 갱신하지 않아
                # 일정 시간 뒤 자동으로 판매 보류된다.
                touch_time=(valid is not None),
            )
            stats['checked'] += 1

            if valid is True:
                stats['valid'] += 1
            elif valid is False:
                stats['invalid'] += 1
                if not item.get('invalid'):
                    stats['newly_invalid'].append({
                        'id': item['id'],
                        'product_id': item['product_id'],
                        'file_name': item.get('file_name') or '',
                        'username': result.get('username') or '',
                        'error': result.get('error') or '',
                    })
            else:
                stats['unknown'] += 1

            await asyncio.sleep(0.7)  # Roblox 요청 간격 (레이트리밋 보호)

        # 마지막 검사 시각 기록 (자판기 패널의 "쿠키 검사 N초 전" 표시용)
        db.set_setting('cookie_last_check_at', now_iso_utc())

        if stats['newly_invalid']:
            logger.warning(f"[쿠키검사] 무효 쿠키 {len(stats['newly_invalid'])}개 감지 → 판매 제외")
            await self.alert_invalid_cookies(stats['newly_invalid'])
        else:
            logger.info(
                f"[쿠키검사] 완료 · 검사 {stats['checked']} / 유효 {stats['valid']} / "
                f"무효 {stats['invalid']} / 판단불가 {stats['unknown']}"
            )

        # 자판기 패널의 검사 시각/수량 표시 갱신
        try:
            await self.refresh_vending_machines()
        except Exception as e:
            logger.error(f"[쿠키검사] 자판기 새로고침 실패: {e}")
        return stats

    async def get_admin_alert_channel(self):
        """관리자 알림 채널 (admin → purchase log → charge log 순)"""
        for key in ('admin_channel_id', 'purchase_log_channel_id', 'charge_log_channel_id'):
            cid = db.get_setting(key, '')
            if not cid:
                continue
            try:
                channel = self.get_channel(int(cid)) or await self.fetch_channel(int(cid))
                if channel:
                    return channel
            except Exception:
                continue
        return None

    async def alert_invalid_cookies(self, items):
        """무효 쿠키를 관리자 채널로 알림"""
        channel = await self.get_admin_alert_channel()
        if not channel:
            logger.warning("[쿠키검사] 관리자 알림 채널이 없어 알림을 건너뜁니다.")
            return

        lines = []
        for it in items[:12]:
            name = it.get('username') or '계정 확인 불가'
            lines.append(
                f"· `#{it['id']}` `{it.get('file_name') or 'file'}` — **{name}**\n"
                f"-# {it.get('error') or '쿠키 무효'}"
            )
        embed = discord.Embed(
            title="무효 쿠키 감지",
            description=(
                "자동 검사에서 **사용할 수 없는 로블록스 쿠키**가 발견되어 판매 목록에서 제외했습니다.\n\n"
                + "\n".join(lines)
            ),
            color=brand_color('error')
        )
        if len(items) > 12:
            embed.add_field(name="추가", value=f"외 {len(items) - 12}개", inline=False)
        embed.set_footer(text=brand_tag('COOKIE CHECK'))
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"[쿠키검사] 알림 전송 실패: {e}")
    
    async def refresh_stock_board(self):
        """재고 채널에 '재고 있는 상품 전체' 보드 이미지를 게시/갱신"""
        channel_id = (db.get_setting('stock_channel_id', '') or '').strip()
        if not channel_id:
            return
        if self._is_rate_limited():
            logger.warning("[재고보드] 레이트리밋 백오프 중 - 스킵")
            return
        try:
            channel = self.get_channel(int(channel_id)) or await self.fetch_channel(int(channel_id))
            if not channel:
                logger.warning(f"[재고보드] 채널 없음: {channel_id}")
                return

            items = []
            for p in db.get_products(active_only=True):
                stock = db.count_listable_keys(p['id'])
                if stock > 0:
                    items.append({
                        'name': p['name'], 'price': p['price'],
                        'stock': stock, 'category': p.get('category') or ''
                    })

            if not cards.available():
                return
            spec = cards.stock_board_spec(BOT_NAME, items, len(db.get_products(active_only=True)))
            png = cards.render_card(spec)
            if not png:
                return
            file = discord.File(io.BytesIO(png), filename='stock_board.png')

            # 텍스트(임베드)로도 읽기 쉽게 정리 — 이미지 + 목록 동시에 제공
            ordered = sorted(
                items,
                key=lambda i: (-int(i['stock']), str(i.get('category') or ''), str(i['name']))
            )
            lines = []
            for i in ordered[:40]:
                cat = f"[{i['category']}] " if i.get('category') else ''
                lines.append(f"▸ {cat}**{i['name']}** · {int(i['price']):,}원 · 재고 **{i['stock']}개**")
            if len(ordered) > 40:
                lines.append(f"-# 외 {len(ordered) - 40}개 상품")
            total_stock = sum(int(i['stock']) for i in items)
            desc = (
                f"**지금 구매 가능한 상품 {len(items)}개 · 총 재고 {total_stock}개**\n"
                + ("\n".join(lines) if lines else "현재 재고가 없습니다. 입고를 기다려 주세요.")
            )

            embed = discord.Embed(
                title="재고 현황",
                description=desc[:4000],
                color=brand_color('success'),
                timestamp=discord.utils.utcnow()
            )
            embed.set_image(url='attachment://stock_board.png')
            embed.set_footer(text="APEX VENDING · 재고 보드 (30분마다 자동 갱신)")

            msg_id = db.get_setting('stock_board_message_id', '')
            if msg_id:
                try:
                    msg = await channel.fetch_message(int(msg_id))
                    await msg.edit(embed=embed, attachments=[file])
                    logger.info(f"[재고보드] 갱신 완료 ({len(items)}개 상품)")
                    return
                except discord.NotFound:
                    pass
                except discord.HTTPException as e:
                    if e.status == 429:
                        self._note_rate_limit(e)
                        return
                    logger.warning(f"[재고보드] 수정 실패, 새로 전송: {e}")

            new_msg = await channel.send(embed=embed, file=file)
            db.set_setting('stock_board_message_id', str(new_msg.id))
            logger.info(f"[재고보드] 게시 완료 ({len(items)}개 상품)")
        except discord.HTTPException as e:
            if e.status == 429:
                self._note_rate_limit(e)
            logger.warning(f"[재고보드] 실패: {e}")
        except Exception as e:
            logger.warning(f"[재고보드] 실패: {e}")

    async def stock_board_loop(self):
        """30분마다 재고 보드 갱신"""
        logger.info("[재고보드] 30분 주기 갱신 시작")
        while True:
            try:
                if self.is_ready():
                    await self.refresh_stock_board()
            except Exception as e:
                logger.warning(f"[재고보드] 루프 오류: {e}")
            await asyncio.sleep(1800)

    async def ping_loop(self):
        """5분마다 대시보드/자판기 핑 자동 전송 (비블로킹)

        부팅 직후 self-ping 은 워커 준비 전이라 타임아웃되기 쉬우므로
        첫 핑은 60초 뒤에 보내고 타임아웃을 30초로 넉넉히 준다.
        """
        await asyncio.sleep(60)
        ping_fails = 0
        while True:
            sleep_for = 300
            try:
                # 핑 URL: 설정값 우선, 없으면 Render 외부 URL(RENDER_EXTERNAL_URL) 자동 사용
                ping_url = db.get_setting('dashboard_url', '') or os.environ.get('RENDER_EXTERNAL_URL', '')
                if ping_url:
                    ping_url = ping_url.strip().rstrip('/')
                    # 설정에 /dashboard 경로가 포함돼 있으면 제거 (→ /ping 404 방지)
                    if ping_url.endswith('/dashboard'):
                        ping_url = ping_url[:-len('/dashboard')]

                    def _do_ping(url=ping_url):
                        import requests as _req
                        try:
                            resp = _req.get(url + '/ping', timeout=10)
                            return resp.status_code
                        except Exception as e:
                            return e

                    status = await self.loop.run_in_executor(None, _do_ping)
                    if isinstance(status, int):
                        logger.info(f"[PING] {ping_url} -> {status} (5분 후 재전송)")
                        ping_fails = 0
                    else:
                        # 자기 공개 URL 접속 실패 → 로그 폭주 방지 (3회까지만 경고, 이후 30분 간격)
                        ping_fails += 1
                        if ping_fails < 3:
                            logger.warning(f"[PING] error: {status}")
                        elif ping_fails == 3:
                            logger.warning(
                                "[PING] 자기 URL 접속이 계속 실패합니다(렌더 라우팅 문제 가능). "
                                "자동 핑을 30분 간격으로 줄입니다. "
                                f"(마지막 오류: {status})"
                            )
                            sleep_for = 1800
                        else:
                            sleep_for = 1800

                # 자판기 새로고침 (재고/상품 상태 최신화)
                await self.refresh_vending_machines()
                logger.info("[PING] Vending machines refreshed")
            except Exception as e:
                logger.error(f"[PING] Error: {e}")
            await asyncio.sleep(sleep_for)  # 정상 5분 / 연속 실패 시 30분

    async def charge_reminder_loop(self):
        """30초마다 확인 - 충전 신청 후 3분이 지나도 자동 충전이 안 된 요청에 리마인더 DM 발송"""
        logger.info("[충전리마인더] 루프 시작 (3분 무충전 시 DM 알림)")
        while True:
            try:
                try:
                    db.set_setting('bot_heartbeat', str(int(time.time())))
                except Exception:
                    pass
                if self.is_ready():
                    await self._process_charge_reminders()
            except Exception as e:
                logger.error(f"[충전리마인더] 루프 오류: {e}")
            await asyncio.sleep(30)

    async def _process_charge_reminders(self):
        """3분 경과한 대기 충전 요청에 리마인더 DM 발송 (발송 완료 표시로 중복 방지)"""
        # 유효 시간(만료 분) 가져오기 (대시보드 설정값, 기본 30분)
        try:
            expire_minutes = int(str(db.get_setting('charge_expire_minutes', '')).strip() or 30)
        except (TypeError, ValueError):
            expire_minutes = 30
        expire_minutes = max(1, min(expire_minutes, 1440))

        rows = db.get_charge_requests_needing_reminder(minutes=3, expire_minutes=expire_minutes)
        if not rows:
            return

        for req in rows:
            # 먼저 발송 표시 (DM 실패해도 무한 재시도 방지)
            db.mark_charge_reminder_sent(req['id'])

            # 발송 직전 상태 재확인 - 그 사이 자동 충전/취소됐으면 스킵
            latest = db.get_charge_request(req['id'])
            if not latest or latest['status'] != 'pending':
                logger.info(f"[충전리마인더] #{req['id']} 이미 처리됨({latest['status'] if latest else '삭제됨'}) → 스킵")
                continue

            try:
                user = await self.fetch_user(int(latest['user_id']))
                if not user:
                    logger.warning(f"[충전리마인더] #{latest['id']} 유저를 찾을 수 없음 ({latest['user_id']})")
                    continue

                bank_account = db.get_setting('bank_account', '미설정')
                bank_holder = db.get_setting('bank_holder', '미설정')
                bank_name = db.get_setting('bank_name', '')

                embed = discord.Embed(
                    title="아직 자동 충전이 확인되지 않았어요!",
                    description=(
                        f"충전 신청 후 **3분**이 지났지만 자동 충전이 되지 않았습니다.\n\n"
                        f"**입금하셨다면**\n"
                        f"입금 완료 사진(스크린샷)을 **이 DM에 사진으로 보내주세요!**\n"
                        f"관리자가 확인 후 승인하면 포인트가 충전됩니다.\n\n"
                        f"**아직 입금 전이라면**\n"
                        f"**{bank_name} {bank_account} ({bank_holder})** 로 입금해주세요.\n"
                        f"입금하면 토스 알림 감지 후 **자동으로 충전**됩니다!"
                    ),
                    color=brand_color('warn')
                )
                embed.add_field(name="요청번호", value=f"#{latest['id']}", inline=True)
                embed.add_field(name="▸ 입금자명", value=latest['depositor_name'], inline=True)
                embed.add_field(name="▸ 충전 금액", value=f"{latest['amount']:,}원 → {latest['amount']:,}포인트", inline=True)
                embed.add_field(name="만료", value=f"이 요청은 신청 후 {expire_minutes}분 뒤 만료됩니다.", inline=False)
                embed.set_footer(text=brand_tag('CHARGE'))

                await user.send(embed=embed)
                logger.info(f"[충전리마인더] #{latest['id']} 리마인더 DM 발송 완료 ({latest['username']})")
            except discord.Forbidden:
                logger.warning(f"[충전리마인더] #{latest['id']} DM 차단으로 발송 실패 (유저: {latest['username']})")
            except Exception as e:
                logger.error(f"[충전리마인더] #{latest['id']} DM 발송 오류: {e}")

    async def on_message(self, message):
        """메시지 처리 - 리뷰는 임베드 버튼(모달)로만 작성 + DM 입금 증거 스크린샷 접수"""
        if message.author.bot:
            return

        # DM에서 이미지 첨부가 오면 = 입금 증거 스크린샷으로 처리
        if isinstance(message.channel, discord.DMChannel) and message.attachments:
            await self.handle_charge_receipt_dm(message)
            return

        # 일반 메시지 처리 (DM 포함 - 일반 채팅은 리뷰로 등록하지 않음)
        await self.process_commands(message)

    async def get_charge_log_channel(self):
        """충전로그 채널 반환 (설정 키: charge_log_channel_id → 없으면 deposit_log_channel_id → admin_channel_id)"""
        cid = (db.get_setting('charge_log_channel_id', '')
               or db.get_setting('deposit_log_channel_id', '')
               or db.get_setting('admin_channel_id', ''))
        if not cid:
            return None, "충전로그 채널이 설정되지 않았습니다.\n대시보드 설정에서 **충전로그 채널 ID**를 저장하세요."
        try:
            channel = self.get_channel(int(cid))
            if not channel:
                channel = await self.fetch_channel(int(cid))
            return channel, None
        except Exception as e:
            return None, f"충전로그 채널을 찾을 수 없습니다: {e}"

    async def handle_charge_receipt_dm(self, message):
        """유저가 DM으로 보낸 입금 증거 스크린샷을 충전로그에 등록하고 관리자에게 알림"""
        # 이미 자동 충전이 완료된 경우 → 사진 접수 차단
        recent = db.get_user_charge_requests(message.author.id, limit=1)
        if recent and recent[0]['status'] == 'completed':
            await message.channel.send(
                "**이미 자동 충전이 완료되었습니다!**\n"
                "입금이 정상 확인되어 포인트가 지급되었으니 사진을 보내실 필요 없습니다 "
            )
            return

        # 대기 중인 충전 요청 확인
        pending = db.get_pending_charge_requests_by_user(message.author.id)
        if not pending:
            await message.channel.send(
                "대기 중인 충전 신청이 없습니다.\n"
                "자판기에서 **충전** → **충전 신청**을 먼저 진행해주세요!"
            )
            return

        req = pending[0]  # 가장 오래된 대기 요청
        if req['receipt_image_url']:
            await message.channel.send("이 충전 신청에는 이미 입금 증거가 접수되어 관리자 확인 중입니다.")
            return

        # 첨부 이미지가 실제 이미지인지 확인
        attachment = message.attachments[0]
        if not (attachment.content_type or '').startswith('image/'):
            await message.channel.send("이미지 파일(스크린샷)로 보내주세요!")
            return

        # 증거 이미지 URL 저장
        db.set_charge_receipt_image(req['id'], attachment.url)
        await message.channel.send("입금 증거 스크린샷이 접수되었습니다! 관리자가 확인 후 승인하면 포인트가 충전됩니다 ")

        # 충전로그 채널에 게시
        channel, err = await self.get_charge_log_channel()
        if not channel:
            logger.error(f"[충전로그] {err}")
            return

        # 관리자 멘션 만들기
        admins = db.get_admins()
        mention_text = " ".join(f"<@{a['user_id']}>" for a in admins) if admins else "@관리자"

        embed = discord.Embed(
            title="충전 승인 요청",
            description=f"**{req['username']}** 님의 충전 신청입니다.",
            color=brand_color('success')
        )
        embed.add_field(name="요청번호", value=f"#{req['id']}", inline=True)
        embed.add_field(name="▸ 입금자명", value=req['depositor_name'], inline=True)
        embed.add_field(name="▸ 충전 금액", value=f"{req['amount']:,}원 → {req['amount']:,}포인트", inline=True)
        embed.add_field(name="신청일", value=req['created_at'], inline=False)
        embed.set_image(url=attachment.url)
        embed.set_footer(text="아래 버튼으로 승인/거절해주세요")

        view = ChargeApproveView(req['id'])
        await channel.send(content=f"{mention_text} 충전 승인 대기!", embed=embed, view=view)
        logger.info(f"[충전로그] #{req['id']} 증거 스크린샷 게시 + 관리자 멘션")

    async def post_review(self, user, order_id, product_name, rating, content):
        """리뷰를 리뷰 채널에 임베드로 게시 (구매당 1개만 작성 가능)"""
        try:
            # 구매당 1개 제한: 해당 주문이 이미 후기를 작성했는지 확인
            reviewed = db.order_is_reviewed(order_id)
            if reviewed is None:
                return False, "주문 정보를 찾을 수 없습니다."
            if reviewed:
                return False, "이 구매건은 이미 후기를 작성하셨습니다.\n후기는 구매당 1개만 작성 가능합니다 "

            review_channel_id = db.get_setting('review_channel_id', '')
            if not review_channel_id:
                return False, "리뷰 채널이 설정되지 않았습니다. 관리자에게 문의해주세요."
            
            try:
                review_channel = self.get_channel(int(review_channel_id))
                if not review_channel:
                    review_channel = await self.fetch_channel(int(review_channel_id))
            except discord.NotFound:
                return False, f"리뷰 채널(ID: {review_channel_id})을 찾을 수 없습니다. 관리자에게 문의해주세요."
            
            if not review_channel:
                return False, "리뷰 채널을 찾을 수 없습니다. 관리자에게 문의해주세요."
            
            stars = '' * int(rating) + '' * (5 - int(rating))

            # 상품 카테고리 (카드 표시용)
            category = ''
            try:
                order_row = db.get_order(order_id) or {}
                if order_row.get('product_id'):
                    prod = db.get_product(order_row['product_id']) or {}
                    category = prod.get('category') or ''
            except Exception:
                category = ''

            card_png = await render_review_card(
                user.display_name, product_name, category, int(rating), order_id, content
            )
            if card_png:
                card_embed = discord.Embed(color=discord.Color(0xF2C14E))
                card_embed.set_image(url='attachment://review.png')
                card_embed.set_footer(text=brand_tag('REVIEW'))
                await review_channel.send(
                    embed=card_embed,
                    file=discord.File(io.BytesIO(card_png), filename='review.png')
                )
            else:
                embed = discord.Embed(
                    title="구매 후기",
                    description=content,
                    color=brand_color('main')
                )
                embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
                embed.add_field(name="별점", value=stars, inline=True)
                embed.add_field(name="상품", value=product_name, inline=True)
                embed.add_field(name="주문번호", value=f"#{order_id}", inline=True)
                embed.set_footer(text=brand_tag('REVIEW'))

                await review_channel.send(embed=embed)
            
            # 후기 작성 완료 처리 (구매당 1개 제한)
            db.mark_order_reviewed(order_id)
            
            logger.info(f"Review registered from {user} for order #{order_id} ({rating} stars)")
            return True, "후기가 등록되었습니다!"
        except Exception as e:
            logger.error(f"Post review error: {e}")
            return False, f"후기 등록 실패: {str(e)}"
    
    async def restore_vending_machines(self):
        """봇 시작 시 자판기 메시지 복원 - 레이트리밋 안전하게 채널별 간격"""
        channels = db.get_vending_channels()
        for i, ch in enumerate(channels):
            result = "skip"
            try:
                channel = self.get_channel(int(ch['channel_id']))
                if channel:
                    result = await self.update_vending_machine(channel)
                    if result == "updated":
                        logger.info(f"Vending machine restored in channel {ch['channel_id']}")
                    elif result == "rate_limited":
                        logger.warning("[VENDING] restore 중단: 전역 레이트리밋(429) 백오프 시작")
                        break
            except Exception as e:
                logger.error(f"Restore vending machine error: {e}")
            if result == "updated" and i < len(channels) - 1:
                await asyncio.sleep(1.0)  # 실제 갱신했을 때만 간격 (시작 시 버스트 방지)

    async def update_vending_machine(self, channel, force_edit=False, verify=False):
        """자판기 메시지 갱신 - 429 레이트리밋에 안전한 로직

        핵심 변경:
        - 내용이 안 바뀌었으면 API 호출 자체를 생략 (레이트리밋 예방)
        - 429 발생 시 즉시 재전송하지 않고 백오프 (악순환 차단)
        - 메시지가 실제로 삭제된 경우(NotFound)에만 새로 전송
        """
        if self._is_rate_limited():
            logger.warning(f"[VENDING] update 스킵: 채널 {channel.id} - 전역 레이트리밋(429) 백오프 중")
            return "rate_limited"

        # 내용 변경 여부 먼저 판별 - 안 바뀌었으면 뷰 생성/API 호출 전부 생략
        content_hash = _vending_content_signature()
        existing = db.get_vending_message(channel.id)
        msg = None
        hash_unchanged = bool(
            content_hash and not force_edit
            and existing and existing.get('content_hash') == content_hash
        )

        if existing and hash_unchanged and not verify:
            return "skip"  # 내용 동일 + 실존 확인 불필요 → Discord API 호출 없음

        view = VendingMainView()

        if existing:
            try:
                msg = await channel.fetch_message(int(existing['message_id']))
            except discord.Forbidden:
                raise  # 권한 오류는 상위(설치 명령어)에서 사용자 안내하도록 전파
            except discord.NotFound:
                msg = None  # 삭제된 메시지 → 아래에서 새로 전송
                logger.info(f"[VENDING] 저장된 자판기 메시지가 삭제됨 (채널 {channel.id}) - 재설치 진행")
            except discord.HTTPException as e:
                if e.status == 429:
                    retry = self._note_rate_limit(e)
                    logger.warning(f"[VENDING] fetch 레이트리밋(429) 채널 {channel.id}: {e} (백오프 {retry}초)")
                else:
                    logger.warning(f"[VENDING] fetch 실패 채널 {channel.id}: {e}")
                return "rate_limited" if e.status == 429 else "failed"
            except Exception as e:
                logger.warning(f"[VENDING] fetch 실패 채널 {channel.id}: {e}")
                return "failed"
            if hash_unchanged and msg is not None:
                return "skip"  # verify 모드: 실존 확인만 하고 내용이 같으면 edit 생략
        else:
            # DB 기록 없음 - 기존 자판기 메시지가 남아 있으면 재사용 (DB 초기화 등으로 중복 전송 방지)
            msg = await self._find_existing_vending_message(channel)

        if msg is not None:
            try:
                await msg.edit(view=view)
                db.set_vending_message(channel.id, msg.id, content_hash)
                return "updated"
            except discord.Forbidden:
                raise
            except discord.NotFound:
                msg = None  # 수정 직전에 삭제됨 → 재전송
            except discord.HTTPException as e:
                if e.status == 429:
                    retry = self._note_rate_limit(e)
                    logger.warning(f"[VENDING] edit 레이트리밋(429) 채널 {channel.id}: {e} (백오프 {retry}초)")
                else:
                    logger.warning(f"[VENDING] edit 실패 채널 {channel.id}: {e}")
                return "rate_limited" if e.status == 429 else "failed"
            except Exception as e:
                logger.warning(f"[VENDING] edit 실패 채널 {channel.id}: {e}")
                return "failed"

        if msg is None:
            if self._is_rate_limited():
                logger.warning(f"[VENDING] 전송 스킵: 채널 {channel.id} - 레이트리밋 백오프 중")
                return "rate_limited"
            try:
                new_msg = await channel.send(view=view)
                db.set_vending_message(channel.id, new_msg.id, content_hash)
                return "updated"
            except discord.Forbidden:
                raise
            except discord.HTTPException as e:
                if e.status == 429:
                    retry = self._note_rate_limit(e)
                    logger.warning(f"[VENDING] send 레이트리밋(429) 채널 {channel.id}: {e} (백오프 {retry}초)")
                else:
                    logger.warning(f"[VENDING] send 실패 채널 {channel.id}: {e}")
                return "rate_limited" if e.status == 429 else "failed"
            except Exception as e:
                logger.warning(f"[VENDING] send 실패 채널 {channel.id}: {e}")
                return "failed"

        return "failed"

    async def _find_existing_vending_message(self, channel):
        """채널 최근 메시지에서 기존 자판기 메시지(버튼 custom_id 포함)를 찾아 재사용"""
        try:
            async for msg in channel.history(limit=50):
                if _message_has_vending_components(msg):
                    return msg
        except Exception as e:
            logger.warning(f"[VENDING] 히스토리 검색 실패 채널 {channel.id}: {e}")
        return None
    
    async def grant_purchase_role(self, member, product_name=None):
        """구매 완료 시 지정된 역할 자동 지급"""
        role_id = db.get_setting('purchase_role_id', '')
        if not role_id:
            return False
        
        try:
            role = member.guild.get_role(int(role_id))
            if not role:
                logger.warning(f"구매 역할을 찾을 수 없습니다: {role_id}")
                return False
            
            if role not in member.roles:
                await member.add_roles(role, reason="APEX VENDING 상품 구매")
                return True
            return False  # 이미 역할 보유
        except Exception as e:
            logger.error(f"구매 역할 지급 오류: {e}")
            return False
    
    async def request_review_dm(self, user_id, order_id, product_name):
        """구매 후 후기 요청 DM 전송 (임베드 + 후기 작성 버튼)"""
        try:
            user = await self.fetch_user(int(user_id))
            
            embed = discord.Embed(
                title="구매 완료 & 후기 요청",
                description=f"**{product_name}** 구매가 완료되었습니다! \n\n"
                           f"만족하셨다면 아래 **[후기 작성]** 버튼을 눌러\n"
                           f"별점과 함께 후기를 남겨주세요!",
                color=brand_color('main')
            )
            embed.add_field(name="주문번호", value=f"#{order_id}", inline=True)
            embed.add_field(name="상품", value=product_name, inline=True)
            embed.set_footer(text=brand_tag('REVIEW · 후기는 리뷰 채널에 자동 등록됩니다'))
            
            view = ReviewRequestView(order_id, product_name)
            await user.send(embed=embed, view=view)
            return True
        except Exception as e:
            logger.error(f"Review request DM error: {e}")
            return False
    
    def run_bot(self, token):
        def _run():
            try:
                self.run(token)
            except discord.PrivilegedIntentsRequired:
                logger.error(
                    "[봇] 로그인 실패: Privileged Intents 가 꺼져 있습니다.\n"
                    "  → https://discord.com/developers/applications → 해당 앱 → Bot\n"
                    "  → Privileged Gateway Intents 에서 'MESSAGE CONTENT INTENT' 와 "
                    "'SERVER MEMBERS INTENT' 를 ON 으로 저장한 뒤 다시 실행하세요."
                )
            except Exception as e:
                logger.error(f"Bot run error: {e}")
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread
    
    async def send_dm(self, user_id, content=None, embed=None, file=None, files=None):
        """DM 전송 (embed + 파일 첨부(단일/다중) 동시 지원)"""
        try:
            user = await self.fetch_user(int(user_id))
            kwargs = {}
            if content:
                kwargs['content'] = content
            if embed:
                kwargs['embed'] = embed
            if files:
                kwargs['files'] = files
            elif file:
                kwargs['file'] = file
            if not kwargs:
                kwargs['content'] = "안녕하세요!"
            await user.send(**kwargs)
            return True
        except Exception as e:
            logger.error(f"DM send error to {user_id}: {e}")
            return False
    
    async def confirm_order(self, order_id):
        order = db.get_order(order_id)
        if not order:
            return False, "주문을 찾을 수 없습니다."
        if order['status'] != 'pending':
            return False, f"이미 처리된 주문입니다. (상태: {order['status']})"
        
        key = db.get_available_key(order['product_id'])
        if not key:
            db.update_order_status(order_id, 'cancelled')
            await self.send_dm(order['user_id'], 
                f"**주문 #{order_id} 취소 안내**\n\n죄송합니다. 재고가 소진되어 주문이 자동 취소되었습니다.\n주문번호: #{order_id}")
            return False, "재고가 없어 주문을 취소했습니다."
        
        conn = db.get_conn()
        c = conn.cursor()
        c.execute('UPDATE keys SET used=1, order_id=? WHERE id=?', (order_id, key['id']))
        conn.commit()
        conn.close()
        
        db.update_order_status(order_id, 'completed', key_id=key['id'])
        
        embed = discord.Embed(
            title="구매 완료",
            description=f"**{order['product_name']}** 구매가 완료되었습니다!",
            color=brand_color('success')
        )
        embed.add_field(name="▸ 주문번호", value=f"`#{order_id}`", inline=True)
        embed.add_field(name="▸ 상품", value=order['product_name'], inline=True)
        product_row = db.get_product(order['product_id']) or {}
        card_png = await render_purchase_card(
            order['product_name'], product_row.get('category', ''), order['amount'],
            order['username'], order_id, order['user_id'],
            description=product_row.get('description', '')
        )
        card_files = []
        card_content = None
        card_key_file = None
        if card_png:
            card_files.append(discord.File(io.BytesIO(card_png), filename='receipt.png'))
            embed = discord.Embed(color=brand_color('success'))
            embed.set_image(url='attachment://receipt.png')
            embed.set_footer(text=brand_tag('THANK YOU'))
            card_key_file = build_key_attachment(key)
            if card_key_file:
                card_files.append(card_key_file)
            elif (key.get('key_value') or '').strip():
                card_content = "**YOUR KEY**\n```\n%s\n```" % key['key_value']
        else:
            embed.add_field(name="▸ 결제 금액", value=f"**{order['amount']:,}원**", inline=True)
        key_file = None if card_png else add_key_fields_to_embed(embed, key)
        embed.set_footer(text=brand_tag('THANK YOU'))
        
        if card_png:
            await self.send_dm(order['user_id'], content=card_content, embed=embed, files=card_files)
        else:
            await self.send_dm(order['user_id'], embed=embed, file=key_file)
        await self.refresh_vending_machines()
        
        sent_file = (card_key_file is not None) if card_png else (key_file is not None)
        delivered = '파일' if sent_file else '키'
        return True, f"주문 #{order_id} 완료! {delivered}가 전송되었습니다."
    
    async def cancel_order(self, order_id):
        order = db.get_order(order_id)
        if not order:
            return False, "주문을 찾을 수 없습니다."
        if order['status'] != 'pending':
            return False, f"이미 처리된 주문입니다. (상태: {order['status']})"
        
        db.update_order_status(order_id, 'cancelled')
        await self.send_dm(order['user_id'],
            f"**주문 #{order_id} 취소 안내**\n\n주문이 취소되었습니다.\n주문번호: #{order_id}\n상품: {order['product_name']}")
        return True, f"주문 #{order_id} 취소 완료!"
    
    async def refresh_vending_machines(self, force_edit=False):
        """전 채널 자판기 갱신 - 429 레이트리밋/버스트 방지

        - 동시 호출이 겹치면 하나만 실행 (락)
        - 실제 API 호출(edit/send)이 있었을 때만 채널 간 간격 유지
        - 429 발생 시 즉시 중단하고 백오프, 다음 주기에 재시도
        - 일정 주기마다 메시지 실존 확인(verify)으로 삭제 복구
        """
        if self._is_rate_limited():
            logger.warning("[VENDING] Refresh 스킵: 전역 레이트리밋(429) 백오프 중")
            return

        if self._refresh_lock.locked():
            logger.debug("[VENDING] Refresh 이미 진행 중 - 중복 호출 스킵")
            return

        self._refresh_tick += 1
        verify = (self._refresh_tick % 6 == 1)  # 약 30분(6주기)마다 메시지 실존 확인

        async with self._refresh_lock:
            channels = db.get_vending_channels()
            for i, ch in enumerate(channels):
                if self._is_rate_limited():
                    logger.warning("[VENDING] Refresh 중단: 전역 레이트리밋(429) 백오프 시작")
                    break
                try:
                    channel = self.get_channel(int(ch['channel_id']))
                    if not channel:
                        continue
                    result = await self.update_vending_machine(channel, force_edit=force_edit, verify=verify)
                    if result == "rate_limited":
                        break
                    # 실제 API 호출(edit/send)이 있었을 때만 간격 유지 (스킵이면 즉시 다음 채널)
                    if result == "updated" and i < len(channels) - 1:
                        await asyncio.sleep(2.0)
                except Exception as e:
                    logger.error(f"Refresh vending machine error: {e}")
            logger.info("[VENDING] Vending machines refreshed")
    
    async def send_stock_notice(self, product, key_count):
        """재고(키) 입고 시 입고 채널에 카드 이미지 + 임베드 전송"""
        stock_channel_id = db.get_setting('stock_channel_id', '')
        if not stock_channel_id:
            logger.warning("[입고알림] stock_channel_id 미설정 → 대시보드 설정에서 '입고 알림 채널 ID'를 저장하세요.")
            return

        try:
            channel = self.get_channel(int(stock_channel_id))
            if not channel:
                try:
                    channel = await self.fetch_channel(int(stock_channel_id))
                except Exception:
                    channel = None
            if not channel:
                logger.warning(f"[입고알림] 채널을 찾을 수 없음: {stock_channel_id}")
                return

            total_stock = db.count_available_keys(product['id'])
            embed = discord.Embed(
                title="재고 입고 완료!",
                description=f"**{product['name']}** 재고가 입고되었습니다!",
                color=brand_color('success')
            )
            embed.add_field(name="입고 수량", value=f"**+{key_count}개**", inline=True)
            embed.add_field(name="현재 재고", value=f"**{total_stock}개**", inline=True)
            embed.add_field(name="가격", value=f"**{product['price']:,}원**", inline=True)
            embed.set_footer(text=brand_tag('RESTOCK'))

            # 카드 이미지 생성 (실패하면 임베드만 전송)
            file = None
            try:
                if cards.available():
                    spec = cards.stock_spec(
                        BOT_NAME,
                        product.get('name', ''),
                        product.get('category', ''),
                        product.get('price', 0),
                        key_count,
                        total_stock,
                        description=product.get('description', '')
                    )
                    png = cards.render_card(spec)
                    if png:
                        file = discord.File(io.BytesIO(png), filename='apex_stock.png')
                        embed.set_image(url="attachment://apex_stock.png")
            except Exception as e:
                logger.warning(f"[입고알림] 카드 생성 실패: {e}")

            if file:
                await channel.send(embed=embed, file=file)
            else:
                await channel.send(embed=embed)
            logger.info(f"[입고알림] 전송 완료: {product['name']} +{key_count}개 (채널 {stock_channel_id})")
        except Exception as e:
            logger.error(f"Stock notice error: {e}")
    
    async def send_notice(self, title, content, color_hex=None, image_file=None):
        """공지 임베드 전송 (대시보드 및 봇 명령에서 사용) - 이미지 파일 지원"""
        notice_channel_id = db.get_setting('notice_channel_id', '')
        if not notice_channel_id:
            return False, "공지 채널이 설정되지 않았습니다. 대시보드 설정에서 공지 채널 ID를 입력하고 저장해주세요."
        
        try:
            # fetch_channel 사용: 캐시에 없어도 API로 직접 조회
            try:
                channel = self.get_channel(int(notice_channel_id))
                if not channel:
                    channel = await self.fetch_channel(int(notice_channel_id))
            except discord.NotFound:
                return False, f"공지 채널(ID: {notice_channel_id})을 찾을 수 없습니다. 채널 ID가 올바른지 확인해주세요."
            
            if not channel:
                return False, "공지 채널을 찾을 수 없습니다."
            
            try:
                if color_hex and color_hex.startswith('#'):
                    color_hex = color_hex.replace('#', '0x')
                embed_color = discord.Color(int(color_hex or '0xF0B429', 16))
            except:
                embed_color = brand_color('info')
            
            embed = discord.Embed(
                title=title,
                description=content,
                color=embed_color
            )
            embed.set_footer(text=brand_tag('NOTICE'))
            
            # 이미지 파일이 있으면 첨부
            if image_file:
                file = discord.File(image_file, filename="notice_image.png")
                embed.set_image(url="attachment://notice_image.png")
                await channel.send(embed=embed, file=file)
            else:
                await channel.send(embed=embed)
            
            return True, "공지가 전송되었습니다!"
        except Exception as e:
            logger.error(f"Send notice error: {e}")
            return False, f"공지 전송 실패: {str(e)}"


# ============ VENDING MACHINE VIEWS ============

def _catalog_embed(user_id, category=None):
    """제품 목록 임베드 생성 (카테고리 지정 시 해당 카테고리만)"""
    if category:
        products = db.get_products_by_category(category, active_only=True)
        title = f"제품 · {category}"
    else:
        products = db.get_products(active_only=True)
        title = "전체 제품"

    embed = discord.Embed(
        title=title,
        description=(
            f"-# 보유 포인트 **{db.get_balance(str(user_id)):,}P** · 구매 즉시 DM으로 전달"
        ),
        color=brand_color('main')
    )
    if not products:
        embed.add_field(name="상품 준비중", value="해당 카테고리에 판매 중인 상품이 없습니다.", inline=False)
    else:
        lines = []
        for p in products:
            stock = db.count_available_keys(p['id'])
            stock_text = f"재고 {stock}개" if stock > 0 else "품절"
            lines.append(f"▸ {p['name']} · **{p['price']:,}원** · {stock_text}")
            desc_text = product_desc(p, 90)
            if desc_text:
                lines.append(f"-# {desc_text}")
        embed.add_field(name=f"{len(products)}개 상품", value="\n".join(lines)[:1000], inline=False)
    embed.set_footer(text=brand_tag('CATALOG'))
    return embed


class CategoryPickMenu(discord.ui.Select):
    def __init__(self, categories):
        def _info(cat):
            """카테고리 최소 가격과 상품 수"""
            try:
                prods = db.get_products_by_category(cat, active_only=True)
            except Exception:
                prods = []
            prices = [int(p['price']) for p in prods if p.get('price')]
            if not prices:
                return "판매 상품 없음", 0
            return f"최소 {min(prices):,}원", len(prods)

        all_prods = db.get_products(active_only=True)
        all_prices = [int(p['price']) for p in all_prods if p.get('price')]
        all_desc = f"최소 {min(all_prices):,}원 · {len(all_prods)}개" if all_prices else "상품 없음"
        options = [discord.SelectOption(label="전체 보기", value="__all__", description=all_desc)]
        for c in categories[:24]:
            desc, _n = _info(c)
            options.append(discord.SelectOption(label=str(c)[:100], value=str(c)[:100], description=desc))
        super().__init__(placeholder="카테고리를 선택하세요", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        cat = None if self.values[0] == '__all__' else self.values[0]
        try:
            embed = _catalog_embed(interaction.user.id, cat)
            await interaction.edit_original_response(embed=embed, view=None)
        except Exception as e:
            logger.warning(f"[CATALOG] 카테고리 목록 표시 실패: {e}")


class CategoryPickView(discord.ui.View):
    def __init__(self, categories):
        super().__init__(timeout=180)
        self.add_item(CategoryPickMenu(categories))


class ExchangePickMenu(discord.ui.Select):
    """최근 30분 이내 구매 상품 선택 → 교환 티켓 생성"""
    def __init__(self, orders):
        self.orders = orders
        opts = []
        for o in orders[:25]:
            label = str(o.get('product_name') or '상품')[:70]
            opts.append(discord.SelectOption(
                label=label,
                value=str(o['id']),
                description=f"{int(o.get('amount') or 0):,}원 · {str(o.get('created_at'))[:16]}"
            ))
        super().__init__(placeholder="교환할 상품을 선택하세요", min_values=1, max_values=1, options=opts)

    async def callback(self, interaction: discord.Interaction):
        order = next((o for o in self.orders if str(o['id']) == self.values[0]), None)
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        if not order:
            await interaction.followup.send("주문 정보를 찾을 수 없습니다.", ephemeral=True)
            return

        category_id = (db.get_setting('ticket_category_id', '') or '').strip()
        category = interaction.client.get_channel(int(category_id)) if category_id else None
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send("티켓 카테고리가 설정되지 않았습니다. 관리자에게 문의해 주세요.", ephemeral=True)
            return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True, read_message_history=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True, read_message_history=True),
        }
        try:
            for admin in db.get_admins():
                m = interaction.guild.get_member(int(admin['user_id']))
                if m:
                    overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True, read_message_history=True)
        except Exception:
            pass

        try:
            ch = await category.create_text_channel(
                name=f"교환-{interaction.user.name}"[:90], overwrites=overwrites
            )
            embed = discord.Embed(
                title="불량교환 요청",
                description=(
                    f"**상품** : {order.get('product_name')}\n"
                    f"**금액** : {int(order.get('amount') or 0):,}원\n"
                    f"**주문번호** : #{order.get('id')}\n"
                    f"**구매시각** : {order.get('created_at')}\n\n"
                    "교환 사유와 함께 스크린샷/영상을 남겨주세요."
                ),
                color=brand_color('warn')
            )
            embed.set_footer(text=brand_tag('EXCHANGE'))
            await ch.send(content=f"{interaction.user.mention}", embed=embed)
            await interaction.followup.send(f"교환 티켓이 생성되었습니다: {ch.mention}", ephemeral=True)
        except Exception as e:
            logger.error(f"[EXCHANGE] 티켓 생성 실패: {e}")
            await interaction.followup.send(f"티켓 생성에 실패했습니다: {e}", ephemeral=True)


class ExchangePickView(discord.ui.View):
    def __init__(self, orders):
        super().__init__(timeout=180)
        self.add_item(ExchangePickMenu(orders))


class VendingMainView(ui.LayoutView):
    """Components V2: 임베드 컨테이너 안에 드롭다운+버튼이 통합됨"""
    def __init__(self):
        super().__init__(timeout=None)
        
        title = db.get_setting('vending_title', BOT_NAME)
        desc = db.get_setting('vending_desc', '원하시는 메뉴를 선택해주세요.')
        footer = db.get_setting('vending_footer', BRAND_FOOTER)

        try:
            color_hex = db.get_setting('vending_color', '#F0B429')
            if color_hex.startswith('#'):
                color_hex = color_hex.replace('#', '0x')
            accent = discord.Color(int(color_hex, 16))
        except Exception:
            accent = brand_color('main')

        # 실시간 현황
        products = db.get_products(active_only=True)
        total_stock = sum(db.count_available_keys(p['id']) for p in products)
        selling = sum(1 for p in products if db.count_available_keys(p['id']) > 0)
        status_text = (
            f"상품 **{len(products)}**종 · 재고 **{total_stock}**개 · 판매중 **{selling}**종"
        )

        # 쿠키 유효성 검사 현황 (파일 재고가 있을 때만 표시)
        cookie_stats = db.count_cookie_status()
        cookie_line = ''
        if cookie_stats.get('total'):
            last_check = db.get_setting('cookie_last_check_at', '')
            if last_check:
                # 디스코드 동적 타임스탬프: 클라이언트가 1초마다 자동 갱신 + 마우스 오버 시 KST 표시
                when = discord_ts(last_check, 'R') or relative_time_text(last_check)
                cookie_line = (
                    f"쿠키 유효성 검사 {when}\n"
                    f"-# 유효 **{cookie_stats['valid']}** · 무효 **{cookie_stats['invalid']}**"
                    f" · 판매가능 **{cookie_stats['sellable']}**"
                )
            else:
                cookie_line = "쿠키 유효성 검사 **대기 중**\n-# 첫 검사가 완료되면 시각이 표시됩니다."

        # 푸터: 문구 + 채널 멘션(ex. #문의하기)
        footer_channels = db.get_setting('vending_footer_channel_id', '')
        mentions = ' '.join(
            f"<#{cid.strip()}>"
            for cid in str(footer_channels).replace(';', ',').split(',')
            if cid.strip().isdigit()
        )
        footer_line = '  '.join(part for part in (footer, mentions) if part)

        children = [
            ui.TextDisplay(f"# {title}"),
            ui.Separator(),
            ui.TextDisplay(desc),
            ui.ActionRow(CategorySelect()),
            ui.ActionRow(
                VendingButton(label="제품", emoji=app_emoji('cart'), style=discord.ButtonStyle.primary, custom_id="vending_products"),
                VendingButton(label="충전", emoji=app_emoji('card'), style=discord.ButtonStyle.success, custom_id="vending_charge"),
                VendingButton(label="정보", emoji=app_emoji('info'), style=discord.ButtonStyle.secondary, custom_id="vending_info"),
                VendingButton(label="불량교환", emoji=app_emoji('refund'), style=discord.ButtonStyle.secondary, custom_id="vending_ticket"),
            ),
            ui.Separator(),
            ui.TextDisplay(status_text),
        ]
        if cookie_line:
            children.append(ui.TextDisplay(cookie_line))
        if footer_line:
            children.append(ui.TextDisplay(f"-# {footer_line}"))

        # 하단 배너 이미지 (설정된 경우 맨 아래에 크게 표시)
        banner_url = str(db.get_setting('vending_banner_url', '') or '').strip()
        if banner_url.startswith('http'):
            try:
                children.append(ui.MediaGallery(discord.MediaGalleryItem(media=banner_url)))
            except Exception as e:
                logger.warning(f"Banner gallery error: {e}")

        container = ui.Container(*children, accent_color=accent)
        self.add_item(container)


class CategorySelect(discord.ui.Select):
    """카테고리 선택 드롭다운 - 선택 시 해당 카테고리 상품 구매 메뉴 표시"""
    def __init__(self, row=0):
        categories = db.get_categories()
        products = db.get_products(active_only=True)
        
        options = []
        if categories:
            for cat in categories[:24]:
                cat_count = len(db.get_products_by_category(cat, active_only=True))
                options.append(discord.SelectOption(
                    label=cat,
                    description=f"{cat_count}개 상품"
                ))
        else:
            for p in products[:24]:
                stock = db.count_available_keys(p['id'])
                d = product_desc(p, 60)
                opt_desc = (f"{d} · 재고 {stock}개" if d else f"재고: {stock}개")[:100]
                options.append(discord.SelectOption(
                    label=f"{p['name']} ({p['price']:,}원)",
                    description=opt_desc,
                    value=str(p['id'])
                ))
        
        if not options:
            options = [discord.SelectOption(label="상품 준비중", value="none")]
        
        placeholder = "사용할 카테고리를 선택하세요" if categories else "구매할 상품을 선택하세요"
        
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            custom_id="vending_category_select",
            row=row
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        
        if selected == "none":
            await interaction.response.send_message("아직 상품이 등록되지 않았습니다.", ephemeral=True)
            return
        
        # 카테고리 모드인지 상품 ID 모드인지 판단
        categories = db.get_categories()
        
        if categories and selected in categories:
            # 카테고리 선택 → 해당 카테고리 상품 구매 메뉴
            cat_products = db.get_products_by_category(selected, active_only=True)
            if not cat_products:
                await interaction.response.send_message("해당 카테고리에 상품이 없습니다.", ephemeral=True)
                return
            
            balance = db.get_balance(str(interaction.user.id))
            
            embed = discord.Embed(
                title=f"{selected}",
                description=f"구매할 상품을 선택하세요!\n\n현재 포인트: **{balance:,}원**",
                color=brand_color('main')
            )
            for p in cat_products:
                stock = db.count_available_keys(p['id'])
                stock_text = f"재고 {stock}개" if stock > 0 else "품절"
                desc_text = product_desc(p, 200)
                embed.add_field(
                    name=p['name'],
                    value=(f"**{p['price']:,}원** · {stock_text}"
                           + (f"\n{desc_text}" if desc_text else "")),
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, view=BuyProductView(cat_products), ephemeral=True)
        else:
            # 상품 직접 선택 → 구매 확인
            try:
                pid = int(selected)
            except:
                await interaction.response.send_message("잘못된 선택입니다.", ephemeral=True)
                return
            
            product = db.get_product(pid)
            if not product or not product['active']:
                await interaction.response.send_message("판매 중지된 상품입니다.", ephemeral=True)
                return
            
            stock = db.count_available_keys(pid)
            if stock <= 0:
                await interaction.response.send_message(NO_STOCK_TEXT, ephemeral=True)
                return
            
            balance = db.get_balance(str(interaction.user.id))
            price = product['price']
            note = ""
            if balance < price:
                note = (
                    f"\n\n보유 포인트: **{balance:,}P** (정가 {price:,}P)\n"
                    f"-# 할인 쿠폰을 사용하면 할인된 금액으로 결제할 수 있습니다."
                )

            product_desc_line = product_desc(product, 120)
            await interaction.response.send_message(
                f"**{product['name']}** - {price:,}포인트\n"
                + (f"{product_desc_line}\n" if product_desc_line else "")
                + f"\n구매를 진행하시겠습니까?\n"
                f"쿠폰이 있다면 **쿠폰 사용** 버튼을 눌러 할인받으세요! (없으면 바로 구매 확정){note}",
                view=ConfirmBuyView(product),
                ephemeral=True
            )


class VendingButton(discord.ui.Button):
    async def callback(self, interaction: discord.Interaction):
        action = self.custom_id.split('_')[1] if len(self.custom_id.split('_')) > 1 else ''

        try:
            if action == 'products':
                await self.show_products(interaction)
            elif action == 'charge':
                await self.show_charge(interaction)
            elif action == 'buy':
                await self.show_buy_menu(interaction)
            elif action == 'info':
                await self.show_info(interaction)
            elif action == 'ticket':
                await self.show_ticket(interaction)
        except discord.HTTPException as e:
            # 429(특히 Cloudflare 1015 IP 차단) 는 트레이스백 대신 백오프만 기록
            if e.status == 429:
                retry = self.view.bot._note_rate_limit(e) if getattr(self, 'view', None) and getattr(self.view, 'bot', None) else 120
                logger.warning(f"[VENDING] 버튼 응답 429 - {retry:.0f}초 백오프 (액션={action})")
            else:
                logger.warning(f"[VENDING] 버튼 처리 실패 (액션={action}): {e}")
        except Exception as e:
            logger.error(f"[VENDING] 버튼 처리 오류 (액션={action}): {e}")

    async def _safe_defer(self, interaction):
        """interaction 응답 지연(defer). 429/만료 상황에서도 예외를 밖으로 던지지 않는다."""
        try:
            await interaction.response.defer(ephemeral=True)
            return True
        except discord.NotFound:
            logger.warning("[VENDING] 상호작용 만료(10062) - 이미 처리된 클릭")
            return False
        except discord.HTTPException as e:
            if e.status == 429:
                bot = getattr(getattr(self, 'view', None), 'bot', None)
                retry = bot._note_rate_limit(e) if bot else 120
                logger.warning(f"[VENDING] defer 429 - {retry:.0f}초 백오프")
            else:
                logger.warning(f"[VENDING] defer 실패: {e}")
            return False

    async def show_products(self, interaction):
        # defer 먼저 호출하여 interaction 3초 제한 초과 방지 (429/만료는 무시)
        if not await self._safe_defer(interaction):
            return

        # 카테고리가 있으면 항상 카테고리 선택 화면을 먼저 보여준다 (설정값과 무관)
        try:
            cats = db.get_categories()
            if not cats:
                cats = sorted({(p.get('category') or '') for p in db.get_products(active_only=True) if (p.get('category') or '').strip()})
        except Exception:
            cats = []
        if cats:
            embed = discord.Embed(
                title="제품 카테고리",
                description="아래에서 카테고리를 선택하면 해당 제품 목록이 표시됩니다.",
                color=brand_color('main')
            )
            embed.set_footer(text=brand_tag('CATALOG'))
            await interaction.followup.send(embed=embed, view=CategoryPickView(cats), ephemeral=True)
            return

        products = db.get_products(active_only=True)
        
        embed = discord.Embed(
            title="카탈로그",
            description=(
                "판매 중인 상품 목록입니다.\n"
                f"-# 보유 포인트 **{db.get_balance(str(interaction.user.id)):,}P** · 구매 즉시 DM으로 전달"
            ),
            color=brand_color('main')
        )
        
        if not products:
            embed.add_field(name="상품 준비중", value="곧 상품이 등록됩니다!", inline=False)
        else:
            # 카테고리 사용 여부 확인
            use_categories = db.get_setting('use_categories', 'false').lower() == 'true'
            categories = db.get_categories() if use_categories else []

            def _product_lines(items):
                """상품 목록 → 설명 포함 라인"""
                out = []
                for item in items:
                    stock = db.count_available_keys(item['id'])
                    stock_text = f"재고 {stock}개" if stock > 0 else "품절"
                    out.append(f"▸ {item['name']} · **{item['price']:,}원** · {stock_text}")
                    desc_text = product_desc(item, 90)
                    if desc_text:
                        out.append(f"-# {desc_text}")
                return out

            if categories:
                # 카테고리별로 그룹화하여 표시
                for cat in categories:
                    cat_products = db.get_products_by_category(cat, active_only=True)
                    if not cat_products:
                        continue
                    embed.add_field(name=f"▸ {cat}", value="\n".join(_product_lines(cat_products)), inline=False)
                # 카테고리 없는 상품
                no_cat = [p for p in products if not p.get('category')]
                if no_cat:
                    embed.add_field(name="▸ 기타", value="\n".join(_product_lines(no_cat)), inline=False)
            else:
                # 카테고리 미사용 → 전체 표시
                for p in products:
                    stock = db.count_available_keys(p['id'])
                    desc_text = product_desc(p, 200)
                    embed.add_field(
                        name=f"{p['name']} - {p['price']:,}원",
                        value=(f"{desc_text}\n" if desc_text else "") + f"재고: {stock}개",
                        inline=False
                    )
        
        embed.set_footer(text=brand_tag('CATALOG'))
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def show_charge(self, interaction):
        # 계좌 정보는 숨기고 충전 신청 버튼만 표시
        embed = discord.Embed(
            title="포인트 충전",
            description=(
                "충전 신청 버튼을 누르고 입금자명과 금액을 입력하세요.\n"
                "안내된 계좌로 입금하면 자동으로 충전됩니다.\n\n"
                "▸ 입금자명과 금액이 일치해야 자동 충전됩니다.\n"
                "▸ 3분 내 처리되지 않으면 DM으로 안내드립니다."
            ),
            color=brand_color('main')
        )
        embed.add_field(name="▸ 환율", value="`1원 = 1포인트`", inline=True)
        embed.add_field(name="▸ 처리 속도", value="`자동 · 1~2분`", inline=True)
        embed.set_footer(text=brand_tag('CHARGE'))
        
        view = ChargeRequestView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def show_buy_menu(self, interaction):
        # defer 먼저 호출하여 interaction 3초 제한 초과 방지
        await interaction.response.defer(ephemeral=True)
        
        products = db.get_products(active_only=True)
        
        if not products:
            await interaction.followup.send("현재 구매할 수 있는 상품이 없습니다.", ephemeral=True)
            return
        
        # Check balance
        balance = db.get_balance(str(interaction.user.id))
        
        embed = discord.Embed(
            title="상품 구매",
            description=f"구매할 상품을 선택하세요!\n\n현재 포인트: **{balance:,}원**",
            color=brand_color('info')
        )
        
        # 카테고리 사용 여부 확인
        use_categories = db.get_setting('use_categories', 'false').lower() == 'true'
        categories = db.get_categories() if use_categories else []

        def _buy_lines(items):
            out = []
            for item in items:
                stock = db.count_available_keys(item['id'])
                stock_text = f"재고 {stock}개" if stock > 0 else "품절"
                out.append(f"▸ {item['name']} · **{item['price']:,}원** · {stock_text}")
                desc_text = product_desc(item, 90)
                if desc_text:
                    out.append(f"-# {desc_text}")
            return out

        if categories:
            for cat in categories:
                cat_products = db.get_products_by_category(cat, active_only=True)
                if not cat_products:
                    continue
                embed.add_field(name=f"▸ {cat}", value="\n".join(_buy_lines(cat_products)), inline=False)
            # 카테고리 없는 상품
            no_cat = [p for p in products if not p.get('category')]
            if no_cat:
                embed.add_field(name="▸ 기타", value="\n".join(_buy_lines(no_cat)), inline=False)
        else:
            for p in products:
                stock = db.count_available_keys(p['id'])
                desc_text = product_desc(p, 200)
                embed.add_field(
                    name=f"{p['name']} - {p['price']:,}원",
                    value=(f"{desc_text}\n" if desc_text else "") + f"재고: {stock}개",
                    inline=False
                )
        
        await interaction.followup.send(embed=embed, view=BuyProductView(products), ephemeral=True)
    
    async def show_info(self, interaction):
        # defer 먼저 호출하여 interaction 3초 제한 초과 방지
        await interaction.response.defer(ephemeral=True)
        
        user = db.get_or_create_user(str(interaction.user.id), interaction.user.name)
        balance = user['balance']
        
        # Get recent purchases
        orders = db.get_orders(user_id=str(interaction.user.id), limit=5)
        transactions = db.get_user_transactions(str(interaction.user.id), limit=5)
        
        embed = discord.Embed(
            title="내 정보",
            description=f"**{interaction.user.display_name}** 님의 계정 정보입니다.",
            color=brand_color('main')
        )
        embed.add_field(name="▸ 보유 포인트", value=f"**{balance:,} P**", inline=True)
        embed.add_field(name="▸ 구매 완료", value=f"**{sum(1 for o in orders if o['status'] == 'completed')}회**", inline=True)
        
        # 거래 타입 한글 매핑
        trans_type_map = {
            'charge': '충전',
            'purchase': '구매',
            'admin_add': '관리자 지급',
            'admin_remove': '관리자 차감',
            'refund': '환불'
        }
        
        if transactions:
            trans_text = []
            for t in transactions[:5]:
                trans_label = trans_type_map.get(t['type'], t['type'])
                sign = '+' if t['amount'] > 0 else '-'
                trans_text.append(
                    f"▸ {trans_label} {sign}{abs(t['amount']):,}P · {t['created_at']}"
                )
            embed.add_field(name="▸ 최근 거래", value="\n".join(trans_text), inline=False)
        else:
            embed.add_field(name="▸ 최근 거래", value="거래 내역이 없습니다.", inline=False)
        
        embed.set_footer(text=brand_tag('ACCOUNT'))
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def show_ticket(self, interaction):
        """문의 티켓 생성 (모든 유저 이용 가능)"""
        # Check if user already has an open ticket
        existing = db.get_open_ticket_by_user(str(interaction.user.id))
        if existing:
            try:
                channel = interaction.client.get_channel(int(existing['channel_id']))
                if channel:
                    await interaction.response.send_message(
                        f"**이미 열려있는 문의 티켓이 있습니다!**\n\n"
                        f"티켓 채널: {channel.mention}\n"
                        f"티켓을 닫은 후 새로 생성할 수 있습니다.",
                        ephemeral=True
                    )
                    return
            except:
                pass
        
        # 불량교환: 최근 30분 이내 구매 상품을 선택해서 티켓 생성
        orders = db.get_recent_orders(str(interaction.user.id), 30)
        if not orders:
            await interaction.response.send_message(
                "**불량교환은 최근 30분 이내 구매한 상품만 신청할 수 있습니다.**\n\n"
                "구매 내역이 확인되지 않았습니다.\n"
                "· 구매 후 30분이 지났거나\n"
                "· 아직 결제가 확정되지 않은 경우입니다.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="불량교환 신청",
            description="최근 30분 이내 구매한 상품입니다.\n교환할 상품을 아래에서 선택해 주세요.",
            color=brand_color('warn')
        )
        embed.set_footer(text=brand_tag('EXCHANGE'))
        await interaction.response.send_message(embed=embed, view=ExchangePickView(orders), ephemeral=True)
        return

        # Get ticket category
        category_id = db.get_setting('ticket_category_id', '')
        if not category_id:
            await interaction.response.send_message(
                "문의 시스템이 아직 설정되지 않았습니다.\n관리자에게 문의해주세요.",
                ephemeral=True
            )
            return
        
        try:
            category = interaction.client.get_channel(int(category_id))
            if not category or not isinstance(category, discord.CategoryChannel):
                await interaction.response.send_message(
                    "문의 카테고리가 올바르지 않습니다.\n관리자에게 문의해주세요.",
                    ephemeral=True
                )
                return
            
            # Create ticket channel
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True, read_message_history=True),
                interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True, read_message_history=True)
            }
            
            # Add admin permissions (멤버 캐시가 없어도 되도록 fetch 로 보완)
            admins = db.get_admins()
            for admin in admins:
                admin_member = interaction.guild.get_member(int(admin['user_id']))
                if admin_member is None:
                    try:
                        admin_member = await interaction.guild.fetch_member(int(admin['user_id']))
                    except Exception:
                        admin_member = None
                if admin_member:
                    overwrites[admin_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True, read_message_history=True)
            
            channel_name = f"지원-{interaction.user.name}"
            ticket_channel = await category.create_text_channel(
                name=channel_name,
                overwrites=overwrites
            )
            
            # Create ticket in DB
            tid = db.create_ticket(str(interaction.user.id), interaction.user.name, ticket_channel.id)
            if tid == -1:
                await ticket_channel.delete()
                await interaction.response.send_message(
                    "이미 열려있는 문의 티켓이 있습니다!",
                    ephemeral=True
                )
                return
            
            # Send ticket message
            embed = discord.Embed(
                title=f"지원 티켓 #{tid}",
                description=f"**{interaction.user.mention}** 님의 1:1 지원 채널입니다.\n\n"
                           f"> 문의 내용을 이 채널에 작성해주세요.\n"
                           f"> 담당자가 확인 후 순차적으로 답변드립니다.",
                color=brand_color('main')
            )
            embed.add_field(name="▸ 안내", value="문의가 해결되면 관리자가 아래 버튼으로 티켓을 종료합니다.", inline=False)
            embed.set_footer(text=brand_tag('SUPPORT'))
            
            view = TicketView(tid)
            await ticket_channel.send(embed=embed, view=view)
            
            await interaction.response.send_message(
                f"문의 티켓이 생성되었습니다!\n채널: {ticket_channel.mention}",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Ticket creation error: {e}")
            await interaction.response.send_message(
                f"티켓 생성 중 오류가 발생했습니다: {str(e)}",
                ephemeral=True
            )


class TicketView(discord.ui.View):
    """Ticket management view"""
    def __init__(self, ticket_id):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.add_item(CloseTicketButton(ticket_id, row=0))


class CloseTicketButton(discord.ui.Button):
    def __init__(self, ticket_id, row=0):
        super().__init__(
            label="티켓 닫기",
            style=discord.ButtonStyle.danger,
            custom_id=f"ticket_close_{ticket_id}",
            row=row
        )
        self.ticket_id = ticket_id
    
    async def callback(self, interaction: discord.Interaction):
        ticket = db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("티켓을 찾을 수 없습니다.", ephemeral=True)
            return
        
        # 관리자만 티켓 닫기 가능
        if not db.is_admin(str(interaction.user.id)):
            await interaction.response.send_message(
                "**티켓은 관리자만 닫을 수 있습니다.**\n"
                "문의가 해결되었으면 관리자에게 요청해주세요.",
                ephemeral=True
            )
            return
        
        # Close ticket
        db.close_ticket(self.ticket_id)
        
        embed = discord.Embed(
            title="티켓 닫힘",
            description=f"티켓 #{self.ticket_id}이(가) 닫혔습니다.\n\n이 채널은 5초 후 삭제됩니다.",
            color=brand_color('error')
        )
        await interaction.response.edit_message(embed=embed, view=None)
        
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass


class ReviewRequestView(discord.ui.View):
    """후기 작성 버튼 뷰 (DM용)"""
    def __init__(self, order_id, product_name):
        super().__init__(timeout=None)
        self.order_id = order_id
        self.product_name = product_name
        self.add_item(ReviewButton(order_id, product_name))


class ChargeApproveView(discord.ui.View):
    """충전로그에서 관리자가 승인/거절하는 버튼 뷰"""
    def __init__(self, charge_id):
        super().__init__(timeout=None)
        self.charge_id = charge_id

    @discord.ui.button(label="승인", style=discord.ButtonStyle.success, custom_id="charge_approve_btn")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide(interaction, approve=True)

    @discord.ui.button(label="거절", style=discord.ButtonStyle.danger, custom_id="charge_reject_btn")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide(interaction, approve=False)

    async def _decide(self, interaction: discord.Interaction, approve: bool):
        # 관리자 권한 확인
        if not db.is_admin(str(interaction.user.id)):
            await interaction.response.send_message("관리자만 처리할 수 있습니다.", ephemeral=True)
            return

        req = db.get_charge_request(self.charge_id)
        if not req:
            await interaction.response.send_message("충전 요청을 찾을 수 없습니다.", ephemeral=True)
            return
        if req['status'] != 'pending':
            await interaction.response.send_message(f"이미 처리된 요청입니다. (상태: {req['status']})", ephemeral=True)
            return

        if approve:
            # 포인트 지급 + 완료 처리
            new_balance = db.add_balance(
                req['user_id'], req['username'], req['amount'],
                trans_type='charge',
                description=f"수동 승인 충전 ({req['depositor_name']}, {req['amount']:,}원)"
            )
            db.complete_charge_request(req['id'])
            result_text = f"**승인 완료!** {req['username']} 님에게 {req['amount']:,}포인트가 지급되었습니다."
        else:
            db.cancel_charge_request(req['id'])
            result_text = f"**거절되었습니다.** 요청 #{req['id']} 을(를) 취소했습니다."
        # 결정자 기록
        try:
            import sqlite3
            conn = db.get_conn()
            c = conn.cursor()
            c.execute("UPDATE charge_requests SET decided_by=? WHERE id=?",
                      (str(interaction.user.id), self.charge_id))
            conn.commit()
            conn.close()
        except Exception:
            pass

        # 버튼 비활성화 + 결과 표시
        for _btn in self.children:
            _btn.disabled = True
        await interaction.response.edit_message(content=result_text, view=self)

        # 유저에게 DM 알림
        try:
            if approve:
                embed = discord.Embed(
                    title="충전 승인 완료!",
                    description=f"{req['amount']:,}포인트가 충전되었습니다.",
                    color=brand_color('success')
                )
                embed.add_field(name="현재 잔액", value=f"{new_balance:,}포인트", inline=True)
            else:
                embed = discord.Embed(
                    title="충전이 거절되었습니다",
                    description=f"{req['amount']:,}포인트 충전 요청이 거절되었습니다.",
                    color=brand_color('error')
                )
            await interaction.client.send_dm(req['user_id'], embed=embed)
        except Exception as e:
            logger.error(f"[충전승인] DM 알림 실패: {e}")

        logger.info(f"[충전로그] #{self.charge_id} {'승인' if approve else '거절'} (관리자: {interaction.user})")
class ReviewButton(discord.ui.Button):
    def __init__(self, order_id, product_name):
        super().__init__(
            label="후기 작성",
            style=discord.ButtonStyle.success,
            custom_id=f"review_write_{order_id}",
            emoji=None
        )
        self.order_id = order_id
        self.product_name = product_name
    
    async def callback(self, interaction: discord.Interaction):
        # 구매당 1개 제한: 이미 후기 작성한 주문이면 버튼 안내
        reviewed = db.order_is_reviewed(self.order_id)
        if reviewed is None:
            await interaction.response.send_message("주문 정보를 찾을 수 없습니다.", ephemeral=True)
            return
        if reviewed:
            await interaction.response.send_message("이 구매건은 이미 후기를 작성하셨습니다.\n후기는 구매당 1개만 작성 가능합니다 ", ephemeral=True)
            return
        await interaction.response.send_modal(ReviewModal(self.order_id, self.product_name))


class ReviewModal(discord.ui.Modal):
    """후기 작성 모달 (별점 + 내용)"""
    def __init__(self, order_id, product_name):
        super().__init__(title=f"후기 작성 - {product_name[:20]}")
        self.order_id = order_id
        self.product_name = product_name
        
        self.rating = discord.ui.TextInput(
            label="별점 (1~5)",
            placeholder="1부터 5까지 숫자로 입력하세요 (예: 5)",
            required=True,
            max_length=1
        )
        self.add_item(self.rating)
        
        self.content = discord.ui.TextInput(
            label="후기 내용",
            style=discord.TextStyle.paragraph,
            placeholder="상품에 대한 솔직한 후기를 남겨주세요!",
            required=True,
            max_length=1000
        )
        self.add_item(self.content)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating = int(self.rating.value.strip())
        except:
            await interaction.response.send_message("별점은 1~5 사이의 숫자로 입력해주세요.", ephemeral=True)
            return
        
        if rating < 1 or rating > 5:
            await interaction.response.send_message("별점은 1~5 사이의 숫자로 입력해주세요.", ephemeral=True)
            return
        
        content = self.content.value.strip()
        if len(content) < 2:
            await interaction.response.send_message("후기가 너무 짧습니다! 조금 더 길게 작성해주세요.", ephemeral=True)
            return
        
        # 리뷰 채널에 게시
        success, msg = await interaction.client.post_review(
            interaction.user, self.order_id, self.product_name, rating, content
        )
        
        if success:
            confirm_embed = discord.Embed(
                title="후기가 등록되었습니다!",
                description="소중한 후기 감사합니다! \n\n후기는 리뷰 채널에 등록되었습니다.",
                color=brand_color('success')
            )
            confirm_embed.set_footer(text=brand_tag('REVIEW'))
            await interaction.response.send_message(embed=confirm_embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"{msg}", ephemeral=True)


class ChargeRequestView(discord.ui.View):
    """Charge request button view"""
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(ChargeRequestButton(label="충전 신청", style=discord.ButtonStyle.success, custom_id="charge_request"))


class ChargeRequestButton(discord.ui.Button):
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ChargeRequestModal())


class ChargeRequestModal(discord.ui.Modal):
    """Modal for charge request with depositor name and amount"""
    def __init__(self):
        super().__init__(title="포인트 충전 신청")
        
        self.depositor_name = discord.ui.TextInput(
            label="입금자명",
            placeholder="입금하실 때 사용한 이름을 입력하세요",
            required=True,
            max_length=50
        )
        self.add_item(self.depositor_name)
        
        self.amount = discord.ui.TextInput(
            label="충전 금액 (원)",
            placeholder="입금하실 금액을 숫자로 입력하세요 (예: 10000)",
            required=True,
            max_length=10
        )
        self.add_item(self.amount)
    
    async def on_submit(self, interaction: discord.Interaction):
        depositor_name = self.depositor_name.value.strip()
        try:
            amount = int(self.amount.value.strip().replace(',', ''))
        except:
            await interaction.response.send_message("금액은 숫자로 입력해주세요.", ephemeral=True)
            return
        
        if amount <= 0:
            await interaction.response.send_message("0보다 큰 금액을 입력해주세요.", ephemeral=True)
            return
        
        # Get bank info
        bank_account = db.get_setting('bank_account', '미설정')
        bank_holder = db.get_setting('bank_holder', '미설정')
        bank_name = db.get_setting('bank_name', '')
        
        # 충전 요청 유효 시간 (대시보드 설정값, 기본 30분)
        try:
            expire_minutes = int(str(db.get_setting('charge_expire_minutes', '')).strip() or 30)
        except (TypeError, ValueError):
            expire_minutes = 30
        expire_minutes = max(1, min(expire_minutes, 1440))
        
        # Create charge request
        rid = db.create_charge_request(str(interaction.user.id), interaction.user.name, depositor_name, amount)
        
        embed = discord.Embed(
            title="충전 신청 접수",
            description="아래 계좌로 입금하시면 **자동으로 충전**됩니다.",
            color=brand_color('main')
        )
        embed.add_field(name="▸ 요청번호", value=f"#{rid}", inline=True)
        embed.add_field(name="▸ 입금자명", value=depositor_name, inline=True)
        embed.add_field(name="▸ 충전 금액", value=f"{amount:,}원 → {amount:,}포인트", inline=True)
        embed.add_field(name="▸ 입금 계좌", value=f"{bank_name} {bank_account} ({bank_holder})", inline=False)
        embed.add_field(name="▸ 안내", value=(
            f"**{bank_account} ({bank_holder})** 로 입금해주세요.\n\n"
            f"**자동 충전**: 입금하면 토스 알림이 서버로 전달되어 **자동으로 충전됩니다!** (보통 1~2분 내)\n\n"
            f"**3분 후에도 자동 충전이 안 되면** 봇이 DM으로 알려드립니다!\n\n"
            f"**{expire_minutes}분 후에도 충전되지 않았다면**\n"
            f"입금 완료 사진(스크린샷)을 **이 봇의 DM으로 보내주세요** → 관리자가 확인 후 승인해드립니다.\n\n"
            f"**자동 충전이 이미 완료됐다면 사진을 보내지 마세요!** (완료된 충전건에는 사진 접수가 차단됩니다)"
        ), inline=False)
        embed.set_footer(text=brand_tag('AUTO CHARGE · MANUAL FALLBACK'))

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # 유저 DM으로 자동 충전 대기 안내 전송 (충전 안 될 때만 사진 접수)
        try:
            user = interaction.user
            dm_embed = discord.Embed(
                title="자동 충전을 기다려주세요!",
                description=(
                    f"**{bank_name} {bank_account} ({bank_holder})** 로 입금하셨나요?\n\n"
                    f"입금 알림이 서버에 도착하면 **자동으로 충전됩니다!** (보통 1~2분 내)\n\n"
                    f"**{expire_minutes}분 후에도 충전되지 않으면**, 아래 방법으로 입금 완료 사진을 보내주세요.\n"
                    f"관리자가 확인 후 수동으로 승인해드립니다."
                ),
                color=brand_color('info')
            )
            dm_embed.add_field(name="▸ 요청번호", value=f"#{rid}", inline=True)
            dm_embed.add_field(name="▸ 입금자명", value=depositor_name, inline=True)
            dm_embed.add_field(name="▸ 충전 금액", value=f"{amount:,}원 → {amount:,}포인트", inline=True)
            dm_embed.add_field(
                name="수동 승인 방법 (자동 충전이 안 됐을 때만)",
                value=(
                    "1. 입금 완료 화면을 캡처합니다.\n"
                    "2. 이 DM에 사진을 첨부해 전송합니다.\n"
                    "3. 관리자 확인 후 포인트가 지급됩니다.\n\n"
                    "자동 충전이 이미 완료됐다면 사진을 보내지 않아도 됩니다."
                ),
                inline=False
            )
            dm_embed.set_footer(text=brand_tag('AUTO CHARGE'))
            await user.send(embed=dm_embed)
        except Exception as e:
            logger.error(f"[충전] 안내 DM 전송 실패 (유저 {interaction.user.id}): {e}")


class BuyProductView(discord.ui.View):
    """Product selection view for purchasing"""
    def __init__(self, products):
        super().__init__(timeout=120)
        self.products = products
        # Discord UI row는 0~4까지만 허용 (각 row당 최대 5개 버튼)
        # 상품이 25개를 초과하면 추가 버튼을 이전 row에 몰아서 배치
        for i, p in enumerate(products):
            # 5개씩 row 0~4에 분배 (최대 25개 표시)
            row = min(i // 5, 4)
            self.add_item(BuyButton(p, row=row))
            # 상품이 25개 이상이면 나머지는 더 이상 추가하지 않음
            if i >= 24:
                break


class BuyButton(discord.ui.Button):
    def __init__(self, product, row=0):
        stock = db.count_available_keys(product['id'])
        disabled = stock <= 0 or not product['active']
        label = f"{product['name']} - {product['price']:,}원"
        if stock <= 0:
            label = f"{product['name']} (품절)"
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary if stock > 0 else discord.ButtonStyle.secondary,
            custom_id=f"buy_confirm_{product['id']}",
            disabled=disabled,
            row=row
        )
        self.product = product
    
    async def callback(self, interaction: discord.Interaction):
        # 재고 확인 (쿠폰 사용을 막지 않도록 잔액은 여기서 차단하지 않는다)
        stock = db.count_available_keys(self.product['id'])
        if stock <= 0:
            await interaction.response.send_message(NO_STOCK_TEXT, ephemeral=True)
            return

        balance = db.get_balance(str(interaction.user.id))
        price = self.product['price']
        note = ""
        if balance < price:
            note = (
                f"\n\n보유 포인트: **{balance:,}P** (정가 {price:,}P)\n"
                f"-# 할인 쿠폰을 사용하면 할인된 금액으로 결제할 수 있습니다."
            )

        # Confirm purchase
        desc_line = product_desc(self.product, 120)
        await interaction.response.send_message(
            f"**{self.product['name']}** - {price:,}포인트\n"
            + (f"{desc_line}\n" if desc_line else "")
            + f"\n구매를 진행하시겠습니까?\n"
            f"쿠폰이 있다면 **쿠폰 사용** 버튼을 눌러 할인받으세요! (없으면 바로 구매 확정){note}",
            view=ConfirmBuyView(self.product),
            ephemeral=True
        )


class ConfirmBuyView(discord.ui.View):
    """Confirm purchase view (쿠폰 할인 지원)"""
    def __init__(self, product, coupon=None):
        super().__init__(timeout=60)
        self.product = product
        self.coupon = coupon
        self.add_item(ConfirmBuyButton(product, confirm=True, row=0, coupon=coupon))
        self.add_item(CouponApplyButton(product, row=0))
        self.add_item(ConfirmBuyButton(product, confirm=False, row=0))


class ConfirmBuyButton(discord.ui.Button):
    def __init__(self, product, confirm=True, row=0, coupon=None):
        if confirm:
            super().__init__(
                label="구매 확정",
                style=discord.ButtonStyle.success,
                custom_id=f"confirm_yes_{product['id']}",
                row=row
            )
        else:
            super().__init__(
                label="취소",
                style=discord.ButtonStyle.secondary,
                custom_id=f"confirm_no_{product['id']}",
                row=row
            )
        self.product = product
        self.is_confirm = confirm
        self.coupon = coupon
    
    def get_final_price(self):
        """쿠폰 할인이 적용된 최종 가격"""
        price = self.product['price']
        if self.coupon:
            price = max(0, price - self.coupon['discount_amount'])
        return price
    
    async def callback(self, interaction: discord.Interaction):
        if not self.is_confirm:
            await interaction.response.edit_message(content="구매가 취소되었습니다.", embed=None, view=None)
            return
        
        # Double check balance and stock (쿠폰 할인 적용 가격 기준)
        final_price = self.get_final_price()
        balance = db.get_balance(str(interaction.user.id))
        if balance < final_price:
            await interaction.response.edit_message(
                content=(
                    f"포인트가 부족합니다! (부족액: **{final_price - balance:,}포인트**)\n"
                    f"> 필요 **{final_price:,}P** · 보유 **{balance:,}P**\n"
                    f"-# **충전** 버튼으로 충전한 뒤 다시 시도해주세요."
                ),
                embed=None, view=None
            )
            return
        
        stock = db.count_available_keys(self.product['id'])
        if stock <= 0:
            await interaction.response.edit_message(content=NO_STOCK_TEXT, embed=None, view=None)
            return
        
        # Deduct balance (쿠폰 할인 적용)
        coupon_desc = f" (쿠폰 {self.coupon['code']} -{self.coupon['discount_amount']:,})" if self.coupon else ""
        if final_price > 0:
            success = db.deduct_balance(
                str(interaction.user.id),
                final_price,
                trans_type='purchase',
                description=f"{self.product['name']} 구매{coupon_desc}"
            )

            if not success:
                await interaction.response.edit_message(content="결제에 실패했습니다.", embed=None, view=None)
                return
        
        # Create order and complete immediately (points purchase = instant)
        order_id = db.create_order(
            str(interaction.user.id),
            interaction.user.name,
            self.product['id'],
            self.product['name'],
            final_price
        )
        
        # Get key and complete
        key = db.get_available_key(self.product['id'])
        if not key:
            # Refund
            db.add_balance(str(interaction.user.id), interaction.user.name, final_price, 'refund', '재고 소진 환불')
            db.update_order_status(order_id, 'cancelled')
            await interaction.response.edit_message(content="재고가 소진되어 환불되었습니다.", embed=None, view=None)
            return
        
        conn = db.get_conn()
        c = conn.cursor()
        c.execute('UPDATE keys SET used=1, order_id=? WHERE id=?', (order_id, key['id']))
        conn.commit()
        conn.close()
        
        db.update_order_status(order_id, 'completed', key_id=key['id'])
        
        # 쿠폰 사용 처리 (사용 횟수 +1)
        if self.coupon:
            db.use_coupon(self.coupon['id'])
        
        # ===== 구매 완료 DM (카드 이미지 + KEY/파일) =====
        dm_title = db.get_setting('purchase_dm_title', '구매 완료')
        dm_desc = db.get_setting('purchase_dm_desc', '**{product}** 구매가 완료되었습니다!')
        dm_footer = db.get_setting('purchase_dm_footer', BRAND_FOOTER)

        discount_value = self.coupon['discount_amount'] if self.coupon else 0
        card_png = await render_purchase_card(
            self.product['name'],
            self.product.get('category', ''),
            final_price,
            interaction.user.display_name,
            order_id,
            interaction.user.id,
            discount=discount_value,
            description=self.product.get('description', ''),
        )

        files = []
        content = None
        key_file = build_key_attachment(key)
        if card_png:
            files.append(discord.File(io.BytesIO(card_png), filename='receipt.png'))
            embed = discord.Embed(color=brand_color('success'))
            embed.set_image(url='attachment://receipt.png')
            embed.set_footer(text=dm_footer)
            if key_file:
                files.append(key_file)
            elif (key.get('key_value') or '').strip():
                content = "**YOUR KEY**\n```\n%s\n```" % key['key_value']
        else:
            embed = discord.Embed(
                title=dm_title,
                description=dm_desc.replace('{product}', self.product['name']),
                color=brand_color('success')
            )
            embed.add_field(name="▸ 주문번호", value=f"`#{order_id}`", inline=True)
            embed.add_field(name="▸ 상품", value=self.product['name'], inline=True)
            if self.coupon:
                embed.add_field(name="▸ 원래 가격", value=f"{self.product['price']:,}P", inline=True)
                embed.add_field(name=f"▸ 할인 ({self.coupon['code']})", value=f"-{self.coupon['discount_amount']:,}P", inline=True)
            embed.add_field(name="▸ 결제 금액", value=f"**{final_price:,}P**", inline=True)
            key_file = add_key_fields_to_embed(embed, key)
            if key_file:
                files.append(key_file)
            embed.set_footer(text=dm_footer)

        await interaction.client.send_dm(
            interaction.user.id, content=content, embed=embed, files=files
        )
        
        new_balance = db.get_balance(str(interaction.user.id))
        
        discount_text = f"\n쿠폰 할인: -{self.coupon['discount_amount']:,}포인트 ({self.coupon['code']})" if self.coupon else ""
        deliver_label = 'FILE' if key_file else 'KEY'
        await interaction.response.edit_message(
            content=(
                "**PURCHASE COMPLETE**\n\n"
                f"> **상품** · {self.product['name']}\n"
                f"> **결제** · {final_price:,}P{discount_text}\n"
                f"> **잔액** · {new_balance:,}P\n"
                f"> **{deliver_label}** · DM으로 전송되었습니다"
            ),
            embed=None, view=None
        )
        
        # Send purchase log to purchase log channel
        from datetime import datetime
        purchase_log_channel_id = db.get_setting('purchase_log_channel_id', '')
        if purchase_log_channel_id and interaction.client.is_ready():
            try:
                channel = interaction.client.get_channel(int(purchase_log_channel_id))
                if channel:
                    embed_log = discord.Embed(
                        title="구매 완료",
                        description=f"**{interaction.user.name}** 님이 상품을 구매했습니다!",
                        color=brand_color('info'),
                        timestamp=discord.utils.utcnow()
                    )
                    embed_log.add_field(name="주문번호", value=f"#{order_id}", inline=True)
                    embed_log.add_field(name="구매자", value=f"{interaction.user.mention} ({interaction.user.name})", inline=True)
                    embed_log.add_field(name="상품", value=self.product['name'], inline=True)
                    if self.coupon:
                        embed_log.add_field(name="쿠폰 할인", value=f"{self.coupon['code']} (-{self.coupon['discount_amount']:,})", inline=True)
                    embed_log.add_field(name="결제 금액", value=f"{final_price:,}포인트", inline=True)
                    embed_log.add_field(name="구매 시간", value=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), inline=True)
                    embed_log.set_footer(text=brand_tag('PURCHASE LOG'))
                    if card_png:
                        embed_log.set_image(url='attachment://purchase-log.png')
                        await channel.send(
                            embed=embed_log,
                            file=discord.File(io.BytesIO(card_png), filename='purchase-log.png')
                        )
                    else:
                        await channel.send(embed=embed_log)
            except Exception as e:
                logger.error(f"Purchase log channel error: {e}")
        
        # 구매 완료 후 역할 자동 지급
        try:
            if interaction.guild:
                await interaction.client.grant_purchase_role(interaction.user, self.product['name'])
        except Exception as e:
            logger.error(f"Purchase role grant error: {e}")
        
        # 후기 요청 DM 전송
        try:
            await interaction.client.request_review_dm(interaction.user.id, order_id, self.product['name'])
        except Exception as e:
            logger.error(f"Review request DM error: {e}")
        
        # Refresh vending machine stock
        await interaction.client.refresh_vending_machines()


class CouponApplyButton(discord.ui.Button):
    """구매 확인창에서 쿠폰 코드 입력 버튼"""
    def __init__(self, product, row=0):
        super().__init__(
            label="쿠폰 사용",
            style=discord.ButtonStyle.primary,
            custom_id=f"coupon_apply_{product['id']}",
            row=row
        )
        self.product = product
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CouponModal(self.product))


class CouponModal(discord.ui.Modal):
    """쿠폰 코드 입력 모달 - 유효한 쿠폰이면 할인 적용된 구매창으로 갱신"""
    def __init__(self, product):
        super().__init__(title="할인 쿠폰 입력")
        self.product = product
        
        self.code = discord.ui.TextInput(
            label="쿠폰 코드",
            placeholder="쿠폰 코드를 입력하세요 (예: WELCOME1000)",
            required=True,
            max_length=50
        )
        self.add_item(self.code)
    
    async def on_submit(self, interaction: discord.Interaction):
        code = self.code.value.strip()
        coupon = db.get_coupon_by_code(code)
        
        if not coupon:
            await interaction.response.send_message(
                "유효하지 않은 쿠폰 코드입니다.\n"
                "(존재하지 않거나, 비활성화되었거나, 사용 횟수가 모두 소진된 쿠폰입니다.)",
                ephemeral=True
            )
            return
        
        discount = coupon['discount_amount']
        final_price = max(0, self.product['price'] - discount)
        balance = db.get_balance(str(interaction.user.id))

        desc_line = product_desc(self.product, 120)
        content = (
            f"**{self.product['name']}**\n"
            + (f"{desc_line}\n" if desc_line else "")
            + f"\n원래 가격: ~~{self.product['price']:,}포인트~~\n"
            f"쿠폰 할인: **-{discount:,}포인트** ({coupon['code']})\n"
            f"결제 금액: **{final_price:,}포인트**\n"
            f"보유 포인트: **{balance:,}P**\n"
        )
        if balance < final_price:
            content += (
                f"\n포인트가 **{final_price - balance:,}P** 부족합니다.\n"
                f"-# 충전 후 **쿠폰 사용**을 다시 눌러 할인을 적용하세요."
            )
        else:
            content += "\n구매를 진행하시겠습니까?"

        await interaction.response.edit_message(content=content, view=ConfirmBuyView(self.product, coupon))


class BulkPointsConfirmView(discord.ui.View):
    """전체 포인트 지급/차감 실행 확인 뷰"""
    def __init__(self, kind, amount):
        super().__init__(timeout=60)
        self.kind = kind    # 'add' 또는 'remove'
        self.amount = amount
        self.add_item(BulkPointsConfirmButton(confirm=True))
        self.add_item(BulkPointsConfirmButton(confirm=False))


class BulkPointsConfirmButton(discord.ui.Button):
    """전체 포인트 지급/차감 실행 버튼"""
    def __init__(self, confirm):
        if confirm:
            super().__init__(
                label="실행",
                style=discord.ButtonStyle.success,
                custom_id="bulk_points_confirm_yes",
                row=0
            )
        else:
            super().__init__(
                label="취소",
                style=discord.ButtonStyle.secondary,
                custom_id="bulk_points_confirm_no",
                row=0
            )
        self.confirm = confirm

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not view or view.amount <= 0:
            await interaction.response.edit_message(content="유효하지 않은 요청입니다.", embed=None, view=None)
            return

        # 안전장치: 관리자만 실행 가능 (버튼은 명령 실행자에게만 보이지만 이중 확인)
        if not db.is_admin(str(interaction.user.id)):
            await interaction.response.send_message("관리자만 실행할 수 있습니다.", ephemeral=True)
            return

        if not self.confirm:
            await interaction.response.edit_message(content="취소되었습니다.", embed=None, view=None)
            return

        # 대량 유저 처리 시 3초 제한 초과를 피하기 위해 defer 후 followup으로 처리
        await interaction.response.defer()

        amount = view.amount
        kind = view.kind
        try:
            if kind == 'add':
                affected = db.add_balance_all(
                    amount,
                    trans_type='admin_add',
                    description=f"관리자 {interaction.user.name}님이 전체 지급 {amount:,}포인트"
                )
                embed = discord.Embed(
                    title="전체 포인트 지급 완료",
                    description=f"**{affected}명**의 유저에게 각각 **{amount:,}포인트**가 지급되었습니다!",
                    color=brand_color('success')
                )
            elif kind == 'remove':
                affected, total_deducted = db.deduct_balance_all(
                    amount,
                    trans_type='admin_remove',
                    description=f"관리자 {interaction.user.name}님이 전체 차감 {amount:,}포인트"
                )
                desc = f"**{affected}명**의 유저에게서 총 **{total_deducted:,}포인트**가 차감되었습니다."
                if amount > total_deducted:
                    desc += "\n(잔액이 부족한 유저는 보유 잔액까지만 차감되었습니다)"
                embed = discord.Embed(
                    title="전체 포인트 차감 완료",
                    description=desc,
                    color=brand_color('success')
                )
            else:
                await interaction.followup.edit_message(content="잘못된 작업입니다.", embed=None, view=None)
                return
            embed.set_footer(text=f"실행자: {interaction.user.name}")
            await interaction.followup.edit_message(embed=embed, view=None)
        except Exception as e:
            logger.error(f"Bulk points execute error: {e}")
            await interaction.followup.edit_message(
                content=f"실행 중 오류가 발생했습니다: {e}",
                embed=None, view=None
            )



class InquiryModal(discord.ui.Modal, title="문의 접수"):
    reason = discord.ui.TextInput(label="문의 내용", style=discord.TextStyle.paragraph,
                                  placeholder="문의 내용을 자세히 적어주세요", required=True, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        category_id = (db.get_setting('ticket_category_id', '') or '').strip()
        category = interaction.client.get_channel(int(category_id)) if category_id else None
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send("문의 카테고리가 설정되지 않았습니다. 관리자에게 문의해 주세요.", ephemeral=True)
            return
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True, read_message_history=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True, read_message_history=True),
        }
        try:
            for a in db.get_admins():
                m = interaction.guild.get_member(int(a['user_id']))
                if m:
                    overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True, read_message_history=True)
        except Exception:
            pass
        try:
            ch = await category.create_text_channel(name=f"문의-{interaction.user.name}"[:90], overwrites=overwrites)
            e = discord.Embed(title="문의 접수", description=self.reason.value[:1000], color=brand_color('info'))
            e.add_field(name="작성자", value=interaction.user.mention, inline=True)
            e.set_footer(text=brand_tag('INQUIRY'))
            await ch.send(content=interaction.user.mention, embed=e)
            await interaction.followup.send(f"문의가 접수되었습니다: {ch.mention}", ephemeral=True)
        except Exception as ex:
            logger.error(f"[INQUIRY] 티켓 생성 실패: {ex}")
            await interaction.followup.send(f"문의 접수에 실패했습니다: {ex}", ephemeral=True)


class InquiryPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="문의하기", style=discord.ButtonStyle.primary, custom_id="inquiry_open_btn")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InquiryModal())


class VendingCommands(commands.Cog):
    def __init__(self, bot: VendingBot):
        self.bot = bot
    
    def is_admin_check(self, interaction: discord.Interaction) -> bool:
        if not db.get_admins():
            db.add_admin(str(interaction.user.id), interaction.user.name)
            return True
        return db.is_admin(str(interaction.user.id))
    
    # ============ ADMIN COMMANDS ============
    
    @app_commands.command(name="문의패널", description="[관리자] 문의 패널을 현재 채널에 생성합니다")
    async def inquiry_panel(self, interaction: discord.Interaction):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="문의 접수",
            description="아래 **문의하기** 버튼을 눌러 문의 내용을 작성해 주세요.\n접수된 문의는 비공개 채널에서 처리됩니다.",
            color=brand_color('main')
        )
        embed.set_footer(text=brand_tag('INQUIRY'))
        await interaction.channel.send(embed=embed, view=InquiryPanelView())
        await interaction.followup.send("문의 패널을 생성했습니다.", ephemeral=True)

    @app_commands.command(name="자판기설정", description="[관리자] 현재 채널에 버튼 자판기를 설치합니다")
    async def setup_vending(self, interaction: discord.Interaction):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.update_vending_machine(interaction.channel)
            await interaction.followup.send(f"버튼 자판기가 설치되었습니다! (버전: {BOT_VERSION})", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "봇에게 메시지 보내기 권한이 없습니다!\n\n"
                "**해결 방법 (봇 재초대):**\n"
                "아래 링크로 봇을 다시 초대하면 모든 권한이 포함됩니다.\n\n"
                f"https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&permissions=8&scope=bot+applications.commands",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Setup vending error: {e}")
            await interaction.followup.send(
                f"자판기 설치 중 오류가 발생했습니다 (실행 중 버전: {BOT_VERSION}): {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="자판기새로고침", description="[관리자] 자판기 메시지를 새로고침합니다")
    async def refresh_vending(self, interaction: discord.Interaction):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        await self.bot.refresh_vending_machines(force_edit=True)
        await interaction.followup.send("자판기가 새로고침되었습니다!", ephemeral=True)
    
    @app_commands.command(name="포인트지급", description="[관리자] 유저에게 포인트를 지급합니다")
    @app_commands.describe(user="포인트를 지급할 유저", amount="포인트 금액")
    async def give_points(self, interaction: discord.Interaction, user: discord.User, amount: int):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        if amount <= 0:
            await interaction.response.send_message("0보다 큰 금액을 입력해주세요.", ephemeral=True)
            return
        
        new_balance = db.add_balance(
            str(user.id), user.name, amount,
            trans_type='admin_add',
            description=f"관리자 {interaction.user.name}님이 {amount:,}포인트 지급"
        )
        
        # Notify user via DM
        embed = discord.Embed(
            title="포인트 충전 완료!",
            description=f"{amount:,}포인트가 충전되었습니다!",
            color=brand_color('success')
        )
        embed.add_field(name="충전 포인트", value=f"{amount:,}포인트", inline=True)
        embed.add_field(name="현재 잔액", value=f"{new_balance:,}포인트", inline=True)
        embed.set_footer(text=brand_tag('POINT'))
        await self.bot.send_dm(user.id, embed=embed)
        
        await interaction.response.send_message(
            f"{user.mention} 님에게 {amount:,}포인트가 지급되었습니다!\n"
            f"현재 잔액: {new_balance:,}포인트",
            ephemeral=True
        )
    
    @app_commands.command(name="포인트차감", description="[관리자] 유저의 포인트를 차감합니다")
    @app_commands.describe(user="포인트를 차감할 유저", amount="차감할 포인트 금액")
    async def remove_points(self, interaction: discord.Interaction, user: discord.User, amount: int):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        if amount <= 0:
            await interaction.response.send_message("0보다 큰 금액을 입력해주세요.", ephemeral=True)
            return
        
        success = db.deduct_balance(
            str(user.id), amount,
            trans_type='admin_remove',
            description=f"관리자 {interaction.user.name}님이 {amount:,}포인트 차감"
        )
        
        if not success:
            await interaction.response.send_message("유저의 포인트가 부족합니다.", ephemeral=True)
            return
        
        new_balance = db.get_balance(str(user.id))
        
        await interaction.response.send_message(
            f"{user.mention} 님의 {amount:,}포인트가 차감되었습니다!\n"
            f"현재 잔액: {new_balance:,}포인트",
            ephemeral=True
        )
    
    @app_commands.command(name="전체포인트지급", description="[관리자] 등록된 모든 유저에게 동일한 포인트를 지급합니다")
    @app_commands.describe(amount="모든 유저에게 지급할 포인트 금액")
    async def give_points_all(self, interaction: discord.Interaction, amount: int):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("0보다 큰 금액을 입력해주세요.", ephemeral=True)
            return

        total_users = len(db.get_users())
        if total_users == 0:
            await interaction.response.send_message("등록된 유저가 없습니다. 먼저 유저가 봇을 사용해야 합니다.", ephemeral=True)
            return

        embed = discord.Embed(
            title="전체 포인트 지급 확인",
            description=(
                f"**{total_users}명**의 모든 유저에게 각각 **{amount:,}포인트**를 지급합니다.\n"
                f"총 지급 예정: **{total_users * amount:,}포인트**\n\n"
                f"정말 실행하시겠습니까?"
            ),
            color=brand_color('success')
        )
        embed.set_footer(text="이 버튼은 실행한 관리자만 볼 수 있습니다")
        await interaction.response.send_message(embed=embed, view=BulkPointsConfirmView('add', amount), ephemeral=True)
    
    @app_commands.command(name="전체포인트차감", description="[관리자] 등록된 모든 유저의 포인트를 동일하게 차감합니다")
    @app_commands.describe(amount="모든 유저에게서 차감할 포인트 금액")
    async def remove_points_all(self, interaction: discord.Interaction, amount: int):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("0보다 큰 금액을 입력해주세요.", ephemeral=True)
            return

        total_users = len(db.get_users())
        if total_users == 0:
            await interaction.response.send_message("등록된 유저가 없습니다. 먼저 유저가 봇을 사용해야 합니다.", ephemeral=True)
            return

        embed = discord.Embed(
            title="전체 포인트 차감 확인",
            description=(
                f"**{total_users}명**의 모든 유저에게서 각각 **{amount:,}포인트**를 차감합니다.\n"
                f"(잔액이 **0 미만으로 내려가지는 않습니다**)\n\n"
                f"정말 실행하시겠습니까?"
            ),
            color=brand_color('warn')
        )
        embed.set_footer(text="이 버튼은 실행한 관리자만 볼 수 있습니다")
        await interaction.response.send_message(embed=embed, view=BulkPointsConfirmView('remove', amount), ephemeral=True)
    
    @app_commands.command(name="잔액확인", description="[관리자] 유저의 포인트 잔액을 확인합니다")
    @app_commands.describe(user="잔액을 확인할 유저")
    async def check_balance(self, interaction: discord.Interaction, user: discord.User):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        balance = db.get_balance(str(user.id))
        user_data = db.get_user(str(user.id))
        
        embed = discord.Embed(
            title="포인트 잔액 확인",
            color=brand_color('info')
        )
        embed.add_field(name="유저", value=user.mention, inline=True)
        embed.add_field(name="잔액", value=f"**{balance:,}포인트**", inline=True)
        if user_data:
            embed.add_field(name="가입일", value=user_data['created_at'], inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="수동확인", description="[관리자] 주문을 수동으로 확인합니다")
    @app_commands.describe(order_id="확인할 주문번호")
    async def manual_confirm(self, interaction: discord.Interaction, order_id: int):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        success, msg = await self.bot.confirm_order(order_id)
        await interaction.followup.send(msg, ephemeral=True)
    
    @app_commands.command(name="주문취소", description="[관리자] 주문을 취소합니다")
    @app_commands.describe(order_id="취소할 주문번호")
    async def cancel_order(self, interaction: discord.Interaction, order_id: int):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        success, msg = await self.bot.cancel_order(order_id)
        await interaction.followup.send(msg, ephemeral=True)
    
    @app_commands.command(name="대기주문", description="[관리자] 대기 중인 주문 목록을 확인합니다")
    async def pending_orders(self, interaction: discord.Interaction):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        pending = db.get_pending_orders()
        if not pending:
            await interaction.response.send_message("대기 중인 주문이 없습니다.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"대기 중인 주문 ({len(pending)}건)",
            color=brand_color('warn')
        )
        for o in pending[:10]:
            embed.add_field(
                name=f"#{o['id']} - {o['username']}",
                value=f"{o['product_name']} | {o['amount']:,}원 | {o['created_at']}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="상품추가", description="[관리자] 상품을 추가합니다")
    @app_commands.describe(name="상품명", price="가격(포인트)", description="설명", category="카테고리")
    async def add_product(self, interaction: discord.Interaction, name: str, price: int, description: str = "", category: str = ""):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        db.add_product(name, price, description, category=category)
        cat_text = f"\n카테고리: {category}" if category else ""
        await interaction.response.send_message(
            f"상품이 추가되었습니다!\n**{name}** - {price:,}포인트{cat_text}", ephemeral=True)
        await self.bot.refresh_vending_machines()
    
    @app_commands.command(name="상품삭제", description="[관리자] 상품을 삭제합니다")
    @app_commands.describe(product_id="삭제할 상품 ID")
    async def delete_product(self, interaction: discord.Interaction, product_id: int):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        product = db.get_product(product_id)
        if not product:
            await interaction.response.send_message("상품을 찾을 수 없습니다.", ephemeral=True)
            return
        
        db.delete_product(product_id)
        await interaction.response.send_message(
            f"상품이 삭제되었습니다!\n**{product['name']}** - {product['price']:,}포인트",
            ephemeral=True
        )
        await self.bot.refresh_vending_machines()
    
    @app_commands.command(name="키추가", description="[관리자] 상품에 텍스트 키를 추가합니다")
    @app_commands.describe(product_id="상품 ID", keys="키 목록 (줄바꿈으로 구분)")
    async def add_keys(self, interaction: discord.Interaction, product_id: int, keys: str):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        product = db.get_product(product_id)
        if not product:
            await interaction.response.send_message("상품을 찾을 수 없습니다.", ephemeral=True)
            return
        
        key_list = [k.strip() for k in keys.split('\n') if k.strip()]
        if not key_list:
            await interaction.response.send_message("키를 한 개 이상 입력해주세요.", ephemeral=True)
            return
        
        count = db.add_keys(product_id, key_list)
        await interaction.response.send_message(
            f"**{product['name']}**에 키 **{count}개**가 추가되었습니다!\n"
            f"-# 파일(.txt)로 판매하려면 `/파일추가` 명령어를 사용하세요.",
            ephemeral=True)
        await self.bot.refresh_vending_machines()
        
        # 입고 채널에 공지 전송
        await self.bot.send_stock_notice(product, count)
    
    @app_commands.command(name="파일추가", description="[관리자] 상품에 파일(txt 등)을 재고로 추가합니다 (파일 1개 = 재고 1개)")
    @app_commands.describe(
        product_id="상품 ID",
        file="등록할 파일 (.txt 권장)",
        file2="추가로 등록할 파일 (선택)",
        file3="추가로 등록할 파일 (선택)"
    )
    async def add_key_files_cmd(self, interaction: discord.Interaction, product_id: int,
                                file: discord.Attachment,
                                file2: discord.Attachment = None,
                                file3: discord.Attachment = None):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        product = db.get_product(product_id)
        if not product:
            await interaction.response.send_message("상품을 찾을 수 없습니다.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        attachments = [a for a in (file, file2, file3) if a is not None]
        entries = []
        skipped = []
        for att in attachments:
            if att.size and att.size > MAX_KEY_FILE_BYTES:
                skipped.append(f"{att.filename} ({human_size(MAX_KEY_FILE_BYTES)} 초과)")
                continue
            try:
                data = await att.read()
            except Exception as e:
                logger.error(f"[파일추가] 첨부 읽기 실패 {att.filename}: {e}")
                skipped.append(f"{att.filename} (읽기 실패)")
                continue
            if not data:
                skipped.append(f"{att.filename} (빈 파일)")
                continue
            entries.append((att.filename, data))
        
        if not entries:
            msg = "등록할 수 있는 파일이 없습니다."
            if skipped:
                msg += "\n" + "\n".join(f"· {s}" for s in skipped)
            await interaction.followup.send(msg, ephemeral=True)
            return
        
        count = db.add_key_files(product_id, entries)
        lines = [
            f"**{product['name']}**에 파일 재고 **{count}개**가 추가되었습니다!",
            "-# " + ", ".join(f"{name} ({human_size(len(data))})" for name, data in entries),
            "-# 구매 시 해당 파일이 DM 첨부파일로 전송됩니다.",
        ]
        if skipped:
            lines.append("제외된 파일: " + ", ".join(skipped))
        await interaction.followup.send("\n".join(lines), ephemeral=True)
        
        await self.bot.refresh_vending_machines()
        await self.bot.send_stock_notice(product, count)

        # 새로 등록한 파일은 바로 쿠키 검사 (검사 전에는 판매되지 않음)
        try:
            self.bot.loop.create_task(self.bot.check_all_cookies())
        except Exception as e:
            logger.warning(f"[쿠키검사] 등록 직후 검사 예약 실패: {e}")
    
    @app_commands.command(name="쿠키검사", description="[관리자] 파일 재고의 로블록스 쿠키 유효성을 지금 바로 검사합니다")
    async def check_cookies_cmd(self, interaction: discord.Interaction):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        stats = await self.bot.check_all_cookies()
        if not stats['total']:
            await interaction.followup.send("검사할 파일 재고가 없습니다.", ephemeral=True)
            return

        await interaction.followup.send(
            "**쿠키 검사 완료**\n"
            f"> 검사 **{stats['checked']}**개 · 유효 **{stats['valid']}** · "
            f"무효 **{stats['invalid']}** · 판단불가 **{stats['unknown']}**\n"
            f"> 이번에 새로 판매 제외된 쿠키 **{len(stats['newly_invalid'])}**개\n"
            f"-# 주기 설정: 대시보드 → 설정 → 쿠키 검사 주기 (기본 3분)",
            ephemeral=True
        )

    @app_commands.command(name="카테고리토글", description="[관리자] 카테고리 사용 여부를 전환합니다")
    @app_commands.describe(enabled="사용 여부 (true/false)")
    async def toggle_categories(self, interaction: discord.Interaction, enabled: bool):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        db.set_setting('use_categories', str(enabled))
        status = "활성화" if enabled else "비활성화"
        await interaction.response.send_message(
            f"카테고리 기능이 **{status}**되었습니다!", ephemeral=True)
        await self.bot.refresh_vending_machines()
    
    # ============ COUPON COMMANDS (할인 쿠폰) ============
    
    @app_commands.command(name="쿠폰생성", description="[관리자] 할인 쿠폰을 생성합니다")
    @app_commands.describe(code="쿠폰 코드 (예: WELCOME1000)", discount_amount="할인 금액(포인트)", max_uses="최대 사용 횟수 (0=무제한)")
    async def create_coupon_cmd(self, interaction: discord.Interaction, code: str, discount_amount: int, max_uses: int = 0):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        if discount_amount <= 0:
            await interaction.response.send_message("할인 금액은 0보다 커야 합니다.", ephemeral=True)
            return
        if max_uses < 0:
            await interaction.response.send_message("최대 사용 횟수는 0 이상이어야 합니다.", ephemeral=True)
            return
        
        cid = db.create_coupon(code, discount_amount, max_uses)
        if cid == -1:
            await interaction.response.send_message(
                f"이미 존재하는 쿠폰 코드입니다: **{code.strip().upper()}**",
                ephemeral=True
            )
            return
        
        uses_text = f"{max_uses}회" if max_uses > 0 else "무제한"
        await interaction.response.send_message(
            f"쿠폰이 생성되었습니다!\n\n"
            f"코드: **{code.strip().upper()}**\n"
            f"할인: **{discount_amount:,}포인트**\n"
            f"사용 가능: **{uses_text}**",
            ephemeral=True
        )
    
    @app_commands.command(name="쿠폰목록", description="[관리자] 등록된 쿠폰 목록을 확인합니다")
    async def coupon_list_cmd(self, interaction: discord.Interaction):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        coupons = db.get_coupons()
        if not coupons:
            await interaction.response.send_message("등록된 쿠폰이 없습니다.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"할인 쿠폰 목록 ({len(coupons)}개)",
            color=brand_color('main')
        )
        for cp in coupons[:15]:
            status = "활성" if cp['active'] else "비활성"
            uses_text = f"{cp['used_count']}/{cp['max_uses']}" if cp['max_uses'] > 0 else f"{cp['used_count']}/무제한"
            embed.add_field(
                name=f"{cp['code']} (-{cp['discount_amount']:,}포인트)",
                value=f"{status} | 사용: {uses_text}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="쿠폰삭제", description="[관리자] 쿠폰을 삭제합니다")
    @app_commands.describe(code="삭제할 쿠폰 코드")
    async def coupon_delete_cmd(self, interaction: discord.Interaction, code: str):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        conn = db.get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM coupons WHERE code=?', (code.strip().upper(),))
        row = c.fetchone()
        conn.close()
        
        if not row:
            await interaction.response.send_message(
                f"존재하지 않는 쿠폰 코드입니다: **{code.strip().upper()}**",
                ephemeral=True
            )
            return
        
        db.delete_coupon(row['id'])
        await interaction.response.send_message(
            f"쿠폰이 삭제되었습니다: **{code.strip().upper()}**",
            ephemeral=True
        )
    
    @app_commands.command(name="공지", description="[관리자] 공지 채널에 임베드 공지를 보냅니다")
    @app_commands.describe(title="공지 제목", content="공지 내용")
    async def send_notice_cmd(self, interaction: discord.Interaction, title: str, content: str):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        success, msg = await self.bot.send_notice(title, content)
        await interaction.followup.send(msg, ephemeral=True)
    
    @app_commands.command(name="관리자추가", description="[관리자] 관리자를 추가합니다")
    @app_commands.describe(user="관리자로 추가할 유저")
    async def add_admin(self, interaction: discord.Interaction, user: discord.User):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        db.add_admin(str(user.id), user.name)
        await interaction.response.send_message(f"{user.mention} 님이 관리자로 추가되었습니다!", ephemeral=True)
    
    @app_commands.command(name="설정확인", description="[관리자] 봇 설정을 확인합니다")
    async def check_settings(self, interaction: discord.Interaction):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        settings = db.get_all_settings()
        embed = discord.Embed(
            title="봇 설정",
            color=brand_color('info')
        )
        embed.add_field(name="봇 이름", value=settings.get('bot_name', 'APEX VENDING'), inline=True)
        embed.add_field(name="입금 계좌", value=settings.get('bank_account', '미설정'), inline=True)
        embed.add_field(name="예금주", value=settings.get('bank_holder', '미설정'), inline=True)
        embed.add_field(name="Tasker 웹훅", value="자동입금 감지 활성" if settings.get('deposit_webhook_key') else "키 미생성 (대시보드 접속 시 자동 생성)", inline=True)
        embed.add_field(name="대시보드 URL", value=settings.get('dashboard_url', '미설정'), inline=True)
        embed.add_field(name="문의 카테고리", value=settings.get('ticket_category_id', '미설정'), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # ============ VENDING MACHINE TEXT EDIT COMMANDS ============
    
    @app_commands.command(name="자판기제목", description="[관리자] 자판기 제목을 변경합니다")
    @app_commands.describe(text="새 제목")
    async def set_vending_title(self, interaction: discord.Interaction, text: str):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        db.set_setting('vending_title', text)
        await interaction.response.send_message(f"자판기 제목이 변경되었습니다!\n**{text}**", ephemeral=True)
        await self.bot.refresh_vending_machines()
    
    @app_commands.command(name="자판기설명", description="[관리자] 자판기 설명을 변경합니다")
    @app_commands.describe(text="새 설명")
    async def set_vending_desc(self, interaction: discord.Interaction, text: str):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        db.set_setting('vending_desc', text)
        await interaction.response.send_message(f"자판기 설명이 변경되었습니다!", ephemeral=True)
        await self.bot.refresh_vending_machines()
    
    @app_commands.command(name="자판기푸터", description="[관리자] 자판기 하단 문구를 변경합니다")
    @app_commands.describe(text="새 하단 문구")
    async def set_vending_footer(self, interaction: discord.Interaction, text: str):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        db.set_setting('vending_footer', text)
        await interaction.response.send_message(f"자판기 하단 문구가 변경되었습니다!\n**{text}**", ephemeral=True)
        await self.bot.refresh_vending_machines()
    
    @app_commands.command(name="자판기색상", description="[관리자] 자판기 임베드 색상을 변경합니다 (예: #ff0000)")
    @app_commands.describe(color="색상 코드 (예: #3498db)")
    async def set_vending_color(self, interaction: discord.Interaction, color: str):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        try:
            color_hex = color.replace('#', '0x')
            int(color_hex, 16)
        except:
            await interaction.response.send_message("올바른 색상 코드를 입력해주세요. (예: #3498db)", ephemeral=True)
            return
        
        db.set_setting('vending_color', color)
        await interaction.response.send_message(f"자판기 색상이 변경되었습니다! ({color})", ephemeral=True)
        await self.bot.refresh_vending_machines()
    
    @app_commands.command(name="자판기상품제목", description="[관리자] 자판기 상품 섹션 제목을 변경합니다")
    @app_commands.describe(text="새 상품 섹션 제목")
    async def set_vending_product_title(self, interaction: discord.Interaction, text: str):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        db.set_setting('vending_product_title', text)
        await interaction.response.send_message(f"상품 섹션 제목이 변경되었습니다!\n**{text}**", ephemeral=True)
        await self.bot.refresh_vending_machines()
    
    # ============ PURCHASE DM MESSAGE EDIT COMMANDS ============
    
    @app_commands.command(name="구매메시지제목", description="[관리자] 구매 완료 DM 제목을 변경합니다")
    @app_commands.describe(text="새 DM 제목")
    async def set_purchase_dm_title(self, interaction: discord.Interaction, text: str):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        db.set_setting('purchase_dm_title', text)
        await interaction.response.send_message(f"구매 완료 DM 제목이 변경되었습니다!\n**{text}**", ephemeral=True)
    
    @app_commands.command(name="구매메시지설명", description="[관리자] 구매 완료 DM 설명을 변경합니다 ({product} = 상품명)")
    @app_commands.describe(text="새 DM 설명")
    async def set_purchase_dm_desc(self, interaction: discord.Interaction, text: str):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        db.set_setting('purchase_dm_desc', text)
        await interaction.response.send_message(f"구매 완료 DM 설명이 변경되었습니다!", ephemeral=True)
    
    @app_commands.command(name="구매메시지푸터", description="[관리자] 구매 완료 DM 하단 문구를 변경합니다")
    @app_commands.describe(text="새 DM 하단 문구")
    async def set_purchase_dm_footer(self, interaction: discord.Interaction, text: str):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        db.set_setting('purchase_dm_footer', text)
        await interaction.response.send_message(f"구매 완료 DM 하단 문구가 변경되었습니다!\n**{text}**", ephemeral=True)
    
    # ============ TICKET SETTINGS ============
    
    @app_commands.command(name="문의카테고리", description="[관리자] 문의 티켓이 생성될 카테고리를 설정합니다")
    @app_commands.describe(category="티켓이 생성될 카테고리")
    async def set_ticket_category(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        db.set_setting('ticket_category_id', str(category.id))
        await interaction.response.send_message(
            f"문의 티켓 카테고리가 설정되었습니다!\n{category.name}",
            ephemeral=True
        )
    
    @app_commands.command(name="문의목록", description="[관리자] 열려있는 문의 티켓 목록을 확인합니다")
    async def ticket_list(self, interaction: discord.Interaction):
        if not self.is_admin_check(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        tickets = db.get_open_tickets()
        if not tickets:
            await interaction.response.send_message("열려있는 문의 티켓이 없습니다.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"열려있는 문의 티켓 ({len(tickets)}건)",
            color=brand_color('info')
        )
        for t in tickets[:10]:
            embed.add_field(
                name=f"#{t['id']} - {t['username']}",
                value=f"상태: 열림 | 생성: {t['created_at']}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)
