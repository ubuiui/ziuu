import os, asyncio, datetime, random
import discord
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread
from pymongo import MongoClient
import certifi
import flask

# [1] 봇 설정 및 선언 (딱 한 번만 선언해야 합니다!)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# [2] 전역 변수 초기화 (여기서 다 정의해야 에러가 안 납니다)
stocks = {}          # 실제로는 DB에서 불러오지만 초기화 필수
delisted_stocks = {} # <--- 이게 없어서 봇이 죽었던 겁니다!
user_money = {}
user_stocks = {}
user_names = {}
attendance_data = {}
force_next_event = False
last_force_news_time = datetime.datetime.min

game_states = {}
user_stats = {}
user_profits = {}
gift_cooldowns = {}
disaster_cooldowns = {}

# [3] DB 연결 로직
client = None
db = None
users_col = None

try:
    client = MongoClient(os.environ.get('MONGO_URI'), 
                         serverSelectionTimeoutMS=5000,
                         tlsCAFile=certifi.where())
    db = client["stock_game"]
    users_col = db["users"]
    client.server_info()
    print("✅ MongoDB 연결 성공!")
except Exception as e:
    print(f"⚠️ MongoDB 연결 실패, 오프라인 모드로 시작합니다: {e}")

# --- 1. 블랙잭 및 묻더 보조 함수들 ---
def get_score(hand):
    score = 0; aces = 0
    for card in hand:
        val = card[:-1]
        if val in ['J', 'Q', 'K']: score += 10
        elif val == 'A': score += 11; aces += 1
        else: score += int(val)
    while score > 21 and aces: score -= 10; aces -= 1
    return score

def create_embed(uid, data, msg="", is_final=False):
    embed = discord.Embed(title="🃏 블랙잭", color=discord.Color.green())
    embed.add_field(name="내 패", value=f"{' '.join(data['p'])} ({get_score(data['p'])})", inline=True)
    embed.add_field(name="딜러 패", value=f"{' '.join(data['d'])}" if is_final else f"{data['d'][0]} ❓", inline=True)
    if msg: embed.add_field(name="진행 상황", value=msg, inline=False)
    else: embed.add_field(name="조작법", value="`히트`, `스테이`, `더블`, `포기` 를 입력하세요.", inline=False)
    return embed

async def ask_next_game(ctx):
    game_states.pop(ctx.author.id, None)

# --- 2. 6단계 묻더 기능 (40, 30, 20, 15, 10, 5%) ---
async def start_double_or_nothing(ctx, current_money, step=0):
    uid = ctx.author.id
    probs = [0.4, 0.3, 0.2, 0.15, 0.1, 0.05]
    
    if step >= len(probs):
        await ctx.send(f"🎉 **6단계 최종 성공!** 더 이상 도전 불가. 총 **{current_money:,}원**을 획득하며 종료합니다.")
        user_money[uid] = user_money.get(uid, 1000) + current_money
        save_user_db(uid)
        await ask_next_game(ctx)
        return

    current_prob = probs[step]
    embed = discord.Embed(title=f"🎲 묻고 더블로! ({step+1}단계)", color=discord.Color.gold())
    embed.add_field(name="성공 확률", value=f"{int(current_prob*100)}%", inline=True)
    embed.add_field(name="현재 금액", value=f"{current_money:,}원", inline=True)
    embed.add_field(name="성공 시 획득", value=f"{int(current_money * 1.5):,}원", inline=False)
    embed.set_footer(text="도전하려면 '네'를 입력하세요 (그 외 입력 시 정산)")
    
    await ctx.send(embed=embed)

    def check(m):
        return m.author.id == uid and m.channel.id == ctx.channel.id

    try:
        msg = await bot.wait_for('message', check=check, timeout=15.0)
        if msg.content.strip() in ['네', 'y', '예', 'yes']:
            if random.random() < current_prob:
                new_money = int(current_money * 1.5)
                await ctx.send(f"✅ **{step+1}단계 성공!** {new_money:,}원이 되었습니다.")
                await start_double_or_nothing(ctx, new_money, step + 1)
            else:
                await ctx.send(f"💥 **{step+1}단계 실패!** 상금을 모두 잃었습니다.")
                save_user_db(uid)
                await ask_next_game(ctx)
        else:
            await ctx.send(f"✅ 정산 완료! 최종 **{current_money:,}원** 지급.")
            user_money[uid] = user_money.get(uid, 1000) + current_money
            save_user_db(uid)
            await ask_next_game(ctx)
    except asyncio.TimeoutError:
        await ctx.send(f"⏱️ 시간 초과로 정산됩니다. **{current_money:,}원**")
        user_money[uid] = user_money.get(uid, 1000) + current_money
        save_user_db(uid)
        await ask_next_game(ctx)


stocks = {
    "예빈닉스": 10816, "지유엔터": 10489, "헬프미": 10263, 
    "명철수산": 10827, "찬우상사": 10841, "예원데이터": 15909, 
    "민지유건설": 13725, "피브테크": 10680, "루카드림": 12321, "우뱅미디어": 14896,
    "어둠반도체": 10513, "여름전자": 10341, "해나물류": 10519, "헤응인터내셔널": 11215
}

def save_user_db(uid):
    if users_col is None: 
        return
    users_col.update_one(
        {"_id": uid},
        {"$set": {
            "money": user_money.get(uid, 1000),
            "stocks": user_stocks.get(uid, {}),
            "name": user_names.get(uid, "알수없음"),
            "attendance": attendance_data.get(uid, {"streak": 0, "total": 0, "last_date": ""}),
            "stats": user_stats.get(uid, {"atk": 10, "lvl": 1, "強化": 0, "dungeon_floor": 1}),
            "profit": user_profits.get(uid, 0)
        }},
        upsert=True
    )

@bot.command()
@commands.is_owner() # 개발자만 사용 가능하게 설정
async def 주소(ctx):
    # 이 코드를 넣고 봇을 재실행한 뒤, 디스코드에서 !주소 라고 쳐보세요.
    await ctx.send(f"현재 봇의 웹 주소: https://{os.environ['REPL_SLUG']}.{os.environ['REPL_OWNER']}.repl.co")

# --- [설정 공간] ---
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@민지유_인데요/live"  
NOTICE_CHANNEL_ID = 1523727776014794925
IS_LIVE_NOW = False 
app = Flask('')
@app.route('/')
def home(): return "OK", 200

