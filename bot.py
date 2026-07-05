import os, sys, asyncio, datetime, random
import urllib.request
import urllib.parse
import urllib.error

# --- [필수 라이브러리 자동 설치] ---
try:
    import discord
    from flask import Flask
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "discord.py", "flask"])
    import discord
    from flask import Flask

from discord.ext import commands, tasks

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

user_money = {}
game_states = {}

# --- [설정 공간] ---
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@민지유_인데요/live"  
NOTICE_CHANNEL_ID = 1520830878513762375  
IS_LIVE_NOW = False 
# --------------------

# 웹 서버 (Render 포트 감지 무조건 통과용)
app = Flask('')
@app.route('/')
def home(): 
    return "OK", 200

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
    if not is_final:
        embed.set_footer(text="💬 채팅창에 [ㅎ / ㅅ / ㄷ / ㅍ] 중 하나를 입력하세요! (제한시간 60초)")
    return embed

# --- 다음 게임 진행 안내 (채팅형) ---
async def ask_next_game(ctx, current_bet):
    uid = ctx.author.id
    game_states.pop(uid, None)
    final_money = user_money.get(uid, 1000)
    
    if final_money < 1000:
        return await ctx.send("❌ 잔액이 부족(1000원 미만)하여 게임을 종료합니다.")
        
    guide_msg = await ctx.send(
        f"🔄 **다음 게임을 선택하세요!** [현재 자산: {final_money}원]\n"
        f"💬 채팅창에 번호를 입력하세요 (제한시간 30초):\n"
        f"**1** : 동일 배팅 진행 ({current_bet}원)\n"
        f"**2** : 2배 배팅 진행 ({current_bet * 2}원)\n"
        f"**3** : 게임 종료"
    )

    def check(m):
        return m.author.id == uid and m.channel.id == ctx.channel.id and m.content.strip() in ['1', '2', '3']

    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        choice = msg.content.strip()
        
        if choice == '1':
            await play_blackjack(ctx, current_bet)
        elif choice == '2':
            await play_blackjack(ctx, current_bet * 2)
        else:
            await ctx.send("👋 게임을 종료합니다.")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ 시간 초과로 게임 선택이 취소되었습니다.")

