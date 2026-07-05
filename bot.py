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

# Render 빌드 에러 및 채팅/타자 인식 방지 인텐트 설정
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- [데이터베이스 대용 메모리 저장소] ---
user_money = {}
game_states = {}
attendance_data = {}  # {uid: {"streak": 연속일수, "total": 누적일수, "last_date": "YYYY-MM-DD"}}
user_names = {}       # 랭킹 표시용 유저 이름 저장 {uid: name}

# --- [설정 공간] ---
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@민지유_인데/live"  
NOTICE_CHANNEL_ID = 1520830878513762375  
IS_LIVE_NOW = False 
# --------------------

# 웹 서버 (Render 포트 감지 바인딩 에러 프리패스용)
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
        
    await ctx.send(
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
    user_names[uid] = ctx.author.name
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

    def check_action(m):
        if m.author.id != uid or m.channel.id != ctx.channel.id:
            return False
        val = m.content.strip().lower()
        return val in ['ㅎ', 'ㅎㅌ', '히트', 'hit', 'ㅅ', 'ㅅㅌ', '스테이', 'stay', 'ㄷ', 'ㄷㅂ', '더블', 'double', 'ㅍ', 'ㅍㄱ', '포기', 'surrender']

    while uid in game_states:
        try:
            action_msg = await bot.wait_for('message', check=check_action, timeout=60.0)
            user_input = action_msg.content.strip().lower()
            
            try: await action_msg.delete()
            except: pass

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

            elif user_input in ['ㅍ', 'ㅍㄱ', '포기', 'surrender']:
                user_money[uid] = user_money.get(uid, 1000) - (data['bet'] // 2)
                await main_msg.edit(embed=create_embed(uid, data, "🏳️ 포기함 (절반 회수)", is_final=True))
                await ask_next_game(ctx, data['bet'])
                return

        except asyncio.TimeoutError:
            game_states.pop(uid, None)
            await main_msg.edit(content="⏱️ 제한시간 초과로 게임이 자동 취소되었습니다.", embed=None)
            return

# --- 🏎️ 미니게임 1: 자동차 경주 게임 ---
@bot.command()
async def 경주(ctx, bet: int = 1000):
    uid = ctx.author.id
    user_names[uid] = ctx.author.name
    if bet < 1000: return await ctx.send("⚠️ 최소 배팅 1000원부터 가능합니다.")
    if bet > user_money.get(uid, 1000): return await ctx.send("❌ 잔액이 부족하여 시작할 수 없습니다.")
    if uid in game_states: return await ctx.send("이미 진행 중인 미니게임이 있습니다.")

    game_states[uid] = True
    cars = {"🔴🏃‍♀️ 빨간예빈": 0, "🔵🏃‍♀️ 파란예빈": 0, "🟢🏃‍♀️ 초록예빈": 0, "🟡🏃‍♀️ 노란예빈": 0}
    car_list = list(cars.keys())
    
    guide = await ctx.send(
        f"🏎️ **꼬마 예빈이 달리자 배팅!** [배팅금: {bet}원]\n"
        f"💬 채팅창에 응원할 자동차 번호를 입력하세요 (10초 제한):\n"
        f"**1**: 🔴👧 빨간예빈 | **2**: 🔵👧 파란예빈 | **3**: 🟢👧 초록예빈 | **4**: 🟡👧 노란예빈"
    )

    def check(m):
        return m.author.id == uid and m.channel.id == ctx.channel.id and m.content.strip() in ['1', '2', '3', '4']

    try:
        msg = await bot.wait_for('message', check=check, timeout=10.0)
        user_pick = car_list[int(msg.content.strip()) - 1]
        try: await msg.delete()
        except: pass
    except asyncio.TimeoutError:
        game_states.pop(uid, None)
        return await guide.edit(content="⏱️ 시간 초과로 경주가 취소되었습니다.")

    embed = discord.Embed(title="🏎️ 경주 트랙 스타트!", color=discord.Color.blue())
    race_msg = await ctx.send(embed=embed)
    await guide.delete()

    finish_line = 15
    while True:
        await asyncio.sleep(1.0)
        for car in cars: cars[car] += random.randint(1, 4)

        status_text = ""
        for car, pos in cars.items():
            lane = "." * min(pos, finish_line)
            emoji = car[0]
            status_text += f"{car}: {lane}{emoji}{'.' * (finish_line - pos)}🏁\n" if pos < finish_line else f"{car}: {lane}{emoji} 🏁 **GOAL!**\n"

        embed.description = status_text
        await race_msg.edit(embed=embed)
        winners = [car for car, pos in cars.items() if pos >= finish_line]
        if winners:
            winner = random.choice(winners)
            break

    game_states.pop(uid, None)
    res_embed = discord.Embed(title="🏁 경주 종료 결과 🏁", color=discord.Color.gold())
    res_embed.description = status_text
    
    if winner == user_pick:
        win_money = bet * 3
        user_money[uid] = user_money.get(uid, 1000) + (win_money - bet)
        res_embed.add_field(name="🎉 축하합니다!", value=f"선택하신 **{user_pick}**가 1등을 했습니다!\n**+{win_money}원** 획득! (현재 잔액: {user_money[uid]}원)")
    else:
        user_money[uid] = user_money.get(uid, 1000) - bet
        res_embed.add_field(name="❌ 아쉽습니다", value=f"승리한 예빈이는 **{winner}**였습니다. (선택: {user_pick})\n**-{bet}원** 차감 (현재 잔액: {user_money[uid]}원)")
    await ctx.send(embed=res_embed)

# --- ⚡ 미니게임 2: 순발력 타자 게임 ---
@bot.command()
async def 타자(ctx):
    # 지정해주신 단어들로 커스텀 조합한 35가지 고유 문장 풀
    sentences = [
        "이루카와우뱅의환상적인콜라보레이션", "예원이가유튜브에지유를검색했을때", "피브와예빈이의끝없는유튜브대결", 
        "헬프미를외치는명철이와지유방장님", "만상박장의레전드토크쇼에오신것을환영합니다", "찬우아들이헤응하고울었다는게학계의정설",
        "이루카명철만상박장최강의멤버들", "우뱅이가헬프를외치며예빈이에게달려감", "예원이와피브의지유방송지키기프로젝트",
        "유튜브알고리즘이선택한지유와예빈", "명철아헤응이가부르는데빨리일어나라", "만상이와박장의찬우아들돌보기대작전",
        "이루카피브예원유튜브트리오결성", "우뱅이가지유의헬프요청을승인했습니다", "예빈명철만상박장찬우아들헤응",
        "지유는오늘도유튜브에서빛이너지유", "헤응이의매력에빠져버린이루카와우뱅", "예원이피브헬프치고빨리탈출해",
        "명철이의만상일기속박장의존재감", "찬우아들이추천하는지유와예빈유튜브", "이루카우뱅예원피브예빈유튜브지유",
        "헬프명철만상박장찬우아들헤응이까지", "지유와예빈이의유튜브구독과좋아요", "이루카의우뱅이구출작전헬프미",
        "예원이와피브는명철이의찐팬이래", "만상박장의찬우아들바라기헤응헤응", "지유유튜브구독안하면명철이가출동",
        "예빈피브이루카우뱅의블랙잭대탕진", "헬프요청한박장이와만상이의대탈출", "찬우아들예원이와지유의해피타임",
        "헤응이라고말해버린명철이의최후", "이루카우뱅의유튜브정복기커밍순", "예빈이가지유에게헬프를외친이유",
        "피브와예원의만상박장대백과사전", "찬우아들명철이가헤응하고지유를보네"
    ]
    target = random.choice(sentences)
    
    embed = discord.Embed(title="⚡ 순발력 타자 게임! ⚡", color=discord.Color.purple())
    embed.description = f"아래 문장을 가장 먼저 치는 사람이 상금을 가져갑니다!\n\n제시어: 📝 **{target}**"
    await ctx.send(embed=embed)

    def check(m): return m.channel.id == ctx.channel.id and m.content.strip() == target and not m.author.bot

    try:
        winner_msg = await bot.wait_for('message', check=check, timeout=30.0)
        winner = winner_msg.author
        user_names[winner.id] = winner.name
        prize = random.randint(500, 2000)
        user_money[winner.id] = user_money.get(winner.id, 1000) + prize
        await ctx.send(f"🏆 **{winner.name}**님 칼타자 인정! **+{prize}원** 상금이 지급되었습니다! (총 자산: {user_money[winner.id]}원)")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ 30초 동안 아무도 정확하게 입력하지 않아 게임이 종료되었습니다.")

# --- 🎰 미니게임 3: 슬롯머신 게임 ---
@bot.command()
async def 슬롯(ctx, bet: int = 1000):
    uid = ctx.author.id
    user_names[uid] = ctx.author.name
    if bet < 1000: return await ctx.send("⚠️ 최소 배팅 1000원부터 가능합니다.")
    if bet > user_money.get(uid, 1000): return await ctx.send("❌ 잔액이 부족하여 슬롯을 돌릴 수 없습니다.")
    
    emojis = ["🍒", "🍇", "🍋", "🔔", "💎"]
    embed = discord.Embed(title="🎰 슬롯머신 가동 중...", description="[ 🪙 | 🪙 | 🪙 ]", color=discord.Color.orange())
    msg = await ctx.send(embed=embed)
    
    for _ in range(3):
        await asyncio.sleep(0.5)
        fake_slots = [random.choice(emojis) for _ in range(3)]
        embed.description = f"[ {fake_slots[0]} | {fake_slots[1]} | {fake_slots[2]} ]"
        await msg.edit(embed=embed)

    res = [random.choice(emojis) for _ in range(3)]
    embed.description = f"[ {res[0]} | {res[1]} | {res[2]} ]"
    
    if res[0] == res[1] == res[2]:
        multiplier = 20 if res[0] == "💎" else 5
        msg_text = "💎💎💎 대박 JACKPOT!!! (20배)" if res[0] == "💎" else f"🎉 트리플 완성! ({multiplier}배)"
        win = bet * multiplier
        user_money[uid] = user_money.get(uid, 1000) + (win - bet)
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
        multiplier = 1.5
        win = int(bet * multiplier)
        user_money[uid] = user_money.get(uid, 1000) + (win - bet)
        msg_text = "🔔 페어 성공! (1.5배)"
    else:
        user_money[uid] = user_money.get(uid, 1000) - bet
        msg_text = "😭 꽝! 다음 기회에"

    embed.title = "🎯 슬롯머신 결과 발표"
    embed.add_field(name="정산 결과", value=f"{msg_text}\n변동 금액: {'+' if '배' in msg_text else '-'}{bet if '꽝' in msg_text else int(bet*multiplier)}원\n현재 자산: {user_money[uid]}원")
    await msg.edit(embed=embed)

# --- 📅 추가 기능 4: 출석 체크 시스템 ---
@bot.command()
async def 출석(ctx):
    uid = ctx.author.id
    user_names[uid] = ctx.author.name
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    
    if uid not in attendance_data:
        attendance_data[uid] = {"streak": 0, "total": 0, "last_date": ""}
        
    user_att = attendance_data[uid]
    
    if user_att["last_date"] == today_str:
        return await ctx.send(f"⚠️ {ctx.author.name}님, 오늘은 이미 출석체크를 완료하셨습니다! 내일 다시 와주세요. 📆")
        
    yesterday_str = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    if user_att["last_date"] == yesterday_str:
        user_att["streak"] += 1
    else:
        user_att["streak"] = 1
        
    user_att["total"] += 1
    user_att["last_date"] = today_str
    
    base_reward = 1000
    bonus = min(user_att["streak"] * 100, 1000)
    total_reward = base_reward + bonus
    
    user_money[uid] = user_money.get(uid, 1000) + total_reward
    
    embed = discord.Embed(title="📅 오늘의 출석 체크 완료! 📅", color=discord.Color.green())
    embed.description = f"**{ctx.author.name}**님이 출석 도장을 찍었습니다!"
    embed.add_field(name="연속 출석", value=f"🔥 **{user_att['streak']}일째**", inline=True)
    embed.add_field(name="총 출석일수", value=f"📊 **{user_att['total']}일**", inline=True)
    embed.add_field(name="출석 보상", value=f"💰 +**{total_reward}원** (기본 {base_reward} + 보너스 {bonus})\n현재 자산: {user_money[uid]}원", inline=False)
    embed.set_footer(text=f"출석 일시: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    await ctx.send(embed=embed)

# --- 🏆 추가 기능 5: 통합 랭킹 시스템 ---
@bot.command()
async def 랭킹(ctx):
    sorted_money = sorted(user_money.items(), key=lambda x: x[1], reverse=True)[:5]
    sorted_att = sorted(attendance_data.items(), key=lambda x: x[1]["total"], reverse=True)[:5]
    
    embed = discord.Embed(title="🏆 우리 서버 통합 랭킹 판 🏆", color=discord.Color.gold())
    
    money_text = ""
    for idx, (uid, money) in enumerate(sorted_money, 1):
        name = user_names.get(uid, f"유저({uid})")
        medal = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else f"**{idx}**."))
        money_text += f"{medal} {name} : {money}원\n"
    if not money_text: money_text = "아직 기록이 없습니다."
    
    att_text = ""
    for idx, (uid, att_info) in enumerate(sorted_att, 1):
        name = user_names.get(uid, f"유저({uid})")
        medal = "🥇" if idx == 1 else ("🥈" if idx == 2 else ("🥉" if idx == 3 else f"**{idx}**."))
        att_text += f"{medal} {name} : {att_info['total']}일 (🔥연속 {att_info['streak']}일)\n"
    if not att_text: att_text = "아직 기록이 없습니다."

    embed.add_field(name="💰 자산가 랭킹 Top 5", value=money_text, inline=False)
    embed.add_field(name="📆 성실왕 출석 랭킹 Top 5", value=att_text, inline=False)
    embed.set_footer(text="💡 자산/게임 플레이/출석을 한 번이라도 기록한 유저만 집계됩니다.")
    await ctx.send(embed=embed)


# --- 유튜브 실시간 감지 태스크 ---
@tasks.loop(minutes=5)
async def check_youtube_live():
    global IS_LIVE_NOW
    if not YOUTUBE_CHANNEL_URL or "http" not in YOUTUBE_CHANNEL_URL or not NOTICE_CHANNEL_ID: return
    def fetch_html():
        try:
            req = urllib.request.Request(YOUTUBE_CHANNEL_URL, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=10) as response: return response.read().decode('utf-8')
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
            except Exception as e: print(f"알림 채널 전송 실패: {e}")
        elif not is_live: IS_LIVE_NOW = False

@bot.event
async def on_ready():
    print(f"✅ 디스코드 로그인 성공: {bot.user.name}")
    if not check_youtube_live.is_running(): check_youtube_live.start()

@bot.command()
async def 블랙잭(ctx, bet: int = 1000): await play_blackjack(ctx, bet)

@bot.command()
async def 잔액(ctx): await ctx.send(f"💰 {ctx.author.name}님의 총 자산은 {user_money.get(ctx.author.id, 1000)}원입니다.")

@bot.command()
async def 사다리(ctx, *, args: str = None):
    if not args: return await ctx.send("⚠️ 사용법: `!사다리 항목1 항목2 항목3 ...` (띄어쓰기로 구분)")
    choices = args.split(); len_c = len(choices)
    if len_c < 2: return await ctx.send("⚠️ 최소 2개 이상의 항목을 입력해 주세요!")
    chosen = random.choice(choices)
    embed = discord.Embed(title="🪜 사다리 타기 결과", color=discord.Color.blue())
    embed.add_field(name="선택된 후보들", value=", ".join(choices), inline=False)
    embed.add_field(name="🎯 낙점 결과", value=f"✨ **{chosen}**", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def 룰렛(ctx, *, args: str = None):
    if not args: return await ctx.send("⚠️ 사용법: `!룰렛 항목1 항목2 항목3 ...` (띄어쓰기로 구분)")
    choices = args.split()
    if len(choices) < 2: return await ctx.send("⚠️ 최소 2개 이상의 항목을 입력해 주세요!")
    embed = discord.Embed(title="🎰 룰렛 돌리는 중...", description="🔮 과연 결과는?! \n\n[ 🪙 🟥 🟨 🟩 🟦 🟪 ]", color=discord.Color.purple())
    msg = await ctx.send(embed=embed)
    spin_emojis = ["[ 🟥 🟨 🟩 🟦 🟪 ]", "[ 🟪 🟥 🟨 🟩 🟦 ]", "[ 🟦 🟪 🟥 🟨 🟩 ]"]
    for i in range(3):
        await asyncio.sleep(0.6); embed.description = f"🔮 과연 결과는?! \n\n{spin_emojis[i % len(spin_emojis)]}"; await msg.edit(embed=embed)
    await asyncio.sleep(0.6); chosen = random.choice(choices)
    result_embed = discord.Embed(title="🎯 룰렛 결과 발표", color=discord.Color.green())
    result_embed.add_field(name="전체 후보 리스트", value=", ".join(choices), inline=False)
    result_embed.add_field(name="🏆 최종 당첨 항목", value=f"✨ **{chosen}** ✨", inline=False)
    await msg.edit(result_embed)

# 🔧 [관리자 권한] 유저의 출석 일수 수정용 보정 명령어
@bot.command()
@commands.has_permissions(administrator=True)
async def 출석수정(ctx, m: discord.Member, streak: int, total: int):
    try: await ctx.message.delete()
    except: pass
    
    if m.id not in attendance_data:
        attendance_data[m.id] = {"streak": 0, "total": 0, "last_date": ""}
        
    attendance_data[m.id]["streak"] = streak
    attendance_data[m.id]["total"] = total
    user_names[m.id] = m.name
    
    embed = discord.Embed(title="🔧 출석 데이터 수동 보정 완료", color=discord.Color.orange())
    embed.description = f"관리자 **{ctx.author.name}**님이 유저 **{m.name}**님의 출석 데이터를 수정했습니다."
    embed.add_field(name="수정 후 연속 출석", value=f"🔥 {streak}일", inline=True)
    embed.add_field(name="수정 후 누적 출석", value=f"📊 {total}일", inline=True)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int):
    try: await ctx.message.delete()
    except: pass
    user_money[m.id] = user_money.get(m.id, 1000) + a
    user_names[m.id] = m.name
    embed = discord.Embed(title="💵 자산 지급 완료", color=discord.Color.green())
    embed.description = f"관리자 **{ctx.author.name}**님이 유저 **{m.name}**에게 **{a}원**을 지급하였습니다.\n💰 총 금액: {user_money[m.id]}원"
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def 회수(ctx, m: discord.Member, a: int):
    try: await ctx.message.delete()
    except: pass
    user_money[m.id] = user_money.get(m.id, 1000) - a
    user_names[m.id] = m.name
    embed = discord.Embed(title="🛑 자산 회수 완료", color=discord.Color.red())
    embed.description = f"관리자 **{ctx.author.name}**님이 유저 **{m.name}**에게서 **{a}원**을 회수하였습니다.\n💰 총 금액: {user_money[m.id]}원"
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def 공지(ctx, ch: discord.TextChannel, *, t):
    await ch.send(embed=discord.Embed(title="📢 [공지사항]", description=t, color=discord.Color.blue(), timestamp=datetime.datetime.now()))

@bot.command()
@commands.has_permissions(administrator=True)
async def 청소(ctx, n: int): await ctx.channel.purge(limit=n + 1)

async def main():
    token = os.environ.get('BOT_TOKEN')
    if not token or len(token.strip()) < 10:
        while True: await asyncio.sleep(3600)
    try:
        async with bot: await bot.start(token)
    except:
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    from threading import Thread
    port = int(os.environ.get("PORT", 10000))
    server_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False))
    server_thread.daemon = True
    server_thread.start()
    asyncio.run(main())