# --- [뉴스 데이터베이스] ---
NEWS_DB = {
    "호재": [
        "🚀 [호재] {name}, 신제품 대박 터져 주문 폭주!",
        "💎 [호재] {name}, 업계 1위 기술력 인증으로 주가 상승!",
        "📈 [호재] {name}, 경쟁사 몰락으로 시장 점유율 1위 등극!",
        "🎁 [호재] {name}, 깜짝 배당 발표에 투자자들 환호!",
        "✨ [호재] {name}, 유명 인플루언서와 광고 계약 체결!",
        "🌟 [호재] {name}, 역대급 실적 달성으로 주주가치 제고!",
        "🤝 [호재] {name}, 글로벌 대기업과 전략적 파트너십 체결!",
        "🧪 [호재] {name}, 차세대 원천 기술 특허 등록 완료!",
        "🏢 [호재] {name}, 본사 확장 이전 및 대규모 인재 채용!",
        "🌈 [호재] {name}, 정부 주관 친환경 우수 기업 선정!",
        "💰 [호재] {name}, 예상치 못한 대규모 투자 유치 성공!"
    ],
    "악재": [
        "⚠️ [악재] {name}, 공장 화재 발생으로 생산 차질...",
        "📉 [악재] {name}, 내부 경영진 횡령 의혹 수사 착수!",
        "💧 [악재] {name}, 제품 치명적 결함으로 전량 리콜 사태!",
        "🚫 [악재] {name}, 대규모 파업으로 공장 가동 전면 중단!",
        "💨 [악재] {name}, 3분기 실적 발표 결과, 적자 폭 확대...",
        "💥 [악재] {name}, 핵심 기술 유출 사고로 검찰 조사 중...",
        "🦠 [악재] {name}, 원자재 공급망 차질로 인한 원가 급상승!",
        "📉 [악재] {name}, 주요 임원들의 대규모 주식 매도 소식!",
        "🚨 [악재] {name}, 경쟁사와의 특허 소송에서 최종 패소!",
        "🌫️ [악재] {name}, 시장의 외면으로 신제품 판매 부진 지속...",
        "🥀 [악재] {name}, 노후 설비 폭발 사고로 안전성 논란 발생!"
    ]
}

# --- [주식 변동 시스템] ---
# [3] 주식 변동 및 리포트 (기존 루프를 이걸로 교체하세요)
@tasks.loop(minutes=3)
async def update_stocks():
    global force_next_event
    channel = bot.get_channel(NOTICE_CHANNEL_ID)
    if not channel: return
    
    # 1. 재상장 로직
    for name, delist_time in list(delisted_stocks.items()):
        if datetime.datetime.now() - delist_time >= datetime.timedelta(minutes=10):
            stocks[name] = random.randint(1000, 10000)
            del delisted_stocks[name]
            await channel.send(f"🔄 **{name}** 주식이 시장에 재상장되었습니다!")

    # 2. 시장 변동 계산 및 리포트 작성 (Embed UI)
    report_desc = ""
    for stock in list(stocks.keys()):
        if stock in delisted_stocks: continue
        
        old_p = stocks[stock]
        up_chance = 0.55 if old_p < 10000 else (0.45 if old_p > 50000 else 0.50)
        rate = random.uniform(1.01, 1.06) if random.random() < up_chance else random.uniform(0.94, 0.99)
        new_p = int(old_p * rate)
        
        # 등락률 계산 및 아이콘 설정
        diff_percent = ((new_p - old_p) / old_p) * 100
        if new_p > old_p:
            icon = "📈"
            percent_text = f"+{diff_percent:.2f}%"
        elif new_p < old_p:
            icon = "📉 "
            percent_text = f"{diff_percent:.2f}%"
        else:
            icon = "➖"
            percent_text = "0.00%"
            
        report_desc += f"{icon} **{stock}** | `{old_p:,}원` → `{new_p:,}원` (`{percent_text}`)\n"
        stocks[stock] = new_p
        
        # 차트 기록 저장 및 20개 자동 유지 로직
        db["price_history"].insert_one({"name": stock, "price": new_p, "time": datetime.datetime.now()})
        if db["price_history"].count_documents({"name": stock}) > 20:
            oldest = db["price_history"].find({"name": stock}).sort("time", 1).limit(1)
            for doc in oldest:
                db["price_history"].delete_one({"_id": doc["_id"]})

    # 리포트 전송 (Embed)
    embed = discord.Embed(title="📊 실시간 시장 변동 리포트", description=report_desc, color=discord.Color.gold())
    embed.set_footer(text="3분마다 시장 상황이 자동 갱신됩니다.")
    await channel.send(embed=embed)

    # 3. 뉴스 이벤트 (확률적 발생)
    if random.random() < 0.2 or force_next_event:
        force_next_event = False
        target = random.choice([s for s in stocks if s not in delisted_stocks])
        is_good = random.random() < 0.5
        
        category = "호재" if is_good else "악재"
        news_text = random.choice(NEWS_DB[category]).format(name=target)
        
        embed = discord.Embed(
            title="📢 [속보]", 
            description=f"{'🔴' if is_good else '🔵'} **[{'호재!' if is_good else '악재!'}]**\n\n{news_text}\n\n이로 인해 **{'급등' if is_good else '급락'}** 할 것으로 보입니다!", 
            color=discord.Color.red() if is_good else discord.Color.blue()
        )
        await channel.send(embed=embed)
        
        change_rate = random.uniform(0.15, 0.40)
        if is_good: 
            stocks[target] = int(stocks[target] * (1 + change_rate))
        else:
            stocks[target] = int(stocks[target] * (1 - change_rate))
            
            # 상장폐지 로직
            if stocks[target] <= 1000 and random.random() < 0.05:
                delisted_stocks[target] = datetime.datetime.now()
                mentions = [f"<@{uid}>" for uid, portfolio in user_stocks.items() if target in portfolio]
                await channel.send(f"⚠️ **{target} 상장폐지!** {' '.join(mentions)}\n보유하신 주식이 휴지 조각이 되었습니다.")
                for uid in [u for u, s in user_stocks.items() if target in s]:
                    del user_stocks[uid][target]
                    save_user_db(uid)
                del stocks[target]

# --- 주식 그래프 ---
@bot.command()
async def 차트(ctx, name: str):
    if name not in stocks:
        return await ctx.send("❌ 존재하지 않는 주식입니다.")
    
    # 최근 10개만 불러오기
    history = list(db["price_history"].find({"name": name}).sort("time", -1).limit(10))
    
    if not history:
        return await ctx.send("📉 아직 데이터가 없습니다.")

    # 텍스트 차트 만들기
    chart_text = f"📈 **[{name}] 최근 변동 추이**\n```\n"
    prices = [h['price'] for h in history]
    
    for i in range(len(history)):
        h = history[i]
        time_str = h['time'].strftime('%H:%M')
        # 이전 가격과 비교해서 아이콘 표시
        icon = ""
        if i < len(history) - 1:
            if h['price'] > history[i+1]['price']: icon = "🔺"
            elif h['price'] < history[i+1]['price']: icon = "🔻"
            else: icon = "➖"
        
        chart_text += f"{time_str} | {h['price']:,}원 {icon}\n"
    
    chart_text += "```"
    await ctx.send(chart_text)

