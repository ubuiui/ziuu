import os, asyncio, datetime, random
import discord
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread
from pymongo import MongoClient
import certifi

# [중요] 봇 선언
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
bot = commands.Bot(command_prefix='!', intents=intents)

# [중요] 절대 죽지 않는 DB 연결 로직
client = None
db = None
users_col = None

try:
    # SSL 인증서 문제를 회피하면서 연결 시도
    client = MongoClient(os.environ.get('MONGO_URI'), 
                         serverSelectionTimeoutMS=5000,
                         tlsCAFile=certifi.where())
    db = client["stock_game"]
    users_col = db["users"]
    client.server_info() # 연결 확인
    print("✅ MongoDB 연결 성공!")
except Exception as e:
    print(f"⚠️ MongoDB 연결 실패, 오프라인 모드로 시작합니다: {e}")

def load_all_data():
    if users_col is None: 
        return
    try:
        cursor = users_col.find({})
        for doc in cursor:
            uid = doc["_id"]
            user_money[uid] = doc.get("money", 1000)
            user_stocks[uid] = doc.get("stocks", {})
            user_names[uid] = doc.get("name", "알수없음")
            attendance_data[uid] = doc.get("attendance", {"streak": 0, "total": 0, "last_date": ""})
            user_stats[uid] = doc.get("stats", {"atk": 10, "lvl": 1, "強化": 0, "dungeon_floor": 1})
        print("✅ 데이터 로드 완료")
    except Exception as e:
        print(f"⚠️ 데이터 로드 중 에러: {e}")

user_money = {}
user_stocks = {}
user_names = {}
attendance_data = {}
game_states = {}
gift_cooldowns = {}
disaster_cooldowns = {}
user_stats = {}

stocks = {
    "예빈닉스": 123000, "지유엔터": 15000, "헬프미": 8000, 
    "명철수산": 12000, "찬우상사": 9500, "예원데이터": 25000, 
    "민지유건설": 18000, "피브테크": 7000, "루카드림": 13000, "우뱅미디어": 11000,
    "어둠반도체": 19000, "여름전자": 80200, "해나물류": 3000, "헤응인터내셔널": 1000
}

def save_user_db(uid):
    if users_col is None: return
    # DB 저장 전 살짝 대기
    # 이미 명령어에서 asyncio.sleep을 썼더라도 여기서도 0.1초 대기
    users_col.update_one(
        {"_id": uid},
        {"$set": {
            "money": user_money.get(uid, 1000),
            "stocks": user_stocks.get(uid, {}),
            "name": user_names.get(uid, "알수없음"),
            "attendance": attendance_data.get(uid, {"streak": 0, "last_date": ""})
        }},
        upsert=True
    )
        if result.acknowledged:
            print(f"✅ 유저 {uid} 데이터 DB 저장 완료!")
    except Exception as e:
        print(f"❌ DB 저장 오류: {e}")

def load_all_data():
    global user_money, user_stocks, user_names, attendance_data, user_stats
    for data in users_col.find():
        uid = data["_id"]
        user_money[uid] = data.get("money", 1000)
        user_stocks[uid] = data.get("stocks", {})
        user_names[uid] = data.get("name", "알수없음")
        attendance_data[uid] = data.get("attendance", {"streak": 0, "total": 0, "last_date": ""})
        user_stats[uid] = data.get("stats", {"atk": 10, "lvl": 1, "強化": 0, "dungeon_floor": 1})
    print("✅ MongoDB에서 모든 데이터를 성공적으로 로드했습니다.")

