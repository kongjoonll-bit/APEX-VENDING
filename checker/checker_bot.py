"""Apex Checker — 새 봇 (구매자 역할 전용, 쿠키 체커)

환경변수
- CHECKER_TOKEN      : 새 봇 토큰
- BUYER_ROLE_ID      : 이 역할을 가진 사람만 사용 가능
- WEB_BASE_URL       : 결과 웹사이트 주소 (예: https://apex-checker.onrender.com)
"""
import os
import logging
import discord
from discord import app_commands

import database as db
from cookie_parser import parse_cookie_report, summarize

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger('checker')

TOKEN = os.environ.get('CHECKER_TOKEN', '').strip()
BUYER_ROLE_ID = os.environ.get('BUYER_ROLE_ID', '').strip()
WEB = (os.environ.get('WEB_BASE_URL', '').strip() or '').rstrip('/')

db.init()


class CookieModal(discord.ui.Modal, title='쿠키 검사'):
    cookie = discord.ui.TextInput(
        label='로블록스 쿠키 (.ROBLOSECURITY)',
        style=discord.TextStyle.paragraph,
        placeholder='쿠키 값을 붙여넣어 주세요',
        required=True, max_length=4000,
    )
    checker_out = discord.ui.TextInput(
        label='체커 결과 (선택)',
        style=discord.TextStyle.paragraph,
        placeholder='| Username: ... | Balance: ... | 게임: 값 | 형태로 붙여넣기',
        required=False, max_length=4000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw = (self.checker_out.value or '').strip()
        if not raw:
            embed = discord.Embed(
                title='체커 결과가 필요합니다',
                description='쿠키만으로는 계정 정보를 조회할 수 없습니다.\n'
                            '`체커 결과` 칸에 체커 출력(`| Username: ... |`)을 붙여넣어 주세요.',
                color=0xf2c14e)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        report = parse_cookie_report(raw)
        s = summarize(report)
        token = db.save(interaction.user.id, s.get('username') or interaction.user.name, raw, report)

        embed = discord.Embed(title='검사 완료', color=0x2ecc71)
        embed.add_field(name='계정', value=f"{s.get('username') or '-'}\nID {s.get('user_id') or '-'}", inline=True)
        embed.add_field(name='로벅 잔액 / 기부', value=f"{s.get('balance') if s.get('balance') is not None else '-'} / {s.get('donated') if s.get('donated') is not None else '-'}", inline=True)
        embed.add_field(name='플레이 게임', value=f"{s['games_played']} / {s['games_total']}", inline=True)
        embed.add_field(name='로벅 최다 사용', value=(s['top_robux']['name'] if s['top_robux'] else '-'), inline=True)
        embed.add_field(name='최장 플레이', value=(s['top_time']['name'] if s['top_time'] else '-'), inline=True)
        embed.add_field(name='총 플레이타임', value=s['total_hours_text'], inline=True)
        embed.set_footer(text='자세한 내용은 아래 버튼에서 확인하세요')

        view = None
        if WEB:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label='웹에서 자세히 보기', style=discord.ButtonStyle.link,
                                            url=f'{WEB}/c/{token}'))
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


def has_role(member) -> bool:
    if not BUYER_ROLE_ID:
        return True
    if isinstance(member, discord.Member):
        return any(str(r.id) == BUYER_ROLE_ID for r in member.roles)
    return False


class CheckerBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        log.info('슬래시 커맨드 동기화 완료')

    async def on_ready(self):
        log.info(f'로그인: {self.user} ({self.user.id})')


bot = CheckerBot()


@bot.tree.command(name='체커', description='구매한 쿠키를 검사합니다 (구매자 전용)')
async def checker(interaction: discord.Interaction):
    if not has_role(interaction.user):
        await interaction.response.send_message('구매자 역할이 있어야 사용할 수 있습니다.', ephemeral=True)
        return
    await interaction.response.send_modal(CookieModal())


@bot.tree.command(name='내검사', description='최근 검사 기록 보기')
async def my_checks(interaction: discord.Interaction):
    rows = db.recent(interaction.user.id, 10)
    if not rows:
        await interaction.response.send_message('검사 기록이 없습니다.', ephemeral=True)
        return
    lines = []
    import datetime
    for r in rows:
        at = datetime.datetime.utcfromtimestamp(r['created_at']).strftime('%m-%d %H:%M')
        lines.append(f"`{at}` **{r['username'] or '-'}** → {WEB}/c/{r['token']}" if WEB else f"`{at}` {r['username']}")
    await interaction.response.send_message('\n'.join(lines)[:1900], ephemeral=True)


if __name__ == '__main__':
    if not TOKEN:
        raise SystemExit('CHECKER_TOKEN 환경변수가 필요합니다.')
    bot.run(TOKEN)