# ==========================================
# [신규 기능: 주식, 강화, 던전, 보물찾기]
# ==========================================

@bot.command()
async def 매수(ctx, name: str, qty: int):
    uid = ctx.author.id
    sync_user_data(uid, ctx.author.name)
    await asyncio.sleep(0.3)
    if name not in stocks or qty <= 0:
        return await ctx.send("❌ 존재하지 않는 종목이거나 잘못된 수량입니다.")
    
    cost = stocks[name] * qty
    if user_money.get(uid, 1000) < cost:
        return await ctx.send("❌ 잔액이 부족합니다!")
    
    user_money[uid] -= cost
    
    if uid not in user_stocks:
        user_stocks[uid] = {}
    
    # 평단가 계산
    current_data = user_stocks[uid].get(name, {"qty": 0, "avg_price": 0})
    total_qty = current_data["qty"] + qty
    new_avg = ((current_data["qty"] * current_data["avg_price"]) + (qty * stocks[name])) / total_qty
    
    user_stocks[uid][name] = {"qty": total_qty, "avg_price": int(new_avg)}
    
    # [핵심] DB 저장 함수 호출
    save_user_db(uid)
    
    await ctx.send(f"✅ {name} {qty}주 매수 완료! (평단가: {int(new_avg):,}원)")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandInvokeError):
        if isinstance(error.original, discord.errors.HTTPException) and error.original.status == 429:
            await ctx.send("⚠️ 디스코드 API 제한에 걸렸습니다. 10초만 기다려 주세요!")

@bot.command()
async def 내정보(ctx):
    uid = ctx.author.id
    sync_user_data(uid, ctx.author.name)
    
    money = user_money.get(uid, 1000)
    stocks_info = user_stocks.get(uid, {})
    
    # [수정] 내주식 로직을 이곳에 통합
    stock_str = ""
    for name, data in stocks_info.items():
        if data["qty"] > 0:
            current_price = stocks[name]
            profit = ((current_price - data["avg_price"]) / data["avg_price"]) * 100
            profit_icon = "📈" if profit >= 0 else "📉"
            stock_str += f"- **{name}**: {data['qty']}주 | 평단:{data['avg_price']:,}원 | 수익:{profit_icon} {profit:.1f}%\n"
    
    if not stock_str: stock_str = "보유 주식이 없습니다."
    
    embed = discord.Embed(title=f"👤 {ctx.author.name}님의 정보", color=discord.Color.blue())
    embed.add_field(name="💰 보유 자산", value=f"{money:,}원", inline=False)
    embed.add_field(name="📈 보유 주식", value=stock_str, inline=False)
    embed.add_field(name="📅 출석 횟수", value=f"{attendance_data.get(uid, {}).get('total', 0)}회", inline=True)
    
    await ctx.send(embed=embed)

# --- 주식 매도 기능 ---
@bot.command()
async def 매도(ctx, name: str, qty: int):
    uid = ctx.author.id
    sync_user_data(uid, ctx.author.name)
    await asyncio.sleep(0.3)
    # 1. 예외 처리
    if name not in user_stocks.get(uid, {}) or user_stocks[uid][name]["qty"] < qty:
        return await ctx.send("❌ 보유 중인 주식이 없거나 수량이 부족합니다.")
    
    # 2. 매도 로직
    sell_price = stocks[name] * qty
    user_money[uid] = user_money.get(uid, 1000) + sell_price
    user_stocks[uid][name]["qty"] -= qty
    
    # 수량이 0이면 해당 종목 삭제
    if user_stocks[uid][name]["qty"] == 0:
        del user_stocks[uid][name]
        
    # [핵심] DB 저장 함수 호출 (돈과 주식이 모두 변했으므로 반드시 호출!)
    save_user_db(uid)
    
    await ctx.send(f"✅ {name} {qty}주 매도 완료! (획득 금액: {sell_price:,}원)")

@tasks.loop(hours=1.5)
async def treasure_event():
    channel = bot.get_channel(NOTICE_CHANNEL_ID) 
    if not channel: return
    msg = await channel.send("💎 **[보물 이벤트]** 채팅창 어딘가에 보물이 나타났습니다! 1분 내에 ✋ 이모지를 누르는 선착순 1명에게 보상을 드립니다!")
    await msg.add_reaction("✋")
    def check(reaction, user):
        return reaction.message.id == msg.id and str(reaction.emoji) == "✋" and not user.bot
    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
        reward = random.randint(50000, 200000)
        user_money[user.id] = user_money.get(user.id, 1000) + reward
        await channel.send(f"🎉 **{user.name}**님이 보물을 선점하여 {reward:,}원을 획득했습니다!")
    except:
        await channel.send("💨 아쉽게도 아무도 보물을 가져가지 못했습니다.")


