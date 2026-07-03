import os, discord, random, asyncio, yt_dlp, time, datetime
from discord.ext import commands
from flask import Flask
from threading import Thread

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)
user_money = {}
game_states = {}

# --- 웹 서버 ---
app = Flask('')
@app.route('/')
def home(): return "봇이 살아있어요!"
Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))), daemon=True).start()

# --- 도구 함수 ---
def create_embed(uid, data, status="진행 중", result_msg=""):
    balance = user_money.get(uid, 1000)
    embed = discord.Embed(title="♠️ 블랙잭 실시간 게임 ♣️", color=discord.Color.gold())
    d_cards = " ".join(data['dealer_hand']) if status != "진행 중" else f"{data['dealer_hand'][0]} [??]"
    d_score = "?" if status == "진행 중" else get_score(data['dealer_hand'])
    
    embed.add_field(name="딜러 카드", value=f"{d_cards} (합: {d_score})", inline=True)
    embed.add_field(name="나의 카드", value=f"{' '.join(data['player_hand'])} (합: {get_score(data['player_hand'])})", inline=True)
    embed.add_field(name="상태 정보", value=f"베팅액: {data['bet']}원\n현재 잔액: {balance}원\n{result_msg}", inline=False)
    embed.set_footer(text="ㅎ:히트, ㅅ:스테이, ㄷ:더블, ㅍ:포기")
    return embed

def get_score(hand):
    score, aces = 0, 0
    for card in hand:
        rank = card[:-1]
        score += 10 if rank in ['J', 'Q', 'K'] else (11 if rank == 'A' else int(rank))
        if rank == 'A': aces += 1
    while score > 21 and aces: score -= 10; aces -= 1
    return score

# --- 게임 로직 ---
async def play_blackjack(ctx, bet):
    uid = ctx.author.id
    deck = [r+s for s in ['♠', '♥', '◆', '♣'] for r in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']]
    random.shuffle(deck)
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    data = {'deck': deck, 'player_hand': p, 'dealer_hand': d, 'bet': bet}
    game_states[uid] = data # 상태 저장
    
    msg = await ctx.send(embed=create_embed(uid, data))
    
    try:
        while True:
            choice = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['ㅎ','ㅅ','ㄷ','ㅍ'], timeout=15.0)
            if choice.content == 'ㅎ':
                data['player_hand'].append(data['deck'].pop())
                if get_score(data['player_hand']) > 21:
                    user_money[uid] = user_money.get(uid, 1000) - data['bet']
                    await msg.edit(embed=create_embed(uid, data, "버스트", f"패배! -{data['bet']}원"))
                    break
                await msg.edit(embed=create_embed(uid, data))
            elif choice.content == 'ㄷ':
                data['bet'] *= 2
                data['player_hand'].append(data['deck'].pop())
                # 더블 시 스테이 로직 강제 실행
                choice = type('obj', (object,), {'content': 'ㅅ'})()
            elif choice.content == 'ㅍ':
                loss = data['bet'] // 2
                user_money[uid] = user_money.get(uid, 1000) - loss
                await msg.edit(embed=create_embed(uid, data, "포기", f"절반 차감! -{loss}원"))
                break
            
            if choice.content == 'ㅅ':
                while get_score(data['dealer_hand']) < 17: data['dealer_hand'].append(data['deck'].pop())
                p_s, d_s = get_score(data['player_hand']), get_score(data['dealer_hand'])
                if d_s > 21 or p_s > d_s:
                    user_money[uid] = user_money.get(uid, 1000) + data['bet']
                    res = f"승리! +{data['bet']}원"
                elif p_s < d_s:
                    user_money[uid] = user_money.get(uid, 1000) - data['bet']
                    res = f"패배! -{data['bet']}원"
                else: res = "무승부!"
                await msg.edit(embed=create_embed(uid, data, "종료", res))
                break
        
        # 여기서 게임 상태 정리
        del game_states[uid]
        
        # 선택지 로직
        await ctx.send("🔄 다음 게임? (1:동일배팅, 2:2배배팅, 3:그만하기)")
        next_c = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['1','2','3'], timeout=15.0)
        
        if next_c.content == '1': await play_blackjack(ctx, bet)
        elif next_c.content == '2': await play_blackjack(ctx, bet * 2)
        else: await ctx.send("게임을 종료합니다.")

    except asyncio.TimeoutError:
        await ctx.send("⏱️ 시간이 초과되어 게임을 종료합니다.")
        if uid in game_states: del game_states[uid]

@bot.command()
async def 블랙잭(ctx, bet: int = 100):
    if ctx.author.id in game_states: return await ctx.send("이미 진행 중인 게임이 있습니다!")
    await play_blackjack(ctx, bet)

# 봇 시작 시간 기록 (맨 위에 `start_time = datetime.datetime.utcnow()` 추가 필요)
start_time = datetime.datetime.utcnow()

@bot.command()
@commands.has_permissions(administrator=True)
async def 상태(ctx):
    # 가동 시간 계산
    uptime = datetime.datetime.utcnow() - start_time
    days, seconds = uptime.days, uptime.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    
    # 임베드 생성
    embed = discord.Embed(title="🤖 봇 실시간 시스템 상태", color=discord.Color.green())
    embed.add_field(name="🕒 가동 시간", value=f"{days}일 {hours}시간 {minutes}분", inline=True)
    embed.add_field(name="📡 핑(Latency)", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.add_field(name="📊 현재 서버 수", value=f"{len(bot.guilds)}개", inline=True)
    embed.add_field(name="⚙️ 시스템 상태", value="정상 작동 중 ✅", inline=False)
    
    await ctx.send(embed=embed)

bot.run(os.environ['BOT_TOKEN'])