# [기존 코드의 나머지 부분은 그대로 유지하되, 각 명령어 함수 끝에 save_user_db(ctx.author.id)를 추가하세요]
# 예: !매수 함수 마지막에 save_user_db(ctx.author.id) 추가

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
@tasks.loop(minutes=3)
async def update_stocks():
    # 1. 기본 변동 (일반적인 시장 등락)
    for stock in stocks:
        change_rate = random.uniform(0.97, 1.04) 
        stocks[stock] = int(stocks[stock] * change_rate)
        if stocks[stock] < 100: stocks[stock] = 100
    
    # 2. 뉴스 생성 및 주가 즉시 반영 로직
    news_display = ""
    # 10% 확률로 뉴스 발생
    if random.random() < 0.1:  
        target_stock = random.choice(list(stocks.keys()))
        news_type = random.choice(["호재", "악재"])
        news_template = random.choice(NEWS_DB[news_type])
        
        # [핵심] 호재/악재에 따른 주가 강제 변동
        if news_type == "호재":
            stocks[target_stock] = int(stocks[target_stock] * 1.25) # 25% 폭등
            news_display = f"\n📢 **[경제 뉴스]** {news_template.format(name=target_stock)}\n🔥 **{target_stock} 주가 폭등!**"
        else:
            stocks[target_stock] = int(stocks[target_stock] * 0.75) # 25% 폭락
            news_display = f"\n📢 **[경제 뉴스]** {news_template.format(name=target_stock)}\n💥 **{target_stock} 주가 폭락!**"
            
    
    # 3. 채널 알림
    channel = bot.get_channel(NOTICE_CHANNEL_ID)
    if channel:
        msg = "📊 **[시장 상황 보고]**\n--------------------------\n"
        for name, price in stocks.items():
            msg += f"📈 {name}: {price:,}원\n"
        msg += "--------------------------"
        
        if news_display:
            msg += news_display
            
        msg += "\n사용법: `!매수 [종목명] [수량]`"
        await channel.send(msg)
        await asyncio.sleep(2)

# ==========================================
# [신규 기능: 주식, 강화, 던전, 보물찾기]
# ==========================================

@bot.command()
async def 매수(ctx, name: str, qty: int):
    uid = ctx.author.id
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

# --- 보유 주식 확인 기능 ---
@bot.command()
async def 내주식(ctx):
    uid = ctx.author.id
    my_stocks = user_stocks.get(uid, {})
    
    if not my_stocks:
        return await ctx.send("📉 현재 보유 중인 주식이 없습니다.")
    
    msg = "💰 **보유 주식 목록**\n"
    for name, data in my_stocks.items():
        if data["qty"] > 0:
            current_price = stocks[name]
            # 수익률 계산
            profit = ((current_price - data["avg_price"]) / data["avg_price"]) * 100
            profit_icon = "📈" if profit >= 0 else "📉"
            msg += f"- **{name}**: {data['qty']}주 | 평단가: {data['avg_price']:,}원 | 수익률: {profit_icon} {profit:.2f}%\n"
            
    await ctx.send(msg)

@bot.command()
async def 내정보(ctx):
    uid = ctx.author.id
    
    # 혹시 모를 로드 (DB에서 최신 데이터 가져오기)
    data = users_col.find_one({"_id": uid})
    if data:
        user_money[uid] = data.get("money", 1000)
        user_stocks[uid] = data.get("stocks", {})
        attendance_data[uid] = data.get("attendance", {"streak": 0, "total": 0, "last_date": ""})
    
    money = user_money.get(uid, 1000)
    stocks_info = user_stocks.get(uid, {})
    
    # 주식 목록 문자열 만들기
    stock_str = "\n".join([f"{name}: {info['qty']}주 (평단: {info['avg_price']:,}원)" for name, info in stocks_info.items()])
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

# --------------------

app = Flask('')
@app.route('/')
def home(): 
    return "OK", 200

def get_score(hand):
    score = 0; aces = 0
    for card in hand:
        rank = card[:-1]
        score += 10 if rank in ['J','Q','K'] else (11 if rank == 'A' else int(rank))
        if rank == 'A': aces += 1
    while score > 21 and aces: score -= 10; aces -= 1
    return score

def create_embed(uid, data, msg="진행 중", is_final=False):
    embed = discord.Embed(title="♠️ 블랙잭 게임 ♣️", color=discord.Color.gold())
    embed.add_field(name="나의 카드", value=f"{' '.join(data['p'])} (합: {get_score(data['p'])})", inline=True)
    dealer_val = f"{' '.join(data['d'])} (합: {get_score(data['d'])})" if is_final else f"{data['d'][0]} [??]"
    embed.add_field(name="딜러 카드", value=dealer_val, inline=True)
    embed.add_field(name="상태 정보", value=f"베팅액: {data['bet']}원\n총 자산: {user_money.get(uid, 1000)}원\n결과: {msg}", inline=False)
    if not is_final:
        embed.set_footer(text="💬 채팅창에 [ㅎ / ㅅ / ㄷ / ㅍ] 중 하나를 입력하세요! (제한시간 60초)")
    return embed

