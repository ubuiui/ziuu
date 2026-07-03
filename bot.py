import os
import discord
from discord.ext import commands
import yt_dlp
import random
import asyncio
from flask import Flask
from threading import Thread

# 설정
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)
user_money = {}
game_stats = {}
game_states = {}

# 웹 서버 (24시간 가동)
app = Flask('')
@app.route('/')
def home(): return "봇이 살아있어요!"
Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080))), daemon=True).start()

# --- 게임 도구 ---
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

# --- 게임 로직 ---
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    
    uid = message.author.id
    if uid in game_states:
        data = game_states[uid]
        cmd = message.content
        
        if cmd == 'ㅎ':
            data['player_hand'].append(data['deck'].pop())
            score = get_score(data['player_hand'])
            if score > 21:
                user_money[uid] = user_money.get(uid, 1000) - data['bet']
                await data['msg'].edit(content=f"💥 **버스트! {score}점.** 패배했습니다. (잔액: {user_money[uid]}원)")
                del game_states[uid]
                return
            await data['msg'].edit(content=f"나의 카드: {' '.join(data['player_hand'])} (합: {score}) | ㅎ:히트, ㅅ:스테이")
            
        elif cmd == 'ㅅ':
            d_hand = data['dealer_hand']
            while get_score(d_hand) < 17: d_hand.append(data['deck'].pop())
            p_score, d_score = get_score(data['player_hand']), get_score(d_hand)
            
            if d_score > 21 or p_score > d_score:
                user_money[uid] = user_money.get(uid, 1000) + data['bet']
                res = "🎉 승리!"
            elif p_score < d_score:
                user_money[uid] = user_money.get(uid, 1000) - data['bet']
                res = "😭 패배!"
            else: res = "🤝 비김"
            
            await data['msg'].edit(content=f"{res} 딜러: {d_score}점, 나: {p_score}점. (잔액: {user_money[uid]}원)")
            del game_states[uid]

    await bot.process_commands(message)

# --- 관리자 명령어 ---
@bot.command()
@commands.has_permissions(administrator=True)
async def 공지(ctx, channel: discord.TextChannel, title: str, *, content: str):
    embed = discord.Embed(title=title, description=content, color=discord.Color.blue())
    await channel.send(embed=embed)
    await ctx.send("📢 공지 전송 완료.")

@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int):
    user_money[m.id] = user_money.get(m.id, 1000) + a
    await ctx.send(f"✅ {m.name}에게 {a}원 지급.")

# --- 일반 명령어 ---
@bot.command()
async def 블랙잭(ctx, bet: int = 100):
    deck = create_deck()
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    msg = await ctx.send(f"♠️ 블랙잭 시작! 나의 카드: {' '.join(p)} (합: {get_score(p)}) | ㅎ:히트, ㅅ:스테이")
    game_states[ctx.author.id] = {'deck': deck, 'player_hand': p, 'dealer_hand': d, 'bet': bet, 'msg': msg}

@bot.command()
async def 재생(ctx, url: str):
    if not ctx.author.voice: return await ctx.send("음성 채널에 들어가주세요!")
    vc = await ctx.author.voice.channel.connect() if not ctx.voice_client else ctx.voice_client
    with yt_dlp.YoutubeDL({'format': 'bestaudio'}) as ydl:
        info = ydl.extract_info(url, download=False)
        vc.play(discord.FFmpegPCMAudio(info['url']))
        await ctx.send(f"🎵 재생 중: {info['title']}")

@bot.command()
async def 청소(ctx, a: int): await ctx.channel.purge(limit=a + 1)

bot.run(os.environ['BOT_TOKEN'])