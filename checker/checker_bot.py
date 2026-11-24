"""Apex Checker — 구매자용 쿠키 검사 봇 (자판기 패널 방식)

패널을 한 번 게시해두면 구매자는 **버튼만 눌러** 쿠키를 넣고 결과를 받습니다.
슬래시 명령을 외울 필요 없습니다.

환경변수
- CHECKER_TOKEN    : 봇 토큰 (필수)
- BUYER_ROLE_ID    : 이 역할 보유자만 사용 가능
- WEB_BASE_URL     : 결과 웹 주소 (예: https://apex-checker.onrender.com)
- PANEL_CHANNEL_ID : (선택) 시작 시 패널을 자동 게시할 채널 ID
"""
import os
import asyncio
import logging
import datetime

import discord
from discord import app_commands

import database as db
from cookie_parser import summarize, fmt_hours
from game_stats import build_report

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger('checker')


def _load_dotenv():
    """같은 폴더의 .env 파일을 읽어 환경변수로 등록 (없으면 무시)"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

TOKEN = os.environ.get('CHECKER_TOKEN', '').strip()
BUYER_ROLE_ID = os.environ.get('BUYER_ROLE_ID', '').strip()
WEB = (os.environ.get('WEB_BASE_URL', '').strip() or '').rstrip('/')
PANEL_CHANNEL_ID = os.environ.get('PANEL_CHANNEL_ID', '').strip()
GUILD_ID = os.environ.get('GUILD_ID', '').strip()

db.init()


def has_role(member) -> bool:
    if not BUYER_ROLE_ID:
        return True
    if isinstance(member, discord.Member):
        return any(str(r.id) == BUYER_ROLE_ID for r in member.roles)
    return False


def _g(v):
    return '-' if v in (None, '', False) else str(v)


def summary_embed(s: dict, report: dict) -> discord.Embed:
    uid = s.get('user_id')
    head = (f'https://www.roblox.com/headshot-thumbnail/image'
            f'?userId={uid}&width=150&height=150&format=png') if uid else None

    e = discord.Embed(color=0xD4A017, description='')
    title = f"{s.get('username') or '알 수 없음'}"
    if head:
        e.set_author(name=title, icon_url=head)
        e.set_thumbnail(url=head)
    else:
        e.set_author(name=title)

    bal = s.get('balance')
    rap = s.get('rap')
    spent = s.get('total_robux') or 0
    e.description = (f"`ID {uid or '-'}`  ·  `{s.get('premium') or '일반'}`\n"
                     f"잔액 **{f'{bal:,}' if isinstance(bal, int) else '-'}** R$  ·  "
                     f"RAP **{f'{rap:,}' if isinstance(rap, int) else '-'}**  ·  "
                     f"게임 지출 **{spent:,}** R$")

    games = report.get('played_games') or []
    if games:
        top = max((g.get('robux') or 0) for g in games) or 1
        lines = []
        for g in games[:6]:
            rb = g.get('robux') or 0
            filled = max(1, round(rb / top * 10)) if rb else 0
            bar = '▰' * filled + '▱' * (10 - filled)
            lines.append(f"`{bar}` **{g['name'][:22]}** — {rb:,} R$")
        e.add_field(name='게임별 로벅 지출', value='\n'.join(lines)[:1024], inline=False)
    else:
        e.add_field(name='게임별 로벅 지출',
                    value='거래 내역이 없습니다. (게임패스·개발자 상품 구매 기록 기준)',
                    inline=False)

    e.set_footer(text=f"APEX CHECKER · 게임 {s.get('games_played') or 0}종 · 지출 {spent:,} R$")
    return e


async def run_check(interaction: discord.Interaction, cookie: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        res = await asyncio.to_thread(build_report, cookie)
    except Exception as exc:
        log.exception('검사 실패')
        await interaction.followup.send(f'검사 중 오류가 발생했습니다: `{exc}`', ephemeral=True)
        return

    if not res.get('ok'):
        await interaction.followup.send(f"❌ {res.get('error') or '쿠키를 확인할 수 없습니다.'}",
                                        ephemeral=True)
        return

    report = res['report']
    s = summarize(report)
    token = db.save(interaction.user.id, s.get('username') or interaction.user.name, cookie, report)

    view = discord.ui.View()
    if WEB:
        view.add_item(discord.ui.Button(label='웹 리포트', emoji='📊',
                                        style=discord.ButtonStyle.link, url=f'{WEB}/c/{token}'))
    view.add_item(discord.ui.Button(label='다시 검사', emoji='🔄',
                                    style=discord.ButtonStyle.secondary, custom_id='apexck:check'))
    await interaction.followup.send(embed=summary_embed(s, report), view=view, ephemeral=True)


class CookieModal(discord.ui.Modal, title='쿠키 검사'):
    cookie = discord.ui.TextInput(
        label='로블록스 쿠키 (.ROBLOSECURITY)',
        style=discord.TextStyle.paragraph,
        placeholder='_|WARNING:... 값을 그대로 붙여넣어 주세요',
        required=True, max_length=4000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not has_role(interaction.user):
            await interaction.response.send_message('구매자 역할이 있어야 사용할 수 있습니다.',
                                                    ephemeral=True)
            return
        await run_check(interaction, self.cookie.value)


async def send_history(interaction: discord.Interaction):
    rows = db.recent(interaction.user.id, 10)
    if not rows:
        await interaction.response.send_message('검사 기록이 없습니다.', ephemeral=True)
        return
    lines = []
    for r in rows:
        at = datetime.datetime.utcfromtimestamp(r['created_at']).strftime('%m-%d %H:%M')
        lines.append(f"`{at}` **{r['username'] or '-'}** → {WEB}/c/{r['token']}")
    await interaction.response.send_message('\n'.join(lines)[:1900], ephemeral=True)


HELP_TEXT = (
    "**🍪 Apex 쿠키 검사기 사용법**\n"
    "1\\. 아래 **쿠키 검사** 버튼을 누릅니다.\n"
    "2\\. 쿠키(`_|WARNING:...`)를 그대로 붙여넣고 제출합니다.\n"
    "3\\. 몇 초 뒤 계정 정보와 게임별 로벅 지출이 표시됩니다.\n\n"
    "**보안 안내**\n"
    "· 검사 결과는 본인에게만 보입니다.\n"
    "· 검사 후 Roblox 세션 로그아웃을 권장합니다."
)


class Panel(discord.ui.View):
    """자판기형 상시 패널 — 드롭다운 + 버튼 (봇 재시작 후에도 유지)"""

    def __init__(self):
        super().__init__(timeout=None)

    async def _dispatch(self, interaction: discord.Interaction, action: str):
        if not has_role(interaction.user):
            await interaction.response.send_message(
                '이 패널은 **구매자** 역할 보유자만 사용할 수 있습니다.', ephemeral=True)
            return
        if action == 'check':
            await interaction.response.send_modal(CookieModal())
        elif action == 'hist':
            await send_history(interaction)
        elif action == 'help':
            await interaction.response.send_message(HELP_TEXT, ephemeral=True)
        else:
            await interaction.response.send_message(
                f'웹 리포트: {WEB}' if WEB else '웹 주소가 설정되지 않았습니다.', ephemeral=True)

    @discord.ui.button(label='쿠키 검사', emoji='🍪', style=discord.ButtonStyle.primary,
                       custom_id='apexck:check')
    async def check_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._dispatch(interaction, 'check')

    @discord.ui.button(label='내 기록', emoji='📜', style=discord.ButtonStyle.success,
                       custom_id='apexck:hist')
    async def hist_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._dispatch(interaction, 'hist')

    @discord.ui.button(label='정보', emoji='❓', style=discord.ButtonStyle.secondary,
                       custom_id='apexck:help')
    async def help_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._dispatch(interaction, 'help')


def panel_embed(icon_url: str = None) -> discord.Embed:
    e = discord.Embed(
        title='APEX CHECKER',
        description='원하시는 메뉴를 선택해주세요.',
        color=0xD4A017)
    if icon_url:
        e.set_thumbnail(url=icon_url)
    return e


class CheckerBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.add_view(Panel())          # 영구 버튼 등록
        if GUILD_ID:
            g = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=g)
            synced = await self.tree.sync(guild=g)
            log.info('길드 즉시 동기화: %s개 커맨드 (%s)', len(synced), GUILD_ID)
        else:
            synced = await self.tree.sync()
            log.info('글로벌 동기화: %s개 커맨드 (반영까지 최대 1시간)', len(synced))

    async def on_ready(self):
        log.info(f'로그인: {self.user} ({self.user.id})')
        if PANEL_CHANNEL_ID:
            try:
                ch = self.get_channel(int(PANEL_CHANNEL_ID)) or await self.fetch_channel(int(PANEL_CHANNEL_ID))
                await ch.send(embed=panel_embed(self.user.display_avatar.url), view=Panel())
                log.info('패널 자동 게시 완료')
            except Exception:
                log.exception('패널 자동 게시 실패')


bot = CheckerBot()


@bot.tree.command(name='패널', description='쿠키 검사 패널을 이 채널에 게시합니다')
async def panel_cmd(interaction: discord.Interaction):
    perms = interaction.user.guild_permissions if isinstance(interaction.user, discord.Member) else None
    if perms is not None and not (perms.manage_guild or perms.administrator):
        await interaction.response.send_message('서버 관리 권한이 필요합니다.', ephemeral=True)
        return
    await interaction.response.send_message('패널을 게시했습니다.', ephemeral=True)
    await interaction.channel.send(
        embed=panel_embed(interaction.client.user.display_avatar.url), view=Panel())


@bot.tree.command(name='체커', description='쿠키를 바로 검사합니다 (구매자 전용)')
async def checker_cmd(interaction: discord.Interaction):
    if not has_role(interaction.user):
        await interaction.response.send_message('구매자 역할이 있어야 사용할 수 있습니다.', ephemeral=True)
        return
    await interaction.response.send_modal(CookieModal())


@bot.tree.command(name='내검사', description='최근 검사 기록 보기')
async def my_checks(interaction: discord.Interaction):
    await send_history(interaction)


if __name__ == '__main__':
    if not TOKEN:
        raise SystemExit('CHECKER_TOKEN 환경변수가 필요합니다.')
    bot.run(TOKEN)