async def ask_next_game(ctx, current_bet):
    uid = ctx.author.id
    game_states.pop(uid, None)
    final_money = user_money.get(uid, 1000)
    
    if final_money < 1000:
        return await ctx.send("❌ 잔액이 부족(1000원 미만)하여 게임을 종료합니다.")
        
    await ctx.send(
        f"🔄 **다음 게임을 선택하세요!** [현재 자산: {final_money}원]\n"
        f"💬 채팅창에 번호를 입력하세요 (제한시간 30초):\n"
        f"**1** : 동일 배팅 진행 ({current_bet}원)\n"
        f"**2** : 2배 배팅 진행 ({current_bet * 2}원)\n"
        f"**3** : 게임 종료"
    )

    def check(m):
        return m.author.id == uid and m.channel.id == ctx.channel.id and m.content.strip() in ['1', '2', '3']

    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        choice = msg.content.strip()
        
        if choice == '1':
            await play_blackjack(ctx, current_bet)
        elif choice == '2':
            await play_blackjack(ctx, current_bet * 2)
        else:
            await ctx.send("👋 게임을 종료합니다.")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ 30초 내에 선택하지 않아 게임이 종료되었습니다.")

async def play_blackjack(ctx, bet):
    uid = ctx.author.id
    user_names[uid] = ctx.author.name
    if bet < 1000: return await ctx.send("⚠️ 최소 배팅 1000원부터 가능합니다.")
    if bet > user_money.get(uid, 1000): return await ctx.send("❌ 잔액이 부족하여 게임을 시작할 수 없습니다.")
    if uid in game_states: return await ctx.send("이미 진행 중인 게임이 있습니다.")
    
    game_states[uid] = True
    deck = [r+s for s in ['♠','♥','◆','♣'] for r in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']]
    random.shuffle(deck)
    p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
    data = {'deck': deck, 'p': p, 'd': d, 'bet': bet}
    
    main_msg = await ctx.send(embed=create_embed(uid, data))
    
    if get_score(p) == 21:
        game_states.pop(uid, None)
        if get_score(d) == 21:
            await main_msg.edit(embed=create_embed(uid, data, "🤝 양측 모두 블랙잭! 무승부 처리되었습니다.", is_final=True))
        else:
            win = bet * 10
            user_money[uid] = user_money.get(uid, 1000) + win
            await main_msg.edit(embed=create_embed(uid, data, f"🎉 블랙잭(10배)! +{win}원", is_final=True))
            
        await ask_next_game(ctx, bet)
        return

    def check_action(m):
        if m.author.id != uid or m.channel.id != ctx.channel.id:
            return False
        val = m.content.strip().lower()
        return val in ['ㅎ', 'ㅎㅌ', '히트', 'hit', 'ㅅ', 'ㅅㅌ', '스테이', 'stay', 'ㄷ', 'ㄷㅂ', '더블', 'double', 'ㅍ', 'ㅍㄱ', '포기', 'surrender']

    while uid in game_states:
        try:
            action_msg = await bot.wait_for('message', check=check_action, timeout=60.0)
            user_input = action_msg.content.strip().lower()
            
            try: await action_msg.delete()
            except: pass

            if user_input in ['ㅎ', 'ㅎㅌ', '히트', 'hit']:
                data['p'].append(data['deck'].pop())
                if get_score(data['d']) < 17 and get_score(data['p']) <= 21:
                    data['d'].append(data['deck'].pop())

                if get_score(data['p']) > 21:
                    user_money[uid] = user_money.get(uid, 1000) - data['bet']
                    await main_msg.edit(embed=create_embed(uid, data, "💥 버스트! 패배", is_final=True))
                    await ask_next_game(ctx, data['bet'])
                    return
                else:
                    await main_msg.edit(embed=create_embed(uid, data, "진행 중 (히트함)"))

            elif user_input in ['ㅅ', 'ㅅㅌ', '스테이', 'stay']:
                while get_score(data['d']) < 17:
                    data['d'].append(data['deck'].pop())
                    
                ps, ds = get_score(data['p']), get_score(data['d'])
                res_msg = "🏆 승리!" if (ds > 21 or ps > ds) else ("❌ 패배!" if ps < ds else "🤝 무승부")
                
                if "승리" in res_msg: user_money[uid] = user_money.get(uid, 1000) + data['bet']
                elif "패배" in res_msg: user_money[uid] = user_money.get(uid, 1000) - data['bet']
                
                await main_msg.edit(embed=create_embed(uid, data, res_msg, is_final=True))
                await ask_next_game(ctx, data['bet'])
                return

            elif user_input in ['ㄷ', 'ㄷㅂ', '더블', 'double']:
                if (data['bet'] * 2) > user_money.get(uid, 1000):
                    await ctx.send("⚠️ 잔액이 부족하여 더블다운이 불가능합니다.", delete_after=3)
                    continue
                
                data['bet'] *= 2
                data['p'].append(data['deck'].pop())
                while get_score(data['d']) < 17:
                    data['d'].append(data['deck'].pop())
                    
                ps, ds = get_score(data['p']), get_score(data['d'])
                if ps > 21:
                    res_msg = "💥 버스트! 패배"
                    user_money[uid] = user_money.get(uid, 1000) - data['bet']
                else:
                    res_msg = "🏆 승리!" if (ds > 21 or ps > ds) else ("❌ 패배!" if ps < ds else "🤝 무승부")
                    if "승리" in res_msg: user_money[uid] = user_money.get(uid, 1000) + data['bet']
                    elif "패배" in res_msg: user_money[uid] = user_money.get(uid, 1000) - data['bet']
                    
                await main_msg.edit(embed=create_embed(uid, data, f"더블다운 ➡️ {res_msg}", is_final=True))
                await ask_next_game(ctx, data['bet'])
                return

            elif user_input in ['ㅍ', 'ㅍㄱ', '포기', 'surrender']:
                user_money[uid] = user_money.get(uid, 1000) - (data['bet'] // 2)
                await main_msg.edit(embed=create_embed(uid, data, "🏳️ 포기함 (절반 회수)", is_final=True))
                await ask_next_game(ctx, data['bet'])
                return

        except asyncio.TimeoutError:
            game_states.pop(uid, None)
            await main_msg.edit(content="⏱️ 제한시간 초과로 게임이 자동 취소되었습니다.", embed=None)
            return

# --- 🚀 [공통 시스템] 미니게임용 묻고 더블로 가! 로직 ---
async def start_double_or_nothing(ctx, current_win_prize, original_bet, game_name):
    uid = ctx.author.id
    current_prize = current_win_prize
    stage = 1

    while True:
        success_rate = max(0.70 - (stage - 1) * 0.10, 0.10)
        success_percentage = int(success_rate * 100)
        fail_percentage = 100 - success_percentage

        embed = discord.Embed(title=f"🔥 {game_name} - 묻고 더블로 가! (Stage {stage})", color=discord.Color.red())
        embed.description = (
            f"현재 누적 상금: **{current_prize:,}원**\n\n"
            f"💬 채팅창에 다음 중 하나를 입력하세요 (제한시간 15초):\n"
            f"👉 **`묻더`** : **{success_percentage}% 성공 확률**로 도전! 성공 시 상금이 **2.5배**로 떡상! ({int(current_prize * 2.5):,}원)\n"
            f"👉 **`스톱`** : 여기서 멈추고 현재 상금을 안전하게 수령합니다."
        )
        embed.set_footer(text=f"⚠️ 실패 확률은 {fail_percentage}%이며, 실패 시 상금은 0원이 되고 원금도 날아갑니다!")
        double_msg = await ctx.send(embed=embed)

        def check(m):
            return m.author.id == uid and m.channel.id == ctx.channel.id and m.content.strip() in ['묻더', '스톱']

        try:
            choice_msg = await bot.wait_for('message', check=check, timeout=15.0)
            user_choice = choice_msg.content.strip()
            try: await choice_msg.delete()
            except: pass
            await double_msg.delete()

            if user_choice == '묻더':
                if random.random() < success_rate:
                    current_prize = int(current_prize * 2.5)
                    stage += 1
                    continue
                else:
                    user_money[uid] = user_money.get(uid, 1000) - original_bet
                    fail_embed = discord.Embed(title="💥 묻더 실패! 올인 파산", color=discord.Color.dark_gray())
                    fail_embed.description = f"앗.. {fail_percentage}%의 실패 확률을 뚫지 못하고 실패했습니다.\n상금은 공중분해되었으며 배팅 원금 **-{original_bet:,}원**이 차감됩니다.\n현재 잔액: {user_money[uid]:,}원"
                    await ctx.send(embed=fail_embed)
                    return
            else:
                net_profit = current_prize - original_bet
                user_money[uid] = user_money.get(uid, 1000) + net_profit
                stop_embed = discord.Embed(title="💰 묻더 스톱! 정산 완료", color=discord.Color.green())
                stop_embed.description = f"현명한 선택! Stage {stage-1}에서 멈췄습니다.\n최종 획득 자산: **+{current_prize:,}원**\n현재 잔액: {user_money[uid]:,}원"
                await ctx.send(embed=stop_embed)
                return

        except asyncio.TimeoutError:
            await double_msg.delete()
            net_profit = current_prize - original_bet
            user_money[uid] = user_money.get(uid, 1000) + net_profit
            timeout_embed = discord.Embed(title="⏱️ 시간 초과 자동 정산", color=discord.Color.green())
            timeout_embed.description = f"시간이 초과되어 현재 금액으로 안전 정산되었습니다.\n최종 획득 자산: **+{current_prize:,}원**\n현재 잔액: {user_money[uid]:,}원"
            await ctx.send(embed=timeout_embed)
            return

# --- 🎯 [공통 시스템] 다중 참가자 멀티 배팅방 수집 로직 ---
async def setup_multi_bet_game(ctx, bet_amount, game_title):
    creator = ctx.author
    if bet_amount < 1000:
        await ctx.send("⚠️ 최소 배팅 금액은 1000원입니다.")
        return None
    if user_money.get(creator.id, 1000) < bet_amount:
        await ctx.send(f"❌ 잔액이 부족하여 배팅방을 개설할 수 없습니다. (현재: {user_money.get(creator.id, 1000):,}원)")
        return None

    participants = [creator]
    user_names[creator.id] = creator.name

    def make_embed():
        mentions = ", ".join([u.mention for u in participants])
        embed = discord.Embed(title=f"🎲 {game_title} 배팅방 개설!", color=discord.Color.purple())
        embed.description = (
            f"방장: **{creator.name}**\n"
            f"인당 참가비(배팅금): **{bet_amount:,}원**\n\n"
            f"🙋‍♂️ 함께 돈을 걸고 참여하실 분은 **30초 내에 아래 ✋ 이모지(리액션)**를 눌러주세요!\n"
            f"**현재 참가자 ({len(participants)}명):**\n{mentions}"
        )
        return embed

    join_msg = await ctx.send(embed=make_embed())
    await join_msg.add_reaction("✋")

    end_time = datetime.datetime.now() + datetime.timedelta(seconds=30)
    
    while True:
        remaining = (end_time - datetime.datetime.now()).total_seconds()
        if remaining <= 0:
            break
        try:
            def reaction_check(r, u):
                return r.message.id == join_msg.id and str(r.emoji) == "✋" and not u.bot

            reaction, user = await bot.wait_for('reaction_add', check=reaction_check, timeout=remaining)
            
            if user not in participants:
                if user_money.get(user.id, 1000) >= bet_amount:
                    participants.append(user)
                    user_names[user.id] = user.name
                    await join_msg.edit(embed=make_embed())
                else:
                    await ctx.send(f"⚠️ {user.mention}님은 잔액이 부족하여 참여할 수 없습니다.", delete_after=3)
        except asyncio.TimeoutError:
            break

    try: await join_msg.delete()
    except: pass

    return participants

# --- 🏎️ 미니게임 1: 자동차 경주 게임 ---
@bot.command()
async def 경주(ctx, bet: int = 1000):
    uid = ctx.author.id
    user_names[uid] = ctx.author.name
    if bet < 1000: return await ctx.send("⚠️ 최소 배팅 1000원부터 가능합니다.")
    if bet > user_money.get(uid, 1000): return await ctx.send("❌ 잔액이 부족하여 시작할 수 없습니다.")
    if uid in game_states: return await ctx.send("이미 진행 중인 미니게임이 있습니다.")

    game_states[uid] = True
    cars = {"🔴 빨간예빈": 0, "🔵 파란예빈": 0, "🟢 초록예빈": 0, "🟡 노란예빈": 0}
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

    game_states.pop(uid, None)
    res_embed = discord.Embed(title="🏁 경주 종료 결과 🏁", color=discord.Color.gold())
    res_embed.description = status_text
    
    if winner == user_pick:
        win_money = bet * 3
        res_embed.add_field(name="🎉 축하합니다!", value=f"선택하신 **{user_pick}**가 1등을 했습니다!\n총 상금 **{win_money:,}원** 확보! 묻더 기능이 활성화됩니다.")
        await ctx.send(embed=res_embed)
        await start_double_or_nothing(ctx, win_money, bet, "자동차 경주")
    else:
        user_money[uid] = user_money.get(uid, 1000) - bet
        res_embed.add_field(name="❌ 아쉽습니다", value=f"승리한 예빈이는 **{winner}**였습니다. (선택: {user_pick})\n**-{bet:,}원** 차감 (현재 잔액: {user_money[uid]:,}원)")
        await ctx.send(embed=res_embed)

    save_user_db(uid)

# --- ⚡ 미니게임 2: 순발력 타자 게임 ---
@bot.command()
async def 타자(ctx):
    sentences = [
        "이루카와우뱅의환상적인콜라보레이션", "예원이가유튜브에지유를검색했을때", "피브와예빈이의끝없는유튜브대결", 
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
    user_names[uid] = ctx.author.name
    if bet < 1000: return await ctx.send("⚠️ 최소 배팅 1000원부터 가능합니다.")
    if bet > user_money.get(uid, 1000): return await ctx.send("❌ 잔액이 부족하여 슬롯을 돌릴 수 없습니다.")
    
    emojis = ["🍒", "🍇", "🍋", "🔔", "💎"]
    embed = discord.Embed(title="🎰 슬롯머신 가동 중...", description="[ 🪙 | 🪙 | 🪙 ]", color=discord.Color.orange())
    msg = await ctx.send(embed=embed)
    
    for _ in range(3):
        await asyncio.sleep(0.5)
        fake_slots = [random.choice(emojis) for _ in range(3)]
        embed.description = f"[ {fake_slots[0]} | {fake_slots[1]} | {fake_slots[2]} ]"
        await msg.edit(embed=embed)

    res = [random.choice(emojis) for _ in range(3)]
    embed.description = f"[ {res[0]} | {res[1]} | {res[2]} ]"
    
    is_win = False
    multiplier = 0
    msg_text = ""

    if res[0] == res[1] == res[2]:
        multiplier = 100
        msg_text = f"🎉🎉🎉 트리플 달성! 초대박 잭팟 완성!!! ({multiplier}배)"
        is_win = True
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
        multiplier = 1.5
        msg_text = "🔔 페어 성공! (1.5배)"
        is_win = True
    else:
        user_money[uid] = user_money.get(uid, 1000) - bet
        msg_text = "😭 꽝! 다음 기회에"

    embed.title = "🎯 슬롯머신 결과 발표"
    
    if is_win:
        win_money = int(bet * multiplier)
        embed.add_field(name="정산 결과", value=f"{msg_text}\n획득 예정 상금: **{win_money:,}원**\n\n잠시 후 **묻더** 선택 창이 활성화됩니다!")
        await msg.edit(embed=embed)
        await start_double_or_nothing(ctx, win_money, bet, "슬롯머신")
    else:
        embed.add_field(name="정산 결과", value=f"{msg_text}\n변동 금액: -{bet:,}원\n현재 자산: {user_money[uid]:,}원")
        await msg.edit(embed=embed)

    save_user_db(uid)

# --- 🪜 미니게임 4: 사다리 타기 배팅 게임 (출력 간소화 반영) ---
@bot.command()
async def 사다리(ctx, bet: int = None, *, args: str = None):
    if bet is None:
        return await ctx.send("⚠️ 사용법: `!사다리 [판돈]`")

    participants = await setup_multi_bet_game(ctx, bet, "사다리 타기")
    if not participants or len(participants) < 1:
        return await ctx.send("❌ 참가자가 없어 사다리 타기 게임이 취소되었습니다.")

    total_pool = bet * len(participants)
    deduct_msg = ""
    for p in participants:
        user_money[p.id] = user_money.get(p.id, 1000) - bet
        deduct_msg += f"💸 **{p.name}**님 잔액에서 -{bet:,}원 차감\n"
    
    await ctx.send(f"🪙 **[사다리 배팅금 즉시 차감 완료]** 🪙\n{deduct_msg}")

    winner = random.choice(participants)
    user_money[winner.id] = user_money.get(winner.id, 1000) + total_pool
    p_mentions = ", ".join([p.mention for p in participants])

    embed = discord.Embed(title="🪜 사다리 타기 결과 발표", color=discord.Color.blue())
    embed.add_field(name="👥 참여자 명단", value=p_mentions, inline=False)
    embed.add_field(name="🏆 최종 승리자", value=f"🎉 {winner.mention} 님 독식!!\n상금 **{total_pool:,}원**을 획득하셨습니다! (최종 잔액: {user_money[winner.id]:,}원)", inline=False)
    
    await ctx.send(content=f"🔔 {winner.mention} 축하합니다! 판돈을 모두 획득하셨습니다!", embed=embed)

# --- 🎰 미니게임 5: 멀티 룰렛 배팅 게임 (출력 간소화 반영) ---
@bot.command()
async def 룰렛(ctx, bet: int = None, *, args: str = None):
    if bet is None:
        return await ctx.send("⚠️ 사용법: `!룰렛 [판돈]`")

    participants = await setup_multi_bet_game(ctx, bet, "룰렛 돌리기")
    if not participants or len(participants) < 1:
        return await ctx.send("❌ 참가자가 없어 룰렛 게임이 취소되었습니다.")

    total_pool = bet * len(participants)
    deduct_msg = ""
    for p in participants:
        user_money[p.id] = user_money.get(p.id, 1000) - bet
        deduct_msg += f"💸 **{p.name}**님 잔액에서 -{bet:,}원 차감\n"
        
    await ctx.send(f"🪙 **[룰렛 배팅금 즉시 차감 완료]** 🪙\n{deduct_msg}")

    embed = discord.Embed(title="🎰 멀티 룰렛 돌리는 중...", description="🔮 과연 누가 독식할 것인가?! \n\n[ 🪙 🟥 🟨 🟩 🟦 🟪 ]", color=discord.Color.purple())
    msg = await ctx.send(embed=embed)
    
    spin_emojis = ["[ 🟥 🟨 🟩 🟦 🟪 ]", "[ 🟪 🟥 🟨 🟩 🟦 ]", "[ 🟦 🟪 🟥 🟨 🟩 ]"]
    for i in range(3):
        await asyncio.sleep(0.6)
        embed.description = f"🔮 과연 결과는?! \n\n{spin_emojis[i % len(spin_emojis)]}"
        await msg.edit(embed=embed)

    await asyncio.sleep(0.6)
    winner = random.choice(participants)
    user_money[winner.id] = user_money.get(winner.id, 1000) + total_pool
    p_mentions = ", ".join([p.mention for p in participants])

    result_embed = discord.Embed(title="🎯 룰렛 배팅 결과 발표", color=discord.Color.green())
    result_embed.add_field(name="👥 참여자 명단", value=p_mentions, inline=False)
    result_embed.add_field(name="🏆 최종 승리자", value=f"🎉 {winner.mention} 님 전액 독식!!\n상금 **{total_pool:,}원**을 획득하셨습니다! (최종 잔액: {user_money[winner.id]:,}원)", inline=False)
    
    await msg.edit(content=f"🔔 {winner.mention} 축하합니다! 대박 룰렛의 주인공이 되셨습니다!", embed=result_embed)

# --- ❤️ [신규 미니게임 6] 실시간 중계형 멀티 소개팅 배팅 게임 ---
@bot.command()
async def 소개팅(ctx, bet: int = None):
    if bet is None:
        return await ctx.send("⚠️ 사용법: `!소개팅 [판돈]`")

    # 참가자 모집 (기존 멀티 배팅방 수집 모듈 연동)
    participants = await setup_multi_bet_game(ctx, bet, "두근두근 소개팅")
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

    save_user_db(uid)

# --- 📅 추가 기능: 출석 체크 시스템 ---
@bot.command()
async def 출석(ctx):
    uid = ctx.author.id
    today = datetime.date.today().isoformat()
    
    # 1. 데이터 초기화 및 출석 로직
    if uid not in attendance_data:
        attendance_data[uid] = {"streak": 0, "total": 0, "last_date": ""}
    
    if attendance_data[uid]["last_date"] == today:
        return await ctx.send("❌ 오늘은 이미 출석하셨습니다.")
    
    # 출석 처리
    attendance_data[uid]["streak"] += 1
    attendance_data[uid]["total"] += 1
    attendance_data[uid]["last_date"] = today
    user_money[uid] = user_money.get(uid, 1000) + 500
    user_names[uid] = ctx.author.name
    
    # [핵심] DB 저장
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

    save_user_db(uid)

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
    embed = discord.Embed(title="👑 서버 종합 명예의 전당 👑", color=discord.Color.gold())

    sorted_money = sorted(user_money.items(), key=lambda x: x[1], reverse=True)[:3]
    money_text = ""
    money_emojis = ["🥇", "🥈", "🥉"]
    for idx, (uid, money) in enumerate(sorted_money):
        name = user_names.get(uid, f"유저({uid})")
        money_text += f"{money_emojis[idx]} **{idx+1}위** - {name} : `{money:,}원`\n"
    if not money_text: money_text = "기록이 없습니다."
    embed.add_field(name="💰 서버 최고의 자산가 TOP 3", value=money_text, inline=False)

    attendance_kings = sorted(attendance_data.items(), key=lambda x: x[1]["total"], reverse=True)
    att_text = "아직 출석체크 데이터가 없습니다."
    if attendance_kings:
        top_uid, top_data = attendance_kings[0]
        if top_data["total"] > 0:
            name = user_names.get(top_uid, f"유저({top_uid})")
            att_text = f"📅 **{name}**님 (누적 출석: `{top_data['total']}회` / 현재 연속: `{top_data['streak']}일`)"
    embed.add_field(name="🔥 성실 보스! 오늘의 출첵왕", value=att_text, inline=False)

    broke_users = [uid for uid, money in user_money.items() if money <= 0]
    broke_text = "❌ 현재 파산한 유저가 없습니다! 평화롭군요."
    if broke_users:
        names = [user_names.get(uid, f"유저({uid})") for uid in broke_users]
        broke_text = f"📉 💸 **{', '.join(names)}** (현재 자산 0원 이하)\n*💡 `!재난지원금` 명령어로 부활을 노려보세요!*"
    embed.add_field(name="🚨 비운의 주인공! 실시간 파산왕 명단", value=broke_text, inline=False)

    embed.set_footer(text="꾸준한 출석과 도박 한탕으로 타이틀을 쟁탈해 보세요!")
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ 봇 연결 성공: {bot.user}")
    load_all_data()
    print("💾 데이터 로드 완료.")
    
    # 루프 시작 전 충분한 여유 시간
    await asyncio.sleep(15) 
    
    if not update_stocks.is_running():
        update_stocks.start()
        print("📈 주식 루프 시작.")

@bot.command()
async def 블랙잭(ctx, bet: int = 1000): await play_blackjack(ctx, bet)

@bot.command()
async def 잔액(ctx): await ctx.send(f"💰 {ctx.author.name}님의 총 자산은 {user_money.get(ctx.author.id, 1000):,}원입니다.")

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

# 파일 최하단
if __name__ == "__main__":
    # Flask 서버용 (Render 유지용)
    def run_flask():
        app.run(host='0.0.0.0', port=10000)
    Thread(target=run_flask).start()

    # 디스코드 봇 시작
    bot.run(os.environ.get('BOT_TOKEN'))