# --- 3. 블랙잭 메인 로직 ---
async def play_blackjack(ctx, bet):
    uid = ctx.author.id
    sync_user_data(uid, ctx.author.name)
    if bet < 1000: return await ctx.send("⚠️ 최소 배팅 1000원부터 가능합니다.")
    if bet > user_money.get(uid, 1000): return await ctx.send("❌ 잔액이 부족합니다.")
    if uid in game_states: return await ctx.send("⚠️ 이미 게임 중입니다.")
    
    game_states[uid] = True
    deck = [r+s for s in ['♠','♥','◆','♣'] for r in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']]
    random.shuffle(deck)
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    data = {'deck': deck, 'p': p, 'd': d, 'bet': bet}
    
    main_msg = await ctx.send(embed=create_embed(uid, data))
    
    # 블랙잭 즉시 당첨 확인
    if get_score(p) == 21:
        win_money = int(bet * 1.5)
        await main_msg.edit(embed=create_embed(uid, data, f"🎉 블랙잭(1.5배)! 성공!", is_final=True))
        await start_double_or_nothing(ctx, win_money, step=0)
        return

    def check_action(m):
        return m.author.id == uid and m.channel.id == ctx.channel.id

    while uid in game_states:
        try:
            msg = await bot.wait_for('message', check=check_action, timeout=60.0)
            cmd = msg.content.strip().lower()
            try: await msg.delete() 
            except: pass

            if cmd in ['히트', 'hit', 'ㅎ']:
                data['p'].append(data['deck'].pop())
                if get_score(data['p']) > 21:
                    user_money[uid] -= data['bet']
                    await main_msg.edit(embed=create_embed(uid, data, "💥 버스트! 패배", is_final=True))
                    await ask_next_game(ctx)
                    return
                await main_msg.edit(embed=create_embed(uid, data))

            elif cmd in ['스테이', 'stay', 'ㅅ']:
                while get_score(data['d']) < 17: data['d'].append(data['deck'].pop())
                p_s, d_s = get_score(data['p']), get_score(data['d'])
                if d_s > 21 or p_s > d_s:
                    await main_msg.edit(embed=create_embed(uid, data, "🏆 승리!", is_final=True))
                    win_amount = data['bet'] * 2
                    await start_double_or_nothing(ctx, win_amount, step=0)
                elif p_s == d_s:
                    await main_msg.edit(embed=create_embed(uid, data, "🤝 무승부", is_final=True))
                    await ask_next_game(ctx)
                else:
                    user_money[uid] -= data['bet']
                    await main_msg.edit(embed=create_embed(uid, data, "❌ 패배", is_final=True))
                    await ask_next_game(ctx)
                return

            elif cmd in ['더블', 'double', 'ㄷ']:
                if (data['bet'] * 2) > user_money.get(uid, 1000):
                    await ctx.send("⚠️ 잔액 부족", delete_after=2); continue
                data['bet'] *= 2
                data['p'].append(data['deck'].pop())
                while get_score(data['d']) < 17: data['d'].append(data['deck'].pop())
                if get_score(data['p']) <= 21 and (get_score(data['d']) > 21 or get_score(data['p']) > get_score(data['d'])):
                    await main_msg.edit(embed=create_embed(uid, data, "🏆 더블 승리!", is_final=True))
                    await start_double_or_nothing(ctx, data['bet'], step=0)
                else:
                    user_money[uid] -= data['bet']
                    await main_msg.edit(embed=create_embed(uid, data, "❌ 패배", is_final=True))
                    await ask_next_game(ctx)
                return

            elif cmd in ['포기', 'surrender', 'ㅍ']:
                user_money[uid] -= (data['bet'] // 2)
                await main_msg.edit(embed=create_embed(uid, data, "🏳️ 포기(절반 회수)", is_final=True))
                await ask_next_game(ctx)
                return
        except asyncio.TimeoutError:
            await ctx.send("⏱️ 시간 초과.")
            await ask_next_game(ctx)
            return

# --- 🏎️ 미니게임 1: 자동차 경주 게임 ---
@bot.command()
async def 경주(ctx, bet: int = 1000):
    uid = ctx.author.id
    sync_user_data(uid, ctx.author.name)
    user_names[uid] = ctx.author.name
    
    # 1. 예외 처리
    if bet < 1000: return await ctx.send("⚠️ 최소 배팅 1000원부터 가능합니다.")
    if bet > user_money.get(uid, 1000): return await ctx.send("❌ 잔액이 부족하여 시작할 수 없습니다.")
    if uid in game_states: return await ctx.send("이미 진행 중인 미니게임이 있습니다.")

    game_states[uid] = True
    cars = {"🔴👧 빨간예빈": 0, "🔵👧 파란예빈": 0, "🟢👧 초록예빈": 0, "🟡👧 노란예빈": 0}
    car_list = list(cars.keys())
    
    guide = await ctx.send(
        f"🏎️ **꼬마 예빈이 달리자 배팅!** [배팅금: {bet:,}원]\n"
        f"💬 채팅창에 응원할 자동차 번호를 입력하세요 (10초 제한):\n"
        f"**1**: 🔴👧 빨간예빈 | **2**: 🔵👧 파란예빈 | **3**: 🟢👧 초록예빈 | **4**: 🟡👧 노란예빈"
    )

    def check(m):
        return m.author.id == uid and m.channel.id == ctx.channel.id and m.content.strip() in ['1', '2', '3', '4']

    try:
        msg = await bot.wait_for('message', check=check, timeout=10.0)
        user_pick = car_list[int(msg.content.strip()) - 1]
        try: await msg.delete()
        except: pass
    except asyncio.TimeoutError:
        game_states.pop(uid, None)
        return await guide.edit(content="⏱️ 시간 초과로 경주가 취소되었습니다.")

    # 2. 경주 진행
    embed = discord.Embed(title="🏎️ 경주 트랙 스타트!", color=discord.Color.blue())
    race_msg = await ctx.send(embed=embed)
    await guide.delete()

    finish_line = 15
    while True:
        await asyncio.sleep(1.0)
        for car in cars: cars[car] += random.randint(1, 4)

        status_text = ""
        for car, pos in cars.items():
            lane = "." * min(pos, finish_line)
            emoji = car[0]
            status_text += f"{car}: {lane}{emoji}{'.' * (finish_line - pos)}🏁\n" if pos < finish_line else f"{car}: {lane}{emoji} 🏁 **GOAL!**\n"

        embed.description = status_text
        await race_msg.edit(embed=embed)
        winners = [car for car, pos in cars.items() if pos >= finish_line]
        if winners:
            winner = random.choice(winners)
            break

    # 3. 결과 판정 및 묻더 호출
    game_states.pop(uid, None) # 게임 상태 해제
    
    if winner == user_pick:
        # 승리: 1.3배 지급 예정 (묻더 함수로 넘김)
        win_amount = int(bet * 1.3)
        res_embed = discord.Embed(title="🏁 경주 종료 결과 🏁", color=discord.Color.gold())
        res_embed.description = status_text
        res_embed.add_field(name="🎉 축하합니다!", value=f"선택하신 **{user_pick}**가 1등! {win_amount:,}원 확보! (묻더 진행)")
        await ctx.send(embed=res_embed)
        
        # 여기서 바로 묻더 함수 호출 (지갑에는 아직 안 더함)
        await start_double_or_nothing(ctx, win_amount, step=0)
    else:
        # 패배: 배팅금 차감
        user_money[uid] -= bet
        res_embed = discord.Embed(title="🏁 경주 종료 결과 🏁", color=discord.Color.red())
        res_embed.description = status_text
        res_embed.add_field(name="❌ 아쉽습니다", value=f"승리한 예빈이는 **{winner}**였습니다. **-{bet:,}원** 차감")
        await ctx.send(embed=res_embed)
        save_user_db(uid)

# --- ⚡ 미니게임 2: 순발력 타자 게임 ---
@bot.command()
async def 타자(ctx):
    sentences = [
        "이루카와우뱅의환상적인콜라보레이션", "예원이가유튜브에피브를검색했을때", "우뱅와예빈이의끝없는유튜브대결", 
        "헬프미를외치는명철이와지유방장님", "만상박장의레전드토크쇼에오신것을환영합니다", "찬우아들이헤응하고울었다는게학계의정설"
    ]
    target = random.choice(sentences)
    
    embed = discord.Embed(title="⚡ 순발력 타자 게임! ⚡", color=discord.Color.purple())
    embed.description = f"아래 문장을 가장 먼저 치는 사람이 상금을 가져갑니다!\n\n제시어: 📝 **{target}**"
    await ctx.send(embed=embed)

    def check(m): return m.channel.id == ctx.channel.id and m.content.strip() == target and not m.author.bot

    try:
        winner_msg = await bot.wait_for('message', check=check, timeout=30.0)
        winner = winner_msg.author
        uid = winner.id
        user_names[winner.id] = winner.name
        prize = random.randint(500, 2000)
        user_money[winner.id] = user_money.get(winner.id, 1000) + prize
        await ctx.send(f"🏆 **{winner.name}**님 칼타자 인정! **+{prize:,}원** 상금이 지급되었습니다! (총 자산: {user_money[winner.id]:,}원)")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ 30초 동안 아무도 정확하게 입력하지 않아 게임이 종료되었습니다.")

    save_user_db(uid)

# --- 🎰 미니게임 3: 슬롯머신 게임 ---
@bot.command()
async def 슬롯(ctx, bet: int = 1000):
    uid = ctx.author.id
    sync_user_data(uid, ctx.author.name)
    user_names[uid] = ctx.author.name
    
    # 1. 예외 처리 및 선차감
    if bet < 1000: return await ctx.send("⚠️ 최소 배팅 1000원부터 가능합니다.")
    if bet > user_money.get(uid, 1000): return await ctx.send("❌ 잔액이 부족하여 슬롯을 돌릴 수 없습니다.")
    
    user_money[uid] -= bet # 배팅금 선차감
    
    # 2. 슬롯 애니메이션
    emojis = ["🍒", "🍇", "🍋", "🔔", "💎"]
    embed = discord.Embed(title="🎰 슬롯머신 가동 중...", description="[ 🪙 | 🪙 | 🪙 ]", color=discord.Color.orange())
    msg = await ctx.send(embed=embed)
    
    for _ in range(3):
        await asyncio.sleep(0.5)
        fake_slots = [random.choice(emojis) for _ in range(3)]
        embed.description = f"[ {fake_slots[0]} | {fake_slots[1]} | {fake_slots[2]} ]"
        await msg.edit(embed=embed)

    # 3. 결과 판정
    is_win = random.randint(0, 99) < 40 # 40% 확률 승리
    
    if is_win:
        # 승리 로직
        if random.random() < 0.15: # 잭팟
            res = [random.choice(emojis)] * 3
            multiplier = 10
            msg_text = f"🎉🎉🎉 트리플 달성! 초대박 잭팟 완성!!! ({multiplier}배)"
        else: # 페어
            res = [emojis[0], emojis[0], emojis[1]]
            random.shuffle(res)
            multiplier = 1.2
            msg_text = "🔔 페어 성공! (1.2배)"
        
        win_money = int(bet * multiplier)
        
        # 묻더 연결: 여기서 돈을 더하지 않고 바로 함수로 넘깁니다.
        embed.description = f"[ {res[0]} | {res[1]} | {res[2]} ]"
        embed.title = "🎯 슬롯머신 결과 발표"
        embed.add_field(name="정산 결과", value=f"{msg_text}\n획득 예정 상금: **{win_money:,}원**\n\n잠시 후 **묻더** 선택 창이 활성화됩니다!")
        await msg.edit(embed=embed)
        
        await start_double_or_nothing(ctx, win_money, step=0)
        
    else:
        # 패배 로직
        res = ["🍒", "🍇", "🍋"]
        random.shuffle(res)
        msg_text = "😭 꽝! 다음 기회에"
        
        embed.description = f"[ {res[0]} | {res[1]} | {res[2]} ]"
        embed.title = "🎯 슬롯머신 결과 발표"
        embed.add_field(name="정산 결과", value=f"{msg_text}\n변동 금액: -{bet:,}원\n현재 자산: {user_money[uid]:,}원")
        await msg.edit(embed=embed)
        
        save_user_db(uid) # 패배 시에만 바로 저장

# --- ❤️ [신규 미니게임 6] 실시간 중계형 멀티 소개팅 배팅 게임 ---
@bot.command()
async def 소개팅(ctx, bet: int = None):
    # 멀티 배팅방 수집 모듈 (간단 구현)
    def check_msg(m): return m.author.id != bot.user.id and m.content == "!참가"
    await ctx.send(f"💕 **{bet:,}원** 소개팅 참가자를 모집합니다! 15초간 채팅창에 `!참가`를 입력해주세요.")
    participants = []
    start_time = datetime.datetime.now()
    
    while (datetime.datetime.now() - start_time).total_seconds() < 15:
        try:
            msg = await bot.wait_for('message', check=check_msg, timeout=1.0)
            if msg.author not in participants:
                participants.append(msg.author)
                await ctx.send(f"✅ {msg.author.name}님 참가 완료!")
        except: continue
        
    if not participants or len(participants) < 1:
        return await ctx.send("❌ 참여자가 없어 소개팅이 취소되었습니다.")

    total_pool = bet * len(participants)
    
    # 판돈 먼저 일괄 차감
    deduct_msg = ""
    for p in participants:
        user_money[p.id] = user_money.get(p.id, 1000) - bet
        deduct_msg += f"💸 **{p.name}**님 참가비 -{bet:,}원 차감\n"
    await ctx.send(f"❤️ **[소개팅 참가비가 즉시 차감되었습니다]** ❤️\n{deduct_msg}")

    # 실시간 중계 상황판 임베드 빌드
    embed = discord.Embed(title="💖 실시간 커플 매칭! 두근두근 소개팅 중계 💖", color=discord.Color.from_rgb(255, 105, 180))
    p_mentions = ", ".join([p.mention for p in participants])
    embed.add_field(name="👥 소개팅 참가자", value=p_mentions, inline=False)
    embed.add_field(name="💬 중계 상황", value="상대방이 소개팅 장소에 도착하여 문을 열고 들어옵니다... 🚪", inline=False)
    live_msg = await ctx.send(embed=embed)

    await asyncio.sleep(2.5)

    # 대사 목록
    situations = [
        "님은 긴장해서 물을 마시다가 예빈이 옷에 다 쏟아 호감도가 대폭 하락했습니다! 💦",
        "님이 약속 장소에 세련되고 멋있는 차를 타고 와서 예빈이의 호감도가 1 상승하였습니다! 🚗",
        "님이 며칠 안 씻었는지 냄새가 진동을 하여 예빈이가 코를 막아 소개팅 실패 위기입니다! 🤢",
        "님이 식사를 허겁지겁 너무 쩝쩝거리며 먹어 예빈이의 표정이 어두워집니다... 🥩",
        "님의 유머 감각이 완벽 적중! 예빈이가 귀엽다며 깔깔 웃어 호감도가 대폭 상승합니다! 🤣",
        "님이 밥값을 계산할 때 화장실 간 척하며 은근슬쩍 커피도 안 사줘서 예빈이와의 소개팅이 실패 쪽으로 기울어집니다! ☕",
        "님이 화려하고 센스 넘치는 패션 코디로 나타나 예빈이와의 소개팅에서 첫인상 점수 압승을 거둡니다! ✨"
    ]

  
    loop_count = 3 if len(participants) > 1 else 2
    for i in range(loop_count):
        target_user = random.choice(participants)
        chosen_situation = random.choice(situations)
        
        status_text = f"⏳ **[상황 {i+1}]** {target_user.mention}{chosen_situation}"
        embed.set_field_at(1, name="💬 중계 상황", value=status_text, inline=False)
        await live_msg.edit(embed=embed)
        await asyncio.sleep(3.0)

    # 최종 매칭 결과 발표 정산
    winner = random.choice(participants)
    user_money[winner.id] = user_money.get(winner.id, 1000) + total_pool

    embed.title = "🎉 소개팅 최종 커플 매칭 완료!"
    embed.remove_field(1) # 기존 중계상황 필드 제거
    
    success_msg = (
        f"👑 매력 발산에 완벽하게 성공한 **{winner.mention}** 님이 최종 선택을 받았습니다!\n"
        f"💖 **커플 탄생 성공!** 축하드립니다!\n\n"
        f"💵 **정산 독식금:** 총 **{total_pool:,}원** 수령 완료!\n"
        f"🏦 **{winner.name}님의 최종 잔액:** {user_money[winner.id]:,}원"
    )
    embed.add_field(name="💕 매칭 결과 발표 💕", value=success_msg, inline=False)
    await live_msg.edit(embed=embed)

    save_user_db(winner.id)

# --- 📅 추가 기능: 출석 체크 시스템 ---
@bot.command()
async def 출석(ctx):
    uid = ctx.author.id
    # 현재 시간 기준 날짜
    today = datetime.date.today().isoformat()
    
    if uid not in attendance_data:
        attendance_data[uid] = {"streak": 0, "total": 0, "last_date": ""}
    
    # [핵심] 오늘 이미 출석했는지 정확히 확인
    if attendance_data[uid].get("last_date") == today:
        return await ctx.send("❌ 오늘은 이미 출석하셨습니다. 내일 다시 시도해주세요!")
    
    # 연속 출석 체크 (어제 출석했는지 확인)
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if attendance_data[uid].get("last_date") != yesterday:
        attendance_data[uid]["streak"] = 1 # 끊겼으면 1일부터 시작
    else:
        attendance_data[uid]["streak"] += 1
        
    attendance_data[uid]["total"] += 1
    attendance_data[uid]["last_date"] = today
    user_money[uid] = user_money.get(uid, 1000) + 500
    
    save_user_db(uid)
    await ctx.send(f"✅ 출석 완료! (+500원) 현재 연속 출석: {attendance_data[uid]['streak']}일째")

# --- 🎁 신규 기능: 10분 주기 랜덤 선물 기능 ---
@bot.command()
async def 선물(ctx):
    uid = ctx.author.id
    user_names[uid] = ctx.author.name
    now = datetime.datetime.now()
    if uid in gift_cooldowns:
        if now - gift_cooldowns[uid] < datetime.timedelta(minutes=10):
            return await ctx.send("⏱️ 선물을 받으려면 아직 쿨타임이 남았습니다! (10분 주기)")
            
    reward = random.randint(1000, 30000)
    user_money[uid] = user_money.get(uid, 1000) + reward
    gift_cooldowns[uid] = now
    await ctx.send(f"🎁 깜짝 보상 도착! **{ctx.author.name}**님에게 **+{reward:,}원**이 지급되었습니다.")

    save_user_db(uid)

# --- 🚨 신규 기능: 올인 구제 재난지원금 기능 ---
@bot.command()
async def 재난지원금(ctx):
    uid = ctx.author.id
    user_names[uid] = ctx.author.name
    if user_money.get(uid, 1000) > 0: return await ctx.send("❌ 돈이 남아있어 신청할 수 없습니다.")
    now = datetime.datetime.now()
    if uid in disaster_cooldowns:
        if now - disaster_cooldowns[uid] < datetime.timedelta(hours=12):
            return await ctx.send("⚠️ 12시간 구제 제한에 걸려있습니다.")
            
    reward = random.randint(10000, 100000)
    user_money[uid] = reward
    disaster_cooldowns[uid] = now
    await ctx.send(f"🚨 파산 복구 완료! **{ctx.author.name}**님에게 긴급 지원금 **+{reward:,}원**이 지급되었습니다.")

    save_user_db(uid)

# --- 💸 유저 간 실시간 송금 시스템 ---
@bot.command()
async def 송금(ctx, receiver: discord.Member, amount: int):
    await asyncio.sleep(0.3)
    sender = ctx.author
    
    # 1. 예외 처리: 자기 자신 송금 불가 및 0원 이하 방지
    if sender.id == receiver.id:
        return await ctx.send("❌ 자기 자신에게는 송금할 수 없습니다.")
    if receiver.bot:
        return await ctx.send("❌ 봇에게는 돈을 보낼 수 없습니다.")
    if amount <= 0:
        return await ctx.send("⚠️ 송금 금액은 최소 1원 이상이어야 합니다.")
    if user_money.get(sender.id, 1000) < amount:
        return await ctx.send(f"❌ 잔액이 부족합니다. (현재 보유 잔액: `{user_money.get(sender.id, 1000):,}원`)")
        
    # 2. 송금 로직
    user_money[sender.id] -= amount
    user_money[receiver.id] = user_money.get(receiver.id, 1000) + amount
    user_names[sender.id] = sender.name
    user_names[receiver.id] = receiver.name
    
    # [핵심] DB 저장 (보내는 사람, 받는 사람 둘 다!)
    save_user_db(sender.id)
    save_user_db(receiver.id)
    
    # 3. 결과 출력 (보낸사람 / 받는사람 / 송금액 명시)
    embed = discord.Embed(title="💸 송금 완료", color=discord.Color.teal())
    embed.add_field(name="📤 보낸 사람", value=sender.mention, inline=True)
    embed.add_field(name="📥 받는 사람", value=receiver.mention, inline=True)
    embed.add_field(name="💰 송금된 금액", value=f"`{amount:,}원`", inline=False)
    embed.set_footer(text="데이터베이스에 즉시 반영되었습니다.")
    
    await ctx.send(embed=embed)

# --- 📢 세련된 임베드 공지사항 알림 시스템 ---
@bot.command()
@commands.has_permissions(administrator=True)
async def 공지(ctx, *, args: str = None):
    if not args or "|" not in args:
        return await ctx.send("⚠️ 사용법: `!공지 [제목] | [내용]` 형식을 맞춰 입력해 주세요. (중간에 세로 바 `|` 필수)")

    try: await ctx.message.delete()
    except: pass

    parts = args.split("|", 1)
    title_text = parts[0].strip()
    content_text = parts[1].strip()

    embed = discord.Embed(
        title=f"📢 {title_text}",
        description=content_text,
        color=discord.Color.from_rgb(255, 65, 105),
        timestamp=datetime.datetime.now()
    )
    
    avatar_url = ctx.author.display_avatar.url
    embed.set_author(name=f"작성자: {ctx.author.name}", icon_url=avatar_url)
    embed.set_footer(text="공지사항을 확인해 주시기 바랍니다.")
    await ctx.send(content="@everyone", embed=embed)

# --- 🏆 통합 랭킹 시스템 ---
@bot.command()
async def 랭킹(ctx):
    # 1. DB에서 모든 유저 데이터 가져오기
    all_users = list(users_col.find({}))
    if not all_users:
        return await ctx.send("데이터가 없습니다.")

    # 2. 데이터 가공 (총자산 = 현금 + 주식가치)
    ranking_data = []
    for u in all_users:
        uid = u["_id"]
        money = u.get("money", 1000)
        st = u.get("stocks", {})
        # 현재 주식 가격 기준 가치 계산
        stock_val = sum([stocks.get(name, 0) * count for name, count in st.items()])
        ranking_data.append({
            "name": u.get("name", "알수없음"),
            "total": money + stock_val,
            "profit": u.get("profit", 0),
            "att": u.get("attendance", {"total": 0})["total"]
        })

    # 3. 정렬 함수
    sorted_money = sorted(ranking_data, key=lambda x: x["total"], reverse=True)[:3]
    sorted_profit = sorted(ranking_data, key=lambda x: x["profit"], reverse=True)[:3]
    top_att = max(ranking_data, key=lambda x: x["att"])

    # 4. 임베드 작성
    embed = discord.Embed(title="🏆 서버 통합 랭킹 시스템", color=discord.Color.gold())
    
    # 자산 랭킹
    m_text = "\n".join([f"{['🥇', '🥈', '🥉'][i]} {r['name']}: `{r['total']:,}원`" for i, r in enumerate(sorted_money)])
    embed.add_field(name="💰 최고의 자산가 TOP 3", value=m_text, inline=False)
    
    # 수익왕 랭킹
    p_text = "\n".join([f"{['🥇', '🥈', '🥉'][i]} {r['name']}: `{r['profit']:,}원`" for i, r in enumerate(sorted_profit)])
    embed.add_field(name="📈 주식 수익왕 TOP 3", value=p_text or "기록 없음", inline=False)
    
    # 출첵왕
    embed.add_field(name="🔥 성실 보스! 출첵왕", value=f"📅 {top_att['name']}님 (`{top_att['att']}회 출석`)", inline=False)

    embed.set_footer(text="꾸준한 노력으로 상위권에 도전하세요!")
    await ctx.send(embed=embed)

@bot.command()
async def 블랙잭(ctx, bet: int = 1000): await play_blackjack(ctx, bet)

# --- 📢 대신 말하기 기능 ---
@bot.command()
async def 말해(ctx, channel: discord.TextChannel, *, message: str):
    # 1. 메시지 보낼 채널에 전송
    await channel.send(message)
    
    # 2. 명령어 입력한 메시지 삭제 (깔끔하게 흔적 지움)
    await ctx.message.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def 정보(ctx, m: discord.Member = None):
    m = m or ctx.author
    uid = m.id
    
    # 1. DB에서 가장 최신 데이터를 강제로 불러오기 (이게 핵심!)
    data = users_col.find_one({"_id": uid})
    if data:
        user_money[uid] = data.get("money", 1000)
        user_stocks[uid] = data.get("stocks", {})
        user_stats[uid] = data.get("stats", {"atk": 10, "lvl": 1, "強化": 0, "dungeon_floor": 1})
    
    # 2. 값 가져오기
    money = user_money.get(uid, 1000)
    my_stocks = user_stocks.get(uid, {})
    stats = user_stats.get(uid, {"atk": 10, "lvl": 1, "強化": 0, "dungeon_floor": 1})
    
    # 3. 주식 요약 만들기
    stock_summary = "\n".join([f"- {name}: {info['qty']}주" for name, info in my_stocks.items() if info['qty'] > 0])
    if not stock_summary: stock_summary = "보유 주식 없음"

    embed = discord.Embed(title=f"📋 {m.name}님의 상세 정보", color=discord.Color.blue())
    embed.add_field(name="💰 자산", value=f"{money:,}원", inline=True)
    embed.add_field(name="⚔️ 전투 스탯", value=f"공격력: {stats['atk']}\n강화: +{stats['強化']}\n던전층수: {stats['dungeon_floor']}층", inline=True)
    embed.add_field(name="📈 보유 주식", value=stock_summary, inline=False)
    embed.set_footer(text=f"조회 관리자: {ctx.author.name}")
    
    await ctx.send(embed=embed)

# --- 관리자 전용 : 호재악재 강제 실행 ---
@bot.command()
@commands.has_permissions(administrator=True)
async def 강제뉴스(ctx):
    global force_next_event, last_force_news_time
    now = datetime.datetime.now()
    
    # 2시간 쿨타임 체크 (timedelta(hours=1))
    if now - last_force_news_time < datetime.timedelta(hours=1):
        remaining = datetime.timedelta(hours=1) - (now - last_force_news_time)
        minutes_left = int(remaining.total_seconds() / 60)
        return await ctx.send(f"❌ **쿨타임 중입니다.** {minutes_left}분 뒤에 사용 가능합니다.")
    
    force_next_event = True
    last_force_news_time = now
    await ctx.send("✅ **다음 턴에 무조건 시장 이벤트(호재/악재)가 발생하도록 예약했습니다!**")


# --- 👑 관리자 전용: 유저 전체 데이터 조회 ---
@bot.command()
@commands.has_permissions(administrator=True)
async def 유저정보(ctx, m: discord.Member):
    uid = m.id
    # 데이터 가져오기 (없는 경우 기본값 설정)
    money = user_money.get(uid, 1000)
    stats = user_stats.get(uid, {"atk": 10, "lvl": 1, "強化": 0, "dungeon_floor": 1})
    my_stocks = user_stocks.get(uid, {}) # 주의: 코드에 user_stocks 선언이 필요합니다
    
    # 주식 요약
    stock_summary = "\n".join([f"- {name}: {qty}주" for name, qty in my_stocks.items() if qty > 0])
    if not stock_summary: stock_summary = "보유 주식 없음"

    embed = discord.Embed(title=f"📋 {m.name}님의 상세 정보", color=discord.Color.blue())
    embed.add_field(name="💰 자산", value=f"{money:,}원", inline=True)
    embed.add_field(name="⚔️ 전투 스탯", value=f"공격력: {stats['atk']}\n강화: +{stats['強化']}\n던전층수: {stats['dungeon_floor']}층", inline=True)
    embed.add_field(name="📈 보유 주식", value=stock_summary, inline=False)
    embed.set_footer(text=f"조회 관리자: {ctx.author.name}")
    
    await ctx.send(embed=embed)

# --- 👑 관리자 전용: 자산 지급 ---
@bot.command()
@commands.has_permissions(administrator=True)
async def 지급(ctx, m: discord.Member, a: int):
    uid = m.id
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 데이터 업데이트
    user_money[uid] = user_money.get(uid, 1000) + a
    user_names[uid] = m.name
    
    # DB 반영
    save_user_db(uid)
    
    embed = discord.Embed(title="💰 관리자 자산 관리 [지급]", color=discord.Color.green())
    embed.description = f"🏦 지급 대상: {m.mention}\n📈 지급된 금액: `+{a:,}원`\n🕒 처리 시간: `{now}`\n📊 최종 보유 자산: `{user_money[uid]:,}원`"
    embed.set_footer(text=f"수행 관리자: {ctx.author.name} | 실시간 DB 연동 완료")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def 게임초기화(ctx):
    uid = ctx.author.id
    if uid in game_states:
        game_states.pop(uid, None)
        await ctx.send("✅ 진행 중이던 게임 상태를 강제로 초기화했습니다. 이제 다시 게임을 시작하세요!")
    else:
        await ctx.send("ℹ️ 현재 진행 중인 게임이 없습니다.")

# --- 👑 관리자 전용: 자산 회수 ---
@bot.command()
@commands.has_permissions(administrator=True)
async def 회수(ctx, m: discord.Member, a: int):
    uid = m.id
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    current_money = user_money.get(uid, 1000)
    user_money[uid] = current_money - a
    user_names[uid] = m.name
    
    # DB 반영
    save_user_db(uid)
    
    embed = discord.Embed(title="🛑 관리자 자산 관리 [회수]", color=discord.Color.red())
    embed.description = f"🏦 대상자: {m.mention}\n📉 차감된 금액: `-{a:,}원`\n🕒 처리 시간: `{now}`\n📊 최종 보유 자산: `{user_money[uid]:,}원`"
    embed.set_footer(text=f"수행 관리자: {ctx.author.name} | 실시간 DB 연동 완료")
    await ctx.send(embed=embed)

# 수정 추천: 데이터를 저장할 때 아주 미세한 간격을 두어 차단을 방지합니다.
@bot.command()
@commands.has_permissions(administrator=True)
async def DB저장(ctx):
    count = 0
    for uid in user_money.keys():
        save_user_db(uid)
        count += 1
        await asyncio.sleep(0.5) # 0.5초씩 쉬면서 저장하여 차단을 방지
    await ctx.send(f"✅ {count}명의 유저 데이터를 관리자 권한으로 강제 저장하였습니다.")

@bot.command()
@commands.has_permissions(administrator=True)
async def 청소(ctx, n: int): await ctx.channel.purge(limit=n + 1)

# [데이터 로드 함수 추가]
def load_all_data():
    global stocks, user_money, user_stocks, user_names, attendance_data, user_stats, user_profits
    try:
        all_users = list(users_col.find())
        for doc in all_users:
            uid = doc["_id"]
            user_money[uid] = doc.get("money", 1000)
            user_stocks[uid] = doc.get("stocks", {})
            user_names[uid] = doc.get("name", "알수없음")
            attendance_data[uid] = doc.get("attendance", {"streak": 0, "total": 0, "last_date": ""})
            # 아래 데이터들을 추가로 로드해야 합니다.
            user_stats[uid] = doc.get("stats", {"atk": 10, "lvl": 1, "強化": 0, "dungeon_floor": 1})
            user_profits[uid] = doc.get("profit", 0)
        print("📥 데이터베이스에서 모든 유저 데이터를 로드했습니다.")
    except Exception as e:
        print(f"⚠️ 데이터 로드 중 오류 발생: {e}")

@bot.event
async def on_ready():
    print(f"✅ {bot.user} 로그인 완료!")
    
    # 1. DB에서 데이터 불러오기
    load_all_data() 
    print("📥 데이터베이스 데이터 로드 완료.")
    
    # 2. 주식 변동 루프 시작 (이게 없으면 차트가 안 올라옵니다!)
    if not update_stocks.is_running():
        update_stocks.start()
        print("🚀 주식 변동 시스템 루프가 시작되었습니다.")
    else:
        print("ℹ️ 루프가 이미 실행 중입니다.")

def sync_user_data(uid, name="알수없음"):
    # 메모리에 데이터가 이미 있으면 그냥 통과
    if uid in user_money:
        return
    
    # 메모리에 없으면 DB에서 즉시 조회
    data = users_col.find_one({"_id": uid})
    if data:
        user_money[uid] = data.get("money", 1000)
        user_stocks[uid] = data.get("stocks", {})
        user_names[uid] = data.get("name", name)
        attendance_data[uid] = data.get("attendance", {"streak": 0, "total": 0, "last_date": ""})
        user_stats[uid] = data.get("stats", {"atk": 10, "lvl": 1, "強化": 0, "dungeon_floor": 1})
        user_profits[uid] = data.get("profit", 0)
    else:
        # DB에도 없으면 신규 유저로 기본값 설정
        user_money[uid] = 1000
        user_stocks[uid] = {}
        user_names[uid] = name

@app.route('/api/healthz')
def health():
    return {"status": "ok"}, 200

# 1. 봇 실행 함수
if __name__ == "__main__":
    # Flask 서버를 별도 스레드로 먼저 띄우기
    def run_flask():
        app.run(host="0.0.0.0", port=5000)

    # 스레드 설정
    t = Thread(target=run_flask)
    t.daemon = True # 프로그램이 종료되면 Flask도 자동으로 꺼지게 함
    t.start()

    # 봇 실행 (이게 없으면 봇이 안 켜집니다!)
    # Render 환경변수(BOT_TOKEN)를 정확히 가져옵니다.
    token = os.environ.get('BOT_TOKEN')
    if token:
        bot.run(token)
    else:
        print("❌ 에러: BOT_TOKEN 환경 변수가 설정되지 않았습니다!")