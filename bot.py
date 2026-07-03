import os, discord, random, asyncio, yt_dlp
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
    embed.add_field(name="결과", value=f"베팅액: {data['bet']}원\n{result_msg}", inline=False)
    embed.set_footer(text="ㅎ:히트, ㅅ:스테이, ㄷ:더블, ㅍ:포기 (15초 내 입력)")
    return embed

# --- 게임 로직 ---
@bot.command()
async def 블랙잭(ctx, bet: int = 100):
    if ctx.author.id in game_states: return await ctx.send("이미 진행 중인 게임이 있습니다!")
    
    deck = create_deck()
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    data = {'deck': deck, 'player_hand': p, 'dealer_hand': d, 'bet': bet}
    
    # 21 블랙잭 체크 (10배 보상)
    if get_score(p) == 21:
        win_amt = bet * 10
        user_money[ctx.author.id] = user_money.get(ctx.author.id, 1000) + win_amt
        return await ctx.send(f"🎉 **블랙잭(21)!** 10배 당첨! +{win_amt}원 획득.")

    msg = await ctx.send(embed=create_embed(data))
    game_states[ctx.author.id] = {**data, 'msg': msg}

    try:
        while True:
            choice = await bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content in ['ㅎ','ㅅ','ㄷ','ㅍ'], timeout=15.0)
            data = game_states[ctx.author.id]
            
            if choice.content == 'ㅎ': # 히트
                data['player_hand'].append(data['deck'].pop())
                if get_score(data['player_hand']) > 21:
                    user_money[ctx.author.id] = user_money.get(ctx.author.id, 1000) - data['bet']
                    await msg.edit(embed=create_embed(data, "버스트", f"패배! -{data['bet']}원"))
                    break
                await msg.edit(embed=create_embed(data))
            
            elif choice.content == 'ㄷ': # 더블 (베팅 2배)
                data['bet'] *= 2
                data['player_hand'].append(data['deck'].pop())
                # 강제 스테이 로직
                choice = type('obj', (object,), {'content': 'ㅅ'})()
            
            elif choice.content == 'ㅍ': # 포기 (서렌더)
                loss = data['bet'] // 2
                user_money[ctx.author.id] = user_money.get(ctx.author.id, 1000) - loss
                await msg.edit(embed=create_embed(data, "포기", f"절반만 차감됨! -{loss}원"))
                break

            if choice.content == 'ㅅ': # 스테이
                while get_score(data['dealer_hand']) < 17: data['dealer_hand'].append(data['deck'].pop())
                p_s, d_s = get_score(data['player_hand']), get_score(data['dealer_hand'])
                if d_s > 21 or p_s > d_s:
                    user_money[ctx.author.id] = user_money.get(ctx.author.id, 1000) + data['bet']
                    res = f"승리! +{data['bet']}원"
                elif p_s < d_s:
                    user_money[ctx.author.id] = user_money.get(ctx.author.id, 1000) - data['bet']
                    res = f"패배! -{data['bet']}원"
                else: res = "무승부!"
                await msg.edit(embed=create_embed(data, "종료", res))
                break
    except asyncio.TimeoutError:
        await ctx.send("⏱️ 시간이 초과되었습니다.")
    finally:
        if ctx.author.id in game_states: del game_states[ctx.author.id]
        await msg.add_reaction("🔄")

# --- 관리자 및 기타 명령어 ---
@bot.command()
@commands.has_permissions(administrator=True)
async def 공지(ctx, channel: discord.TextChannel, *, args: str):
    parts = args.split(' ', 1)
    embed = discord.Embed(title=parts[0], description=parts[1] if len(parts)>1 else "", color=discord.Color.blue())
    await channel.send(embed=embed)
    await ctx.send("📢 공지 완료.")

@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int):
    user_money[m.id] = user_money.get(m.id, 1000) + a
    await ctx.send(f"✅ {m.name} 지급.")

@bot.command()
async def 잔액(ctx): await ctx.send(f"💰 잔액: {user_money.get(ctx.author.id, 1000)}원")
@bot.command()
async def 청소(ctx, a: int): await ctx.channel.purge(limit=a + 1)
@bot.command()
async def 재생(ctx, url: str):
    if not ctx.author.voice: return await ctx.send("음성 채널에 들어가주세요!")
    vc = await ctx.author.voice.channel.connect() if not ctx.voice_client else ctx.voice_client
    with yt_dlp.YoutubeDL({'format': 'bestaudio'}) as ydl:
        info = ydl.extract_info(url, download=False)
        vc.play(discord.FFmpegPCMAudio(info['url']))
        await ctx.send(f"🎵 재생 중: {info['title']}")

bot.run(os.environ['BOT_TOKEN'])