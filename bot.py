import os, discord, random, asyncio, datetime
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread
import urllib.request
import urllib.parse
import urllib.error

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

user_money = {}
game_states = {}

# --- [설정 공간] ---
# 한글 주소 처리를 위해 원본 주소를 안전하게 인코딩하도록 자동 처리해두었습니다.
ORIGINAL_YOUTUBE_URL = "https://www.youtube.com/@민지유_인데요/live"  
# ⚠️ 주의: 채널 ID가 올바른지 디스코드 개발자 모드에서 꼭 다시 확인해 보세요! (보통 18자리 숫자입니다)
NOTICE_CHANNEL_ID = 1520830878513762375  
IS_LIVE_NOW = False 

# 한글 주소 안전 인코딩 변환
try:
    parsed_url = urllib.parse.urlparse(ORIGINAL_YOUTUBE_URL)
    encoded_path = urllib.parse.quote(parsed_url.path)
    YOUTUBE_CHANNEL_URL = urllib.parse.urlunparse((parsed_url.scheme, parsed_url.netloc, encoded_path, parsed_url.params, parsed_url.query, parsed_url.fragment))
except Exception:
    YOUTUBE_CHANNEL_URL = ORIGINAL_YOUTUBE_URL
# --------------------

# 웹 서버 (Render 24시간 가동 및 포트 충돌 원천 차단)
app = Flask('')
@app.route('/')
def home(): return "봇이 완벽하게 살아있습니다!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_flask, daemon=True).start()

def get_score(hand):
    score = 0; aces = 0
    for card in hand:
        rank = card[:-1]
        score += 10 if rank in ['J','Q','K'] else (11 if rank == 'A' else int(rank))
        if rank == 'A': aces += 1
    while score > 21 and aces: score -= 10; aces -= 1
    return score

def create_embed(uid, data, msg="진행 중", is_final=False):
    embed = discord.Embed(title="♠️ 블랙잭 게임 ♣️", color=discord.Color.gold())
    embed.add_field(name="나의 카드", value=f"{' '.join(data['p'])} (합: {get_score(data['p'])})", inline=True)
    dealer_val = f"{' '.join(data['d'])} (합: {get_score(data['d'])})" if is_final else f"{data['d'][0]} [??]"
    embed.add_field(name="딜러 카드", value=dealer_val, inline=True)
    embed.add_field(name="상태 정보", value=f"베팅액: {data['bet']}원\n총 자산: {user_money.get(uid, 1000)}원\n결과: {msg}", inline=False)
    return embed

