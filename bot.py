import os, discord, random, asyncio, yt_dlp
from discord.ext import commands
from flask import Flask
from threading import Thread

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)
user_money = {}
game_states = {}
voice_clients = {} # 음성 상태 관리

# --- 웹 서버 ---
app = Flask('')
@app.route('/')
def home(): return "봇이 살아있어요!"
Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))), daemon=True).start()

# --- 도구 함수 (블랙잭용) ---
def create_deck():
    deck = [r+s for s in ['♠', '♥', '◆', '♣'] for r in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']]
    random.shuffle(deck)
    return deck

def get_score(hand):
    score, aces = 0, 0
    for card in hand:
        rank = card[:-1]
        score += 10 if rank in ['J', 'Q', 'K'] else (11 if rank == 'A' else int(rank))
        if rank == 'A': aces += 1
    while score > 21 and aces: score -= 10; aces -= 1
    return score

def create_embed(data, status="진행 중", result_msg=""):
    embed = discord.Embed(title="♠️ 블랙잭 실시간 게임 ♣️", color=discord.Color.gold())
    d_cards = " ".join(data['dealer_hand']) if status != "진행 중" else f"{data['dealer_hand'][0]} [??]"
    d_score = get_score(data['dealer_hand']) if status != "진행 중" else "??"
    embed.add_field(name="딜러 카드", value=f"{d_cards} (합: {d_score})", inline=True)
    embed.add_field(name="나의 카드", value=f"{' '.join(data['player_hand'])} (합: {get_score(data['player_hand'])})", inline=True)
    embed.add_field(name="상태 정보", value=f"베팅액: {data['bet']}원\n현재 잔액: {user_money.get(data['uid'], 1000)}원\n{result_msg}", inline=False)
    embed.set_footer(text="ㅎ:히트, ㅅ:스테이, ㄷ:더블, ㅍ:포기")
    return embed

# --- 노래 및 권한 체크 ---
def is_owner_or_admin(ctx):
    vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    return (vc and vc.channel == ctx.author.voice.channel) or ctx.author.guild_permissions.administrator

# --- 명령어 ---

# [노래봇]
@bot.command()
async def 재생(ctx, url: str):
    if not ctx.author.voice: return await ctx.send("음성 채널에 들어가주세요!")
    vc = await ctx.author.voice.channel.connect() if not ctx.voice_client else ctx.voice_client
    voice_clients[ctx.guild.id] = {'owner': ctx.author.id, 'vc': vc}
    with yt_dlp.YoutubeDL({'format': 'bestaudio'}) as ydl:
        info = ydl.extract_info(url, download=False)
        vc.play(discord.FFmpegPCMAudio(info['url']))
        await ctx.send(f"🎵 재생 중: {info['title']}")

@bot.command()
async def 일시정지(ctx):
    if is_owner_or_admin(ctx): ctx.voice_client.pause()
    else: await ctx.send("권한이 없습니다.")

@bot.command()
async def 재개(ctx):
    if is_owner_or_admin(ctx): ctx.voice_client.resume()

@bot.command()
async def 건너뛰기(ctx):
    if is_owner_or_admin(ctx): ctx.voice_client.stop()
    else: await ctx.send("권한이 없습니다.")

# [경제 및 관리]
@bot.command()
@commands.has_permissions(administrator=True)
async def 회수(ctx, m: discord.Member, a: int):
    user_money[m.id] = user_money.get(m.id, 1000) - a
    await ctx.send(f"⚠️ {m.name}에게서 {a}원을 회수했습니다.")

@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int):
    user_money[m.id] = user_money.get(m.id, 1000) + a
    await ctx.send(f"✅ {m.name}에게 {a}원 지급.")

# [블랙잭 로직 (재귀적 연속 플레이)]
async def play_blackjack(ctx, bet):
    uid = ctx.author.id
    deck = create_deck()
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    data = {'uid': uid, 'deck': deck, 'player_hand': p, 'dealer_hand': d, 'bet': bet}
    
    if get_score(p) == 21:
        win_amt = bet * 10
        user_money[uid] = user_money.get(uid, 1000) + win_amt
        return await ctx.send(f"🎉 **블랙잭(21)!** 10배 당첨! +{win_amt}원.")

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
        await ctx.send("🔄 다음 게임? (1:동일배팅, 2:2배배팅, 3:그만하기)")
        next_c = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['1','2','3'], timeout=15.0)
        if next_c.content == '1': await play_blackjack(ctx, bet)
        elif next_c.content == '2': await play_blackjack(ctx, bet * 2)
    except asyncio.TimeoutError: await ctx.send("시간 초과 종료.")
    finally:
        if uid in game_states: del game_states[uid]

@bot.command()
async def 블랙잭(ctx, bet: int = 100): await play_blackjack(ctx, bet)

bot.run(os.environ['BOT_TOKEN'])