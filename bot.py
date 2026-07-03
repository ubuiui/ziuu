import os, discord, random, asyncio, yt_dlp
from discord.ext import commands
from flask import Flask
from threading import Thread

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)
user_money = {}
game_states = {}

# --- 웹 서버 (24시간 유지용) ---
app = Flask('')
@app.route('/')
def home(): return "봇이 살아있어요!"
Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))), daemon=True).start()

# --- 도구 함수 ---
def get_score(hand):
    score, aces = 0, 0
    for card in hand:
        rank = card[:-1]
        score += 10 if rank in ['J', 'Q', 'K'] else (11 if rank == 'A' else int(rank))
        if rank == 'A': aces += 1
    while score > 21 and aces: score -= 10; aces -= 1
    return score

def create_embed(data, status="진행 중", result_msg=""):
    uid = data['uid']
    balance = user_money.get(uid, 1000)
    embed = discord.Embed(title="♠️ 블랙잭 실시간 게임 ♣️", color=discord.Color.gold())
    d_cards = " ".join(data['dealer_hand']) if status != "진행 중" else f"{data['dealer_hand'][0]} [??]"
    embed.add_field(name="딜러 카드", value=f"{d_cards} (합: {get_score(data['dealer_hand']) if status != '진행 중' else '??'})", inline=True)
    embed.add_field(name="나의 카드", value=f"{' '.join(data['player_hand'])} (합: {get_score(data['player_hand'])})", inline=True)
    embed.add_field(name="상태 정보", value=f"베팅액: {data['bet']}원\n현재 잔액: {balance}원\n{result_msg}", inline=False)
    embed.set_footer(text="ㅎ:히트, ㅅ:스테이, ㄷ:더블, ㅍ:포기")
    return embed

# --- 게임 로직 ---
async def play_blackjack(ctx, bet):
    uid = ctx.author.id
    deck = [r+s for s in ['♠', '♥', '◆', '♣'] for r in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']]
    random.shuffle(deck)
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    data = {'uid': uid, 'deck': deck, 'player_hand': p, 'dealer_hand': d, 'bet': bet}
    
    msg = await ctx.send(embed=create_embed(data))
    game_states[uid] = {**data, 'msg': msg}

    try:
        while True:
            choice = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['ㅎ','ㅅ','ㄷ','ㅍ'], timeout=15.0)
            data = game_states[uid]
            
            if choice.content == 'ㅎ':
                data['player_hand'].append(data['deck'].pop())
                if get_score(data['player_hand']) > 21:
                    user_money[uid] = user_money.get(uid, 1000) - data['bet']
                    await msg.edit(embed=create_embed(data, "버스트", f"패배! -{data['bet']}원"))
                    break
                await msg.edit(embed=create_embed(data))
            elif choice.content == 'ㄷ':
                data['bet'] *= 2
                data['player_hand'].append(data['deck'].pop())
                choice = type('obj', (object,), {'content': 'ㅅ'})()
            elif choice.content == 'ㅍ':
                loss = data['bet'] // 2
                user_money[uid] = user_money.get(uid, 1000) - loss
                await msg.edit(embed=create_embed(data, "포기", f"절반 차감! -{loss}원"))
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
                await msg.edit(embed=create_embed(data, "종료", res))
                break
        
        # 재시작 질의
        await ctx.send("🔄 다음 게임? (1:동일배팅, 2:2배배팅, 3:그만하기)")
        next_c = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['1','2','3'], timeout=15.0)
        if next_c.content == '1': await play_blackjack(ctx, bet)
        elif next_c.content == '2': await play_blackjack(ctx, bet * 2)
        else: await ctx.send("게임을 종료합니다.")
    except asyncio.TimeoutError: await ctx.send("⏱️ 시간 초과로 종료합니다.")
    finally:
        if uid in game_states: del game_states[uid]

@bot.command()
async def 블랙잭(ctx, bet: int = 100): await play_blackjack(ctx, bet)

# --- 노래 및 기타 명령어 생략 (위 코드와 동일) ---
# [재생, 일시정지, 재개, 건너뛰기, 입금, 회수 등은 이전과 동일하게 작성]

bot.run(os.environ['BOT_TOKEN'])