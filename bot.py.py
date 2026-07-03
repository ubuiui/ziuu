import os
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import random
from flask import Flask
from threading import Thread

# 1. 설정
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)
user_money = {} 
game_stats = {} 
game_states = {} 

# 웹 서버
app = Flask('')
@app.route('/')
def home(): return "봇이 살아있어요!"
def run(): app.run(host='0.0.0.0', port=8080)
Thread(target=run).start()

# --- 도구 함수 ---
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

def create_embed(data):
    embed = discord.Embed(title="♠️ 블랙잭 게임 ♣️", color=discord.Color.green())
    embed.add_field(name="딜러 카드", value=f"{data['dealer_hand'][0]} [??]", inline=True)
    embed.add_field(name="나의 카드", value=f"{format_cards(data['player_hand'])} (합: {get_score(data['player_hand'])})", inline=True)
    embed.add_field(name="현재 베팅액", value=f"{data['bet']}원", inline=False)
    embed.set_footer(text="ㅎ:히트 | ㄷ:더블 | ㅅ:스테이 | ㅍ:서렌더")
    return embed

# --- 게임 엔진 ---
@bot.event
async def on_message(message):
    if message.author == bot.user: return
    uid = message.author.id
    if uid in game_states:
        data = game_states[uid]
        cmd = message.content
        try: await message.delete()
        except: pass

        if data.get('waiting_for_restart'):
            if cmd == 'ㅇㅇ': await start_blackjack(message.channel, message.author, data['bet'])
            else:
                await data['msg'].edit(embed=None, content=f"게임 종료. 최종 잔액: {user_money.get(uid, 1000)}원")
                del game_states[uid]
            return

        if cmd in ['ㅎ', 'ㅅ', 'ㅍ', 'ㄷ']:
            if cmd in ['ㅎ', 'ㄷ']:
                if cmd == 'ㄷ':
                    if user_money.get(uid, 1000) < data['bet'] * 2: return
                    data['bet'] *= 2
                data['player_hand'].append(data['deck'].pop())
                score = get_score(data['player_hand'])
                if score > 21:
                    user_money[uid] = user_money.get(uid, 1000) - data['bet']
                    game_stats.setdefault(uid, {'w':0,'l':0})['l']+=1
                    await data['msg'].edit(embed=None, content=f"💥 **버스트! {data['bet']}원 패배.** (잔액: {user_money[uid]}원)")
                    del game_states[uid]
                else: await data['msg'].edit(embed=create_embed(data))
            
            elif cmd == 'ㅅ':
                d_hand, p_score = data['dealer_hand'], get_score(data['player_hand'])
                while get_score(d_hand) < 17: d_hand.append(data['deck'].pop())
                d_score = get_score(d_hand)
                is_bj = (p_score == 21 and len(data['player_hand']) == 2)
                res = "🎉 승리!" if (d_score > 21 or p_score > d_score) else ("😭 패배!" if p_score < d_score else "🤝 비김")
                if res == "🎉 승리!": 
                    user_money[uid] = user_money.get(uid, 1000) + (data['bet'] * 10 if is_bj else data['bet'])
                    game_stats.setdefault(uid, {'w':0,'l':0})['w']+=1
                elif res == "😭 패배!": 
                    user_money[uid] = user_money.get(uid, 1000) - data['bet']
                    game_stats.setdefault(uid, {'w':0,'l':0})['l']+=1
                await data['msg'].edit(embed=None, content=f"{'블랙잭 10배 승리!' if is_bj and res=='🎉 승리!' else res}\n결과: 나({p_score}) vs 딜러({d_score})\n잔액: {user_money[uid]}원\n\n한 판 더? (ㅇㅇ / ㄴㄴ)")
                data['waiting_for_restart'] = True
            
            elif cmd == 'ㅍ':
                user_money[uid] = user_money.get(uid, 1000) - (data['bet'] // 2)
                await data['msg'].edit(embed=None, content=f"🏳️ 서렌더! 절반 차감. 잔액: {user_money[uid]}원\n\n한 판 더? (ㅇㅇ / ㄴㄴ)")
                data['waiting_for_restart'] = True
    await bot.process_commands(message)

async def start_blackjack(channel, user, bet):
    deck = create_deck()
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    msg = await channel.send(embed=create_embed({'player_hand':p, 'dealer_hand':d, 'bet':bet}))
    game_states[user.id] = {'deck':deck, 'player_hand':p, 'dealer_hand':d, 'bet':bet, 'msg':msg}

# --- 명령어 ---
@bot.command()
async def 블랙잭(ctx, bet: int = 100): await start_blackjack(ctx.channel, ctx.author, bet)
@bot.command()
async def 전적(ctx):
    s = game_stats.get(ctx.author.id, {'w': 0, 'l': 0})
    await ctx.send(f"📊 전적: {s['w']}승 {s['l']}패 (승률: {round(s['w']/(s['w']+s['l']+1)*100, 1)}%)")
@bot.command()
async def 잔액(ctx): await ctx.send(f"💰 현재 잔액: {user_money.get(ctx.author.id, 1000)}원")
@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int): user_money[m.id] = user_money.get(m.id, 1000) + a; await ctx.send(f"✅ {m.name}에게 {a}원 지급.")
@bot.command()
@commands.has_permissions(administrator=True)
async def 회수(ctx, m: discord.Member, a: int): user_money[m.id] = user_money.get(m.id, 1000) - a; await ctx.send(f"⚠️ {m.name}에게 {a}원 회수.")
@bot.command()
async def 청소(ctx, a: int): await ctx.channel.purge(limit=a + 1)
@bot.command()
async def 말하기(ctx, *, t: str): await ctx.message.delete(); await ctx.send(t)
@bot.command()
async def 재생(ctx, url: str):
    vc = await ctx.author.voice.channel.connect() if not ctx.voice_client else ctx.voice_client
    with yt_dlp.YoutubeDL({'format': 'bestaudio'}) as ydl:
        info = ydl.extract_info(url, download=False)
        vc.play(discord.FFmpegPCMAudio(info['url']))
        await ctx.send(f"🎵 재생 중: {info['title']}")


# 봇 실행
bot.run(os.environ['BOT_TOKEN'])