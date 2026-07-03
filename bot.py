import os, discord, random, asyncio, datetime
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
Thread(target=lambda: app.run(host='0.0.0.0', port=10000), daemon=True).start()

# --- 블랙잭 로직 (이전과 동일) ---
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
    return embed

async def play_blackjack(ctx, bet):
    uid = ctx.author.id
    current_money = user_money.get(uid, 1000)
    if bet > current_money: return await ctx.send(f"⚠️ 자산이 부족합니다! (현재: {current_money}원)")
    if uid in game_states: return await ctx.send("이미 진행 중인 게임이 있습니다.")
    
    deck = [r+s for s in ['♠','♥','◆','♣'] for r in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']]
    random.shuffle(deck)
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    data = {'deck': deck, 'p': p, 'd': d, 'bet': bet}
    game_states[uid] = True
    msg = await ctx.send(embed=create_embed(uid, data))
    
    if get_score(p) == 21:
        win = bet * 10
        user_money[uid] = user_money.get(uid, 1000) + win
        await msg.edit(embed=create_embed(uid, data, f"🎉 블랙잭(10배)! +{win}원"))
    else:
        while True:
            try:
                res = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['ㅎ','ㅅ','ㄷ','ㅍ'], timeout=30.0)
                if res.content == 'ㅎ':
                    p.append(deck.pop())
                    if get_score(p) > 21:
                        user_money[uid] = user_money.get(uid, 1000) - bet
                        await msg.edit(embed=create_embed(uid, data, "💥 버스트! 패배"))
                        break
                    await msg.edit(embed=create_embed(uid, data))
                elif res.content == 'ㅅ':
                    while get_score(d) < 17: d.append(deck.pop())
                    ps, ds = get_score(p), get_score(d)
                    if ds > 21 or ps > ds:
                        user_money[uid] = user_money.get(uid, 1000) + bet
                        await msg.edit(embed=create_embed(uid, data, f"🏆 승리! +{bet}원"))
                    elif ps < ds:
                        user_money[uid] = user_money.get(uid, 1000) - bet
                        await msg.edit(embed=create_embed(uid, data, f"❌ 패배! -{bet}원"))
                    else: await msg.edit(embed=create_embed(uid, data, "🤝 무승부"))
                    break
                elif res.content == 'ㄷ':
                    if (bet * 2) > user_money.get(uid, 1000): await ctx.send("⚠️ 잔액 부족으로 더블 불가"); continue
                    bet *= 2; p.append(deck.pop()); data['bet'] = bet
                    await msg.edit(embed=create_embed(uid, data, "더블다운!"))
                    continue
                elif res.content == 'ㅍ':
                    user_money[uid] = user_money.get(uid, 1000) - (bet // 2)
                    await msg.edit(embed=create_embed(uid, data, "🏳️ 포기함"))
                    break
            except: break
    
    del game_states[uid]
    final_money = user_money.get(uid, 1000)
    await ctx.send(f"🔄 다음 게임? (1:동일베팅, 2:2배베팅, 3:종료)\n💰 **현재 총 자산: {final_money}원**")
    try:
        next_c = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['1','2','3'], timeout=15.0)
        if next_c.content == '1':
            if bet > final_money: await ctx.send("❌ 잔액 부족")
            else: await play_blackjack(ctx, bet)
        elif next_c.content == '2':
            if (bet * 2) > final_money: await ctx.send("❌ 잔액 부족")
            else: await play_blackjack(ctx, bet * 2)
    except: pass

# --- 관리자 전용 명령어 ---
@bot.command()
@commands.has_permissions(administrator=True)
async def 공지(ctx, channel: discord.TextChannel, *, text):
    await channel.send(f"📢 **[공지사항]**\n\n{text}")
    await ctx.send("✅ 공지 전송 완료")

@bot.command()
@commands.has_permissions(administrator=True)
async def 청소(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 {amount}개의 메시지를 삭제했습니다.", delete_after=2)

# --- 일반 명령어 ---
@bot.command()
async def 잔액(ctx): await ctx.send(f"💰 {ctx.author.name}님의 총 자산은 {user_money.get(ctx.author.id, 1000)}원입니다.")

@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int):
    user_money[m.id] = user_money.get(m.id, 1000) + a
    await ctx.send(f"✅ {ctx.author.name}님이 {m.name}에게 {a}원을 지급 완료했습니다. (현재 자산: {user_money[m.id]}원)")

@bot.command()
@commands.has_permissions(administrator=True)
async def 회수(ctx, m: discord.Member, a: int):
    user_money[m.id] = user_money.get(m.id, 1000) - a
    await ctx.send(f"⚠️ {ctx.author.name}님이 {m.name}에게서 {a}원을 회수 완료했습니다. (현재 자산: {user_money[m.id]}원)")

@bot.command()
async def 블랙잭(ctx, bet: int = 100): await play_blackjack(ctx, bet)

bot.run(os.environ['BOT_TOKEN'])