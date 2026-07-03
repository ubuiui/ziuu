import os, discord, random, asyncio, yt_dlp, datetime
from discord.ext import commands
from flask import Flask
from threading import Thread

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

user_money = {}
game_states = {}
start_time = datetime.datetime.utcnow()

# --- 웹 서버 (24시간 유지) ---
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

def create_embed(uid, data, status="진행 중", result_msg=""):
    embed = discord.Embed(title="♠️ 블랙잭 게임 ♣️", color=discord.Color.gold())
    d_cards = " ".join(data['dealer_hand']) if status != "진행 중" else f"{data['dealer_hand'][0]} [??]"
    d_score = "?" if status == "진행 중" else get_score(data['dealer_hand'])
    embed.add_field(name="딜러 카드", value=f"{d_cards} (합: {d_score})", inline=True)
    embed.add_field(name="나의 카드", value=f"{' '.join(data['player_hand'])} (합: {get_score(data['player_hand'])})", inline=True)
    embed.add_field(name="상태 정보", value=f"베팅액: {data['bet']}원\n총 자산: {user_money.get(uid, 1000)}원\n{result_msg}", inline=False)
    embed.set_footer(text="ㅎ:히트, ㅅ:스테이, ㄷ:더블, ㅍ:포기")
    return embed

# --- 블랙잭 로직 ---
async def play_blackjack(ctx, bet):
    uid = ctx.author.id
    deck = [r+s for s in ['♠', '♥', '◆', '♣'] for r in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']]
    random.shuffle(deck)
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    data = {'deck': deck, 'player_hand': p, 'dealer_hand': d, 'bet': bet}
    game_states[uid] = True
    
    # 블랙잭 즉시 승리 체크 (10배)
    if get_score(p) == 21:
        win = bet * 10
        user_money[uid] = user_money.get(uid, 1000) + win
        await ctx.send(f"🎉 **블랙잭(21)!** 10배 당첨! +{win}원 획득. (총 자산: {user_money[uid]}원)")
        del game_states[uid]
        return

    msg = await ctx.send(embed=create_embed(uid, data))
    
    while True:
        try:
            choice = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['ㅎ','ㅅ','ㄷ','ㅍ'], timeout=20.0)
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
                choice = type('obj', (object,), {'content': 'ㅅ'})()
            elif choice.content == 'ㅍ':
                loss = data['bet'] // 2
                user_money[uid] = user_money.get(uid, 1000) - loss
                await msg.edit(embed=create_embed(uid, data, "포기", f"절반 차감! -{loss}원"))
                break
            if choice.content == 'ㅅ':
                while get_score(data['dealer_hand']) < 17: data['dealer_hand'].append(data['deck'].pop())
                p_s, d_s = get_score(data['player_hand']), get_score(data['dealer_hand'])
                res = f"승리! +{data['bet']}원" if (d_s > 21 or p_s > d_s) else (f"패배! -{data['bet']}원" if p_s < d_s else "무승부!")
                user_money[uid] = user_money.get(uid, 1000) + (data['bet'] if "승리" in res else (-data['bet'] if "패배" in res else 0))
                await msg.edit(embed=create_embed(uid, data, "종료", res))
                break
        except asyncio.TimeoutError:
            await ctx.send("⏱️ 시간 초과 종료.")
            break
    
    del game_states[uid]
    await ctx.send("🔄 다음 게임? (1:동일배팅, 2:2배배팅, 3:그만하기)")
    try:
        next_c = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['1','2','3'], timeout=15.0)
        if next_c.content == '1': await play_blackjack(ctx, bet)
        elif next_c.content == '2': await play_blackjack(ctx, bet * 2)
    except: pass

# --- 명령어 ---
@bot.command()
async def 입금(ctx, member: discord.Member, amount: int):
    user_money[member.id] = user_money.get(member.id, 1000) + amount
    await ctx.send(f"✅ {member.name}님에게 {amount}원을 지급했습니다.")

@bot.command()
async def 회수(ctx, member: discord.Member, amount: int):
    user_money[member.id] = user_money.get(member.id, 1000) - amount
    await ctx.send(f"⚠️ {member.name}님에게서 {amount}원을 회수했습니다.")

@bot.command()
async def 블랙잭(ctx, bet: int = 100):
    if ctx.author.id in game_states: return await ctx.send("이미 진행 중인 게임이 있습니다!")
    await play_blackjack(ctx, bet)

@bot.command()
async def 공지(ctx, channel: discord.TextChannel, *, text): await channel.send(f"📢 {text}")
@bot.command()
async def 청소(ctx, amount: int): await ctx.channel.purge(limit=amount + 1)
@bot.command()
async def 상태(ctx):
    uptime = datetime.datetime.utcnow() - start_time
    await ctx.send(f"🤖 정상 | 가동: {uptime.days}일 {uptime.seconds//3600}시간 | 핑: {round(bot.latency * 1000)}ms")

bot.run(os.environ['BOT_TOKEN'])