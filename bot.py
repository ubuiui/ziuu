import os, discord, random, asyncio, datetime
from discord.ext import commands
from flask import Flask
from threading import Thread

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

user_money = {}
game_states = {}
start_time = datetime.datetime.utcnow()

# 웹 서버 (24시간 유지)
app = Flask('')
@app.route('/')
def home(): return "봇이 살아있어요!"
Thread(target=lambda: app.run(host='0.0.0.0', port=10000), daemon=True).start()

# 블랙잭 상세 로직
def get_score(hand):
    score = 0; aces = 0
    for card in hand:
        rank = card[:-1]
        score += 10 if rank in ['J','Q','K'] else (11 if rank == 'A' else int(rank))
        if rank == 'A': aces += 1
    while score > 21 and aces: score -= 10; aces -= 1
    return score

def create_embed(uid, data, msg="진행 중"):
    embed = discord.Embed(title="♠️ 블랙잭 게임 ♣️", color=discord.Color.gold())
    embed.add_field(name="나의 카드", value=f"{' '.join(data['p'])} (합: {get_score(data['p'])})", inline=True)
    embed.add_field(name="딜러 카드", value=f"{data['d'][0]} [??]", inline=True)
    embed.add_field(name="상태 정보", value=f"베팅액: {data['bet']}원\n총 자산: {user_money.get(uid, 1000)}원\n진행: {msg}", inline=False)
    embed.set_footer(text="ㅎ:히트, ㅅ:스테이, ㄷ:더블, ㅍ:포기")
    return embed

async def play_blackjack(ctx, bet):
    uid = ctx.author.id
    if uid in game_states: return await ctx.send("이미 진행 중인 게임이 있습니다.")
    
    deck = [r+s for s in ['♠','♥','◆','♣'] for r in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']]
    random.shuffle(deck)
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    data = {'deck': deck, 'p': p, 'd': d, 'bet': bet}
    game_states[uid] = True
    
    # 21 즉시 승리
    if get_score(p) == 21:
        win = bet * 10
        user_money[uid] = user_money.get(uid, 1000) + win
        del game_states[uid]
        return await ctx.send(f"🎉 **블랙잭!** 10배 획득! +{win}원 (자산: {user_money[uid]}원)")

    msg = await ctx.send(embed=create_embed(uid, data))
    
    while True:
        try:
            res = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['ㅎ','ㅅ','ㄷ','ㅍ'], timeout=30.0)
            if res.content == 'ㅎ':
                p.append(deck.pop())
                if get_score(p) > 21:
                    user_money[uid] = user_money.get(uid, 1000) - bet
                    await msg.edit(embed=create_embed(uid, data, "버스트! 패배"))
                    break
                await msg.edit(embed=create_embed(uid, data))
            elif res.content == 'ㅅ':
                while get_score(d) < 17: d.append(deck.pop())
                ps, ds = get_score(p), get_score(d)
                if ds > 21 or ps > ds:
                    user_money[uid] = user_money.get(uid, 1000) + bet
                    await msg.edit(embed=create_embed(uid, data, f"승리! +{bet}원"))
                elif ps < ds:
                    user_money[uid] = user_money.get(uid, 1000) - bet
                    await msg.edit(embed=create_embed(uid, data, f"패배! -{bet}원"))
                else: await msg.edit(embed=create_embed(uid, data, "무승부"))
                break
            elif res.content == 'ㄷ':
                data['bet'] *= 2; p.append(deck.pop()); continue
            elif res.content == 'ㅍ':
                user_money[uid] = user_money.get(uid, 1000) - (bet // 2)
                await msg.edit(embed=create_embed(uid, data, "포기함"))
                break
        except: break
    
    del game_states[uid]
    await ctx.send("🔄 다음 게임? (1:동일베팅, 2:2배베팅, 3:종료)")
    try:
        next_c = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['1','2','3'], timeout=15.0)
        if next_c.content == '1': await play_blackjack(ctx, bet)
        elif next_c.content == '2': await play_blackjack(ctx, bet * 2)
    except: pass

# 관리 명령어
@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int): user_money[m.id] = user_money.get(m.id, 1000) + a; await ctx.send(f"{m.name} 지급 완료")
@bot.command()
@commands.has_permissions(administrator=True)
async def 회수(ctx, m: discord.Member, a: int): user_money[m.id] = user_money.get(m.id, 1000) - a; await ctx.send(f"{m.name} 회수 완료")
@bot.command()
async def 블랙잭(ctx, bet: int = 100): await play_blackjack(ctx, bet)
@bot.command()
async def 상태(ctx): await ctx.send("봇 정상 가동 중.")

bot.run(os.environ['BOT_TOKEN'])