# --- 메인 블랙잭 루프 (채팅형) ---
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
    
    main_msg = await ctx.send(embed=create_embed(uid, data))
    
    if get_score(p) == 21:
        game_states.pop(uid, None)
        win = bet * 10
        user_money[uid] = user_money.get(uid, 1000) + win
        await main_msg.edit(embed=create_embed(uid, data, f"🎉 블랙잭(10배)! +{win}원", is_final=True))
        await ask_next_game(ctx, bet)
        return

    # 채팅 입력 대기 루프
    def check_action(m):
        if m.author.id != uid or m.channel.id != ctx.channel.id:
            return False
        val = m.content.strip().lower()
        return val in ['ㅎ', 'ㅎㅌ', '히트', 'hit', 'ㅅ', 'ㅅㅌ', '스테이', 'stay', 'ㄷ', 'ㄷㅂ', '더블', 'double', 'ㅍ', 'ㅍㄱ', '포기', 'surrender']

    while uid in game_states:
        try:
            action_msg = await bot.wait_for('message', check=check_action, timeout=60.0)
            user_input = action_msg.content.strip().lower()
            
            # 유저의 메시지 삭제 시도 (채팅창 깔끔하게 유지)
            try: await action_msg.delete()
            except: pass

            # 1) 히트 (ㅎ)
            if user_input in ['ㅎ', 'ㅎㅌ', '히트', 'hit']:
                data['p'].append(data['deck'].pop())
                if get_score(data['d']) < 17 and get_score(data['p']) <= 21:
                    data['d'].append(data['deck'].pop())

                if get_score(data['p']) > 21:
                    user_money[uid] = user_money.get(uid, 1000) - data['bet']
                    await main_msg.edit(embed=create_embed(uid, data, "💥 버스트! 패배", is_final=True))
                    await ask_next_game(ctx, data['bet'])
                    return
                else:
                    await main_msg.edit(embed=create_embed(uid, data, "진행 중 (히트함)"))

            # 2) 스테이 (ㅅ)
            elif user_input in ['ㅅ', 'ㅅㅌ', '스테이', 'stay']:
                while get_score(data['d']) < 17:
                    data['d'].append(data['deck'].pop())
                    
                ps, ds = get_score(data['p']), get_score(data['d'])
                res_msg = "🏆 승리!" if (ds > 21 or ps > ds) else ("❌ 패배!" if ps < ds else "🤝 무승부")
                
                if "승리" in res_msg: user_money[uid] = user_money.get(uid, 1000) + data['bet']
                elif "패배" in res_msg: user_money[uid] = user_money.get(uid, 1000) - data['bet']
                
                await main_msg.edit(embed=create_embed(uid, data, res_msg, is_final=True))
                await ask_next_game(ctx, data['bet'])
                return

            # 3) 더블 (ㄷ)
            elif user_input in ['ㄷ', 'ㄷㅂ', '더블', 'double']:
                if (data['bet'] * 2) > user_money.get(uid, 1000):
                    await ctx.send("⚠️ 잔액이 부족하여 더블다운이 불가능합니다.", delete_after=3)
                    continue
                
                data['bet'] *= 2
                data['p'].append(data['deck'].pop())
                while get_score(data['d']) < 17:
                    data['d'].append(data['deck'].pop())
                    
                ps, ds = get_score(data['p']), get_score(data['d'])
                if ps > 21:
                    res_msg = "💥 버스트! 패배"
                    user_money[uid] = user_money.get(uid, 1000) - data['bet']
                else:
                    res_msg = "🏆 승리!" if (ds > 21 or ps > ds) else ("❌ 패배!" if ps < ds else "🤝 무승부")
                    if "승리" in res_msg: user_money[uid] = user_money.get(uid, 1000) + data['bet']
                    elif "패배" in res_msg: user_money[uid] = user_money.get(uid, 1000) - data['bet']
                    
                await main_msg.edit(embed=create_embed(uid, data, f"더블다운 ➡️ {res_msg}", is_final=True))
                await ask_next_game(ctx, data['bet'])
                return

            # 4) 포기 (ㅍ)
            elif user_input in ['ㅍ', 'ㅍㄱ', '포기', 'surrender']:
                user_money[uid] = user_money.get(uid, 1000) - (data['bet'] // 2)
                await main_msg.edit(embed=create_embed(uid, data, "🏳️ 포기함 (절반 회수)", is_final=True))
                await ask_next_game(ctx, data['bet'])
                return

        except asyncio.TimeoutError:
            game_states.pop(uid, None)
            await main_msg.edit(content="⏱️ 제한시간 초과로 게임이 자동 취소되었습니다.", embed=None)
            return

# --- 유튜브 실시간 감지 태스크 ---
@tasks.loop(minutes=5)
async def check_youtube_live():
    global IS_LIVE_NOW
    if not YOUTUBE_CHANNEL_URL or "http" not in YOUTUBE_CHANNEL_URL or not NOTICE_CHANNEL_ID: 
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
                channel = bot.get_channel(int(NOTICE_CHANNEL_ID))
                if channel:
                    embed = discord.Embed(title="🔴 유튜브 실시간 방송 시작!", description=f"지금 바로 방송을 시청하세요!\n[방송 바로가기]({YOUTUBE_CHANNEL_URL})", color=discord.Color.red())
                    await channel.send(embed=embed)
            except Exception as e:
                print(f"알림 채널 전송 실패: {e}")
        elif not is_live:
            IS_LIVE_NOW = False

@bot.event
async def on_ready():
    print(f"✅ 디스코드 로그인 성공: {bot.user.name}")
    if not check_youtube_live.is_running():
        check_youtube_live.start()

# --- 미니게임 및 명령어 공간 ---
@bot.command()
async def 블랙잭(ctx, bet: int = 1000): await play_blackjack(ctx, bet)

@bot.command()
async def 잔액(ctx): await ctx.send(f"💰 {ctx.author.name}님의 총 자산은 {user_money.get(ctx.author.id, 1000)}원입니다.")

@bot.command()
async def 사다리(ctx, *, args: str = None):
    if not args:
        return await ctx.send("⚠️ 사용법: `!사다리 항목1 항목2 항목3 ...` (띄어쓰기로 구분)")
    choices = args.split()
    if len(choices) < 2:
        return await ctx.send("⚠️ 최소 2개 이상의 항목을 입력해 주세요!")
    
    chosen = random.choice(choices)
    embed = discord.Embed(title="🪜 사다리 타기 결과", color=discord.Color.blue())
    embed.add_field(name="선택된 후보들", value=", ".join(choices), inline=False)
    embed.add_field(name="🎯 낙점 결과", value=f"✨ **{chosen}**", inline=False)
    embed.set_footer(text=f"요청자: {ctx.author.name}")
    await ctx.send(embed=embed)

@bot.command()
async def 룰렛(ctx, *, args: str = None):
    if not args:
        return await ctx.send("⚠️ 사용법: `!룰렛 항목1 항목2 항목3 ...` (띄어쓰기로 구분)")
    choices = args.split()
    if len(choices) < 2:
        return await ctx.send("⚠️ 최소 2개 이상의 항목을 입력해 주세요!")
    
    embed = discord.Embed(title="🎰 룰렛 돌리는 중...", description="🔮 과연 결과는?! \n\n[ 🪙 🟥 🟨 🟩 🟦 🟪 ]", color=discord.Color.purple())
    msg = await ctx.send(embed=embed)
    
    spin_emojis = ["[ 🟥 🟨 🟩 🟦 🟪 ]", "[ 🟪 🟥 🟨 🟩 🟦 ]", "[ 🟦 🟪 🟥 🟨 🟩 ]", "[ 🟩 🟦 🟪 🟥 🟨 ]"]
    for i in range(3):
        await asyncio.sleep(0.6)
        embed.description = f"🔮 과연 결과는?! \n\n{spin_emojis[i % len(spin_emojis)]}"
        await msg.edit(embed=embed)
        
    await asyncio.sleep(0.6)
    chosen = random.choice(choices)
    
    result_embed = discord.Embed(title="🎯 룰렛 결과 발표", color=discord.Color.green())
    result_embed.add_field(name="전체 후보 리스트", value=", ".join(choices), inline=False)
    result_embed.add_field(name="🏆 최종 당첨 항목", value=f"✨ **{chosen}** ✨", inline=False)
    result_embed.set_footer(text=f"요청자: {ctx.author.name}")
    await msg.edit(embed=result_embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int):
    try: await ctx.message.delete()
    except: pass
    user_money[m.id] = user_money.get(m.id, 1000) + a
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%