# --- 블랙잭 버튼 인터페이스 ---
class BlackjackGameView(discord.ui.View):
    def __init__(self, ctx, uid, data, msg_obj):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.uid = uid
        self.data = data
        self.msg_obj = msg_obj
        self.is_finished = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.uid:
            await interaction.response.send_message("❌ 본인의 게임 버튼만 누를 수 있습니다.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if not self.is_finished:
            game_states.pop(self.uid, None)
            try: await self.msg_obj.edit(content="⏱️ 시간 초과로 게임이 취소되었습니다.", view=None)
            except: pass

    @discord.ui.button(label="히트 (ㅎ)", style=discord.Style.primary, custom_id="hit")
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.data['p'].append(self.data['deck'].pop())
        
        if get_score(self.data['d']) < 17 and get_score(self.data['p']) <= 21:
            self.data['d'].append(self.data['deck'].pop())

        if get_score(self.data['p']) > 21:
            self.is_finished = True
            user_money[self.uid] = user_money.get(self.uid, 1000) - self.data['bet']
            await self.msg_obj.edit(embed=create_embed(self.uid, self.data, "💥 버스트! 패배", is_final=True), view=None)
            self.stop()
            await ask_next_game(self.ctx, self.data['bet'])
        else:
            await self.msg_obj.edit(embed=create_embed(self.uid, self.data, "진행 중"))

    @discord.ui.button(label="스테이 (ㅅ)", style=discord.Style.success, custom_id="stay")
    async def stay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.is_finished = True
        
        while get_score(self.data['d']) < 17:
            self.data['d'].append(self.data['deck'].pop())
            
        ps, ds = get_score(self.data['p']), get_score(self.data['d'])
        res_msg = "🏆 승리!" if (ds > 21 or ps > ds) else ("❌ 패배!" if ps < ds else "🤝 무승부")
        
        if "승리" in res_msg: user_money[self.uid] = user_money.get(self.uid, 1000) + self.data['bet']
        elif "패배" in res_msg: user_money[self.uid] = user_money.get(self.uid, 1000) - self.data['bet']
        
        await self.msg_obj.edit(embed=create_embed(self.uid, self.data, res_msg, is_final=True), view=None)
        self.stop()
        await ask_next_game(self.ctx, self.data['bet'])

    @discord.ui.button(label="더블 (ㄷ)", style=discord.Style.secondary, custom_id="double")
    async def double_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if (self.data['bet'] * 2) > user_money.get(self.uid, 1000):
            return await interaction.response.send_message("⚠️ 잔액이 부족하여 더블다운이 불가능합니다.", ephemeral=True)
        
        await interaction.response.defer()
        self.is_finished = True
        self.data['bet'] *= 2
        self.data['p'].append(self.data['deck'].pop())
        
        while get_score(self.data['d']) < 17:
            self.data['d'].append(self.data['deck'].pop())
            
        ps, ds = get_score(self.data['p']), get_score(self.data['d'])
        if ps > 21:
            res_msg = "💥 버스트! 패배"
            user_money[self.uid] = user_money.get(self.uid, 1000) - self.data['bet']
        else:
            res_msg = "🏆 승리!" if (ds > 21 or ps > ds) else ("❌ 패배!" if ps < ds else "🤝 무승부")
            if "승리" in res_msg: user_money[self.uid] = user_money.get(self.uid, 1000) + self.data['bet']
            elif "패배" in res_msg: user_money[self.uid] = user_money.get(self.uid, 1000) - self.data['bet']
            
        await self.msg_obj.edit(embed=create_embed(self.uid, self.data, f"더블다운 ➡️ {res_msg}", is_final=True), view=None)
        self.stop()
        await ask_next_game(self.ctx, self.data['bet'])

    @discord.ui.button(label="포기 (ㅍ)", style=discord.Style.danger, custom_id="surrender")
    async def surrender_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.is_finished = True
        user_money[self.uid] = user_money.get(self.uid, 1000) - (self.data['bet'] // 2)
        await self.msg_obj.edit(embed=create_embed(self.uid, self.data, "🏳️ 포기함 (절반 회수)", is_final=True), view=None)
        self.stop()
        await ask_next_game(self.ctx, self.data['bet'])

# --- 다음 게임 진행 버튼 인터페이스 ---
class NextGameView(discord.ui.View):
    def __init__(self, ctx, uid, current_bet):
        super().__init__(timeout=30.0)
        self.ctx = ctx
        self.uid = uid
        self.current_bet = current_bet

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.uid:
            await interaction.response.send_message("❌ 본인만 선택할 수 있습니다.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="1️⃣ 동일 배팅 진행", style=discord.Style.success)
    async def re_same(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await interaction.message.delete()
        except: pass
        self.stop()
        await play_blackjack(self.ctx, self.current_bet)

    @discord.ui.button(label="2️⃣ 2배 배팅 진행", style=discord.Style.primary)
    async def re_double(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await interaction.message.delete()
        except: pass
        self.stop()
        await play_blackjack(self.ctx, self.current_bet * 2)

    @discord.ui.button(label="3️⃣ 게임 종료", style=discord.Style.danger)
    async def stop_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await interaction.message.delete()
        except: pass
        self.stop()
        await self.ctx.send("👋 게임을 종료합니다.")

async def ask_next_game(ctx, current_bet):
    uid = ctx.author.id
    game_states.pop(uid, None)
    final_money = user_money.get(uid, 1000)
    
    if final_money < 1000:
        return await ctx.send("❌ 잔액이 부족(1000원 미만)하여 게임을 종료합니다.")
        
    view = NextGameView(ctx, uid, current_bet)
    await ctx.send(f"🔄 다음 게임을 선택하세요! [현재 자산: {final_money}원]", view=view)

async def play_blackjack(ctx, bet):
    uid = ctx.author.id
    if bet < 1000: return await ctx.send("⚠️ 최소 배팅 1000원부터 가능합니다.")
    if bet > user_money.get(uid, 1000): return await ctx.send("❌ 잔액이 부족하여 게임을 시작할 수 없습니다.")
    if uid in game_states: return await ctx.send("이미 진행 중인 게임이 있습니다.")
    
    game_states[uid] = True
    deck = [r+s for s in ['♠','♥','◆','♣'] for r in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']]
    random.shuffle(deck)
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    data = {'deck': deck, 'p': p, 'd': d, 'bet': bet}
    
    msg = await ctx.send(embed=create_embed(uid, data))
    
    if get_score(p) == 21:
        game_states.pop(uid, None)
        win = bet * 10
        user_money[uid] = user_money.get(uid, 1000) + win
        await msg.edit(embed=create_embed(uid, data, f"🎉 블랙잭(10배)! +{win}원", is_final=True))
        await ask_next_game(ctx, bet)
    else:
        view = BlackjackGameView(ctx, uid, data, msg)
        await msg.edit(view=view)

# --- 유튜브 실시간 감지 태스크 ---
@tasks.loop(minutes=5)
async def check_youtube_live():
    global IS_LIVE_NOW
    if not YOUTUBE_CHANNEL_URL or "http" not in YOUTUBE_CHANNEL_URL or NOTICE_CHANNEL_ID == 0: 
        return
    
    def fetch_html():
        try:
            req = urllib.request.Request(YOUTUBE_CHANNEL_URL, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.read().decode('utf-8')
        except: return ""

    loop = asyncio.get_event_loop()
    html = await loop.run_in_executor(None, fetch_html)
    
    if html:
        is_live = '\"isLive\":true' in html or 'liveStreamability' in html
        if is_live and not IS_LIVE_NOW:
            IS_LIVE_NOW = True
            try:
                channel = bot.get_channel(NOTICE_CHANNEL_ID)
                if channel:
                    embed = discord.Embed(title="🔴 유튜브 실시간 방송 시작!", description=f"지금 바로 방송을 시청하세요!\n[방송 바로가기]({ORIGINAL_YOUTUBE_URL})", color=discord.Color.red())
                    await channel.send(embed=embed)
            except Exception as e:
                print(f"알림 채널 전송 오류 (채널 ID 확인 필요): {e}")
        elif not is_live:
            IS_LIVE_NOW = False

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    if not check_youtube_live.is_running():
        check_youtube_live.start()

# --- 명령어 ---
@bot.command()
async def 블랙잭(ctx, bet: int = 1000): await play_blackjack(ctx, bet)

@bot.command()
async def 잔액(ctx): await ctx.send(f"💰 {ctx.author.name}님의 총 자산은 {user_money.get(ctx.author.id, 1000)}원입니다.")

@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int):
    try: await ctx.message.delete()
    except: pass
    user_money[m.id] = user_money.get(m.id, 1000) + a
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    embed = discord.Embed(title="💵 자산 지급 완료", color=discord.Color.green())
    embed.description = f"관리자 **{ctx.author.name}**님이 유저 **{m.name}**에게 **{a}원**을 지급하였습니다."
    embed.add_field(name="지급 후 총 금액", value=f"💰 {user_money[m.id]}원", inline=False)
    embed.set_footer(text=f"일시: {now_str}")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def 회수(ctx, m: discord.Member, a: int):
    try: await ctx.message.delete()
    except: pass
    user_money[m.id] = user_money.get(m.id, 1000) - a
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    embed = discord.Embed(title="🛑 자산 회수 완료", color=discord.Color.red())
    embed.description = f"관리자 **{ctx.author.name}**님이 유저 **{m.name}**에게서 **{a}원**을 회수하였습니다."
    embed.add_field(name="회수 후 총 금액", value=f"💰 {user_money[m.id]}원", inline=False)
    embed.set_footer(text=f"일시: {now_str}")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def 공지(ctx, ch: discord.TextChannel, *, t):
    embed = discord.Embed(title="📢 [공지사항]", description=t, color=discord.Color.blue(), timestamp=datetime.datetime.now())
    await ch.send(embed=embed)
    await ctx.send("✅ 공지 임베드 전송 완료", delete_after=3)

@bot.command()
@commands.has_permissions(administrator=True)
async def 청소(ctx, n: int): await ctx.channel.purge(limit=n + 1)

bot.run(os.environ.get('BOT_TOKEN'))