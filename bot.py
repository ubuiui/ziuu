import os, discord, random, asyncio, datetime
from discord.ext import commands
from flask import Flask
from threading import Thread

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

user_money = {}
game_states = {}

# 웹 서버
app = Flask('')
@app.route('/')
def home(): return "봇이 살아있어요!"
Thread(target=lambda: app.run(host='0.0.0.0', port=10000), daemon=True).start()

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
    embed.add_field(name="상태 정보", value=f"베팅액: {data['bet']}원\n총 자산: {user_money.get(uid, 1000)}원\n결과: {msg}", inline=False)
    embed.set_footer(text="ㅎ:히트, ㅅ:스테이, ㄷ:더블, ㅍ:포기")
    return embed

async def update_msg(msg, uid, data, status):
    """메시지 업데이트 안전 함수"""
    try:
        await msg.edit(embed=create_embed(uid, data, status))
    except discord.NotFound: # 메시지가 삭제된 경우 새로 보냄
        return await msg.channel.send(embed=create_embed(uid, data, status))
    return msg

async def play_blackjack(ctx, bet):
    uid = ctx.author.id
    if bet < 1000: return await ctx.send("⚠️ 최소 배팅 1000원부터 가능.")
    if bet > user_money.get(uid, 1000): return await ctx.send("❌ 잔액 부족.")
    if uid in game_states: return await ctx.send("이미 게임 중입니다.")
    
    game_states[uid] = True
    deck = [r+s for s in ['♠','♥','◆','♣'] for r in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']]
    random.shuffle(deck)
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    data = {'deck': deck, 'p': p, 'd': d, 'bet': bet}
    
    msg = await ctx.send(embed=create_embed(uid, data))
    
    while True:
        try:
            res = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['ㅎ','ㅅ','ㄷ','ㅍ'], timeout=30.0)
            try: await res.delete()
            except: pass
            
            if res.content == 'ㅎ':
                p.append(deck.pop())
                if get_score(p) > 21:
                    user_money[uid] = user_money.get(uid, 1000) - bet
                    msg = await update_msg(msg, uid, data, "💥 버스트! 패배")
                    break
                msg = await update_msg(msg, uid, data, "진행 중")
            
            elif res.content == 'ㅅ':
                while get_score(d) < 17: d.append(deck.pop())
                ps, ds = get_score(p), get_score(d)
                res_msg = "🏆 승리!" if (ds > 21 or ps > ds) else ("❌ 패배!" if ps < ds else "🤝 무승부")
                if "승리" in res_msg: user_money[uid] = user_money.get(uid, 1000) + bet
                elif "패배" in res_msg: user_money[uid] = user_money.get(uid, 1000) - bet
                msg = await update_msg(msg, uid, data, res_msg)
                break
                
            elif res.content == 'ㄷ':
                if (bet * 2) > user_money.get(uid, 1000): 
                    await ctx.send("⚠️ 잔액 부족으로 더블 불가"); continue
                bet *= 2; p.append(deck.pop()); data['bet'] = bet
                msg = await update_msg(msg, uid, data, "더블다운!")
                continue
                
            elif res.content == 'ㅍ':
                user_money[uid] = user_money.get(uid, 1000) - (bet // 2)
                msg = await update_msg(msg, uid, data, "🏳️ 포기함")
                break
        except asyncio.TimeoutError: break
    
    del game_states[uid]
    prompt = await ctx.send(f"🔄 다음 게임? (1:동일, 2:2배, 3:종료) [자산: {user_money.get(uid, 1000)}원]")
    try:
        next_c = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['1','2','3'], timeout=20.0)
        await next_c.delete(); await prompt.delete()
        if next_c.content == '1': await play_blackjack(ctx, bet)
        elif next_c.content == '2': await play_blackjack(ctx, bet * 2)
        else: await ctx.send("게임을 종료합니다.")
    except: await prompt.delete()

@bot.command()
async def 블랙잭(ctx, bet: int = 1000): await play_blackjack(ctx, bet)
@bot.command()
async def 잔액(ctx): await ctx.send(f"💰 {ctx.author.name}님의 총 자산은 {user_money.get(ctx.author.id, 1000)}원입니다.")
@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int): 
    user_money[m.id] = user_money.get(m.id, 1000) + a
    await ctx.send(f"✅ {m.name} 지급 완료.")
@bot.command()
@commands.has_permissions(administrator=True)
async def 청소(ctx, n: int): await ctx.channel.purge(limit=n + 1)

bot.run(os.environ['BOT_TOKEN'])