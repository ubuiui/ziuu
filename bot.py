import os
import discord
from discord.ext import commands
import yt_dlp
import random
import asyncio
from flask import Flask
from threading import Thread

# 1. 설정
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)
user_money = {} 
game_stats = {} 
game_states = {} 

# --- 웹 서버 (24시간 가동용) ---
app = Flask('')
@app.route('/')
def home(): return "봇이 살아있어요!"
def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run, daemon=True).start()

# --- 도구 및 게임 로직 함수 ---
def create_deck():
    deck = [r+s for s in ['♠', '♥', '◆', '♣'] for r in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']]
    random.shuffle(deck)
    return deck

def format_cards(hand): return " ".join(hand)

def get_score(hand):
    score, aces = 0, 0
    for card in hand:
        rank = card[:-1]
        if rank in ['J', 'Q', 'K']: score += 10
        elif rank == 'A': score += 11; aces += 1
        else: score += int(rank)
    while score > 21 and aces: score -= 10; aces -= 1
    return score

async def start_blackjack(channel, user, bet):
    deck = create_deck()
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    embed = discord.Embed(title="♠️ 블랙잭 게임 ♣️", color=discord.Color.green())
    embed.add_field(name="딜러 카드", value=f"{d[0]} [??]", inline=True)
    embed.add_field(name="나의 카드", value=f"{format_cards(p)} (합: {get_score(p)})", inline=True)
    msg = await channel.send(embed=embed)
    game_states[user.id] = {'deck':deck, 'player_hand':p, 'dealer_hand':d, 'bet':bet, 'msg':msg}

# --- 관리자 명령어 ---
@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int): 
    user_money[m.id] = user_money.get(m.id, 1000) + a
    await ctx.send(f"✅ {m.name}에게 {a}원 지급 완료! (현재: {user_money[m.id]}원)")

@bot.command()
@commands.has_permissions(administrator=True)
async def 회수(ctx, m: discord.Member, a: int): 
    user_money[m.id] = user_money.get(m.id, 1000) - a
    await ctx.send(f"⚠️ {m.name}에게 {a}원 회수 완료! (현재: {user_money[m.id]}원)")

@bot.command()
@commands.has_permissions(administrator=True)
async def 말하기(ctx, channel: discord.TextChannel, *, t: str):
    await channel.send(t)
    await ctx.send(f"✅ {channel.name} 채널에 메시지 전송.")

@bot.command()
@commands.has_permissions(administrator=True)
async def 공지(ctx, channel: discord.TextChannel, title: str, *, content: str):
    embed = discord.Embed(title=title, description=content, color=discord.Color.blue())
    embed.set_footer(text=f"관리자 {ctx.author.name} 작성")
    await channel.send(embed=embed)
    await ctx.send(f"📢 {channel.name} 채널에 공지 완료.")

# --- 일반 명령어 ---
@bot.command()
async def 블랙잭(ctx, bet: int = 100): await start_blackjack(ctx.channel, ctx.author, bet)
@bot.command()
async def 잔액(ctx): await ctx.send(f"💰 현재 잔액: {user_money.get(ctx.author.id, 1000)}원")
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

# 봇 실행
bot.run(os.environ['BOT_TOKEN'])