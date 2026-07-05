import os, sys, asyncio, datetime, random
import urllib.request
import urllib.parse
import urllib.error

# --- [필수 라이브러리 자동 설치] ---
try:
    import discord
    from flask import Flask
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "discord.py", "flask"])
    import discord
    from flask import Flask

from discord.ext import commands, tasks

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- [데이터베이스 대용 메모리 저장소] ---
user_money = {}
game_states = {}
attendance_data = {}  # {uid: {"streak": 연속일수, "total": 누적일수, "last_date": "YYYY-MM-DD"}}
user_names = {}       # 랭킹 표시용 유저 이름 저장 {uid: name}

gift_cooldowns = {}       
disaster_cooldowns = {}   

# --- [설정 공간] ---
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@민지유_인데/live"  
NOTICE_CHANNEL_ID = 1520830878513762375  
IS_LIVE_NOW = False 
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
        await ctx.send("⏱️ 시간 초과로 게임 선택이 취소되었습니다.")

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
        embed = discord.Embed(title=f"🔥 {game_name} - 묻고 더블로 가! (Stage {stage})", color=discord.Color.red())
        embed.description = (
            f"현재 누적 상금: **{current_prize}원**\n\n"
            f"💬 채팅창에 다음 중 하나를 입력하세요 (제한시간 15초):\n"
            f"👉 **`묻더`** : **70% 성공 확률**로 도전! 성공 시 상금이 **2.5배**로 떡상! ({int(current_prize * 2.5)}원)\n"
            f"👉 **`스톱`** : 여기서 멈추고 현재 상금을 안전하게 수령합니다."
        )
        embed.set_footer(text="⚠️ 실패 확률은 30%이며, 실패 시 상금은 0원이 되고 원금도 날아갑니다!")
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
                if random.random() < 0.70:
                    current_prize = int(current_prize * 2.5)
                    stage += 1
                    continue
                else:
                    user_money[uid] = user_money.get(uid, 1000) - original_bet
                    fail_embed = discord.Embed(title="💥 묻더 실패! 올인 파산", color=discord.Color.dark_gray())
                    fail_embed.description = f"앗.. 30%의 확률을 뚫고 묻더에 실패했습니다.\n상금은 공중분해되었으며 배팅 원금 **-{original_bet}원**이 차감됩니다.\n현재 잔액: {user_money[uid]}원"
                    await ctx.send(embed=fail_embed)
                    return
            else:
                net_profit = current_prize - original_bet
                user_money[uid] = user_money.get(uid, 1000) + net_profit
                stop_embed = discord.Embed(title="💰 묻더 스톱! 정산 완료", color=discord.Color.green())
                stop_embed.description = f"현명한 선택! Stage {stage-1}에서 멈췄습니다.\n최종 획득 자산: **+{current_prize}원**\n현재 잔액: {user_money[uid]}원"
                await ctx.send(stop_embed)
                return

        except asyncio.TimeoutError:
            await double_msg.delete()
            net_profit = current_prize - original_bet
            user_money[uid] = user_money.get(uid, 1000) + net_profit
            timeout_embed = discord.Embed(title="⏱️ 시간 초과 자동 정산", color=discord.Color.green())
            timeout_embed.description = f"시간이 초과되어 현재 금액으로 안전 정산되었습니다.\n최종 획득 자산: **+{current_prize}원**\n현재 잔액: {user_money[uid]}원"
            await ctx.send(timeout_embed)
            return

# --- 🎯 [공통 시스템] 다중 참가자 멀티 배팅방 수집 로직 ---
async def setup_multi_bet_game(ctx, bet_amount, game_title):
    creator = ctx.author
    if bet_amount < 1000:
        await ctx.send("⚠️ 최소 배팅 금액은 1000원입니다.")
        return None
    if user_money.get(creator.id, 1000) < bet_amount:
        await ctx.send(f"❌ 잔액이 부족하여 배팅방을 개설할 수 없습니다. (현재: {user_money.get(creator.id, 1000)}원)")
        return None

    participants = [creator]
    user_names[creator.id] = creator.name

    join_embed = discord.Embed(title=f"🎲 {game_title} 배팅방 개설!", color=discord.Color.purple())
    join_embed.description = (
        f"방장: **{creator.name}**\n"
        f"인당 참가비(배팅금): **{bet_amount}원**\n\n"
        f"🙋‍♂️ 함께 돈을 걸고 참여하실 분은 **30초 내에 아래 ✋ 이모지(리액션)**를 눌러주세요!\n"
        f"현재 참가 확정자: {creator.mention}"
    )
    join_msg = await ctx.send(embed=join_embed)
    await join_msg.add_reaction("✋")

    await asyncio.sleep(30.0)

    # 리프레시된 메시지로부터 리액션 참가자 확인
    try:
        refreshed_msg = await ctx.channel.fetch_message(join_msg.id)
        reaction = discord.utils.get(refreshed_msg.reactions, emoji="✋")
        if reaction:
            users = [u async for u in reaction.users()]
            for u in users:
                if u.bot or u.id == creator.id:
                    continue
                if user_money.get(u.id, 1000) >= bet_amount:
                    participants.append(u)
                    user_names[u.id] = u.name
                else:
                    await ctx.send(f"⚠️ {u.mention}님은 잔액이 부족하여 배팅에서 제외됩니다.")
    except Exception as e:
        print(f"참가자 수집 오류: {e}")

    await join_msg.delete()
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
        f"🏎️ **꼬마 예빈이 달리자 배팅!** [배팅금: {bet}원]\n"
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
        res_embed.add_field(name="🎉 축하합니다!", value=f"선택하신 **{user_pick}**가 1등을 했습니다!\n총 상금 **{win_money}원** 확보! 묻더 기능이 활성화됩니다.")
        await ctx.send(embed=res_embed)
        await start_double_or_nothing(ctx, win_money, bet, "자동차 경주")
    else:
        user_money[uid] = user_money.get(uid, 1000) - bet
        res_embed.add_field(name="❌ 아쉽습니다", value=f"승리한 예빈이는 **{winner}**였습니다. (선택: {user_pick})\n**-{bet}원** 차감 (현재 잔액: {user_money[uid]}원)")
        await ctx.send(embed=res_embed)

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
        await ctx.send(f"🏆 **{winner.name}**님 칼타자 인정! **+{prize}원** 상금이 지급되었습니다! (총 자산: {user_money[winner.id]}원)")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ 30초 동안 아무도 정확하게 입력하지 않아 게임이 종료되었습니다.")

# --- 🎰 미니게임 3: 슬롯머신 게임 (3개 일치 시 100배 변경) ---
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

    # 세 개가 모두 똑같은거 나왔을 때 원금의 100배 적용
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
        embed.add_field(name="정산 결과", value=f"{msg_text}\n획득 예정 상금: **{win_money}원**\n\n잠시 후 **묻더** 선택 창이 활성화됩니다!")
        await msg.edit(embed=embed)
        await start_double_or_nothing(ctx, win_money, bet, "슬롯머신")
    else:
        embed.add_field(name="정산 결과", value=f"{msg_text}\n변동 금액: -{bet}원\n현재 자산: {user_money[uid]}원")
        await msg.edit(embed=embed)

# --- 🪜 미니게임 4: 다중 참가자 사다리 타기 배팅 게임 ---
@bot.command()
async def 사다리(ctx, bet: int = None, *, args: str = None):
    if bet is None or not args:
        return await ctx.send("⚠️ 사용법: `!사다리 [판돈] [항목1 항목2 항목3 ...]` (띄어쓰기로 구분)")
    
    choices = args.split()
    if len(choices) < 2:
        return await ctx.send("⚠️ 선택 항목은 최소 2개 이상 입력해 주세요!")

    # 참가자 모집 시작
    participants = await setup_multi_bet_game(ctx, bet, "사다리 타기")
    if not participants or len(participants) < 1:
        return

    # 전원 참가비 차감 및 총 상금 계산
    total_pool = bet * len(participants)
    for p in participants:
        user_money[p.id] = user_money.get(p.id, 1000) - bet

    # 결과 산출 및 참가자 매칭
    chosen_item = random.choice(choices)
    winner = random.choice(participants)
    
    # 전원 자산 정산 (승리자에게 올인)
    user_money[winner.id] = user_money.get(winner.id, 1000) + total_pool

    # 참가자 목록 태그화
    p_mentions = ", ".join([p.mention for p in participants])

    embed = discord.Embed(title="🪜 사다리 타기 결과 발표", color=discord.Color.blue())
    embed.add_field(name="총 베팅 규모", value=f"💵 인당 {bet}원 (총 {len(participants)}명 참여) ➡️ 총 상금 **{total_pool}원**", inline=False)
    embed.add_field(name="👥 모든 참여자", value=p_mentions, inline=False)
    embed.add_field(name="🎯 낙점된 항목", value=f"✨ **{chosen_item}**", inline=True)
    embed.add_field(name="🏆 최종 승리자", value=f"🎉 {winner.mention} 님 독식!!", inline=True)
    embed.add_field(name="🏦 승리자 잔액", value=f"{user_money[winner.id]}원", inline=False)
    
    await ctx.send(content=f"🔔 {winner.mention} 축하합니다! 판돈을 모두 획득하셨습니다!", embed=embed)

# --- 🎰 미니게임 5: 다중 참가자 멀티 룰렛 배팅 게임 (오류 수정 완) ---
@bot.command()
async def 룰렛(ctx, bet: int = None, *, args: str = None):
    if bet is None or not args:
        return await ctx.send("⚠️ 사용법: `!룰렛 [판돈] [항목1 항목2 항목3 ...]` (띄어쓰기로 구분)")
    
    choices = args.split()
    if len(choices) < 2:
        return await ctx.send("⚠️ 선택 항목은 최소 2개 이상 입력해 주세요!")

    # 참가자 모집 시작
    participants = await setup_multi_bet_game(ctx, bet, "룰렛 돌리기")
    if not participants or len(participants) < 1:
        return

    # 전원 참가비 차감 및 총 상금 계산
    total_pool = bet * len(participants)
    for p in participants:
        user_money[p.id] = user_money.get(p.id, 1000) - bet

    embed = discord.Embed(title="🎰 멀티 룰렛 돌리는 중...", description="🔮 과연 누구의 항목이 당첨되어 독식할 것인가?! \n\n[ 🪙 🟥 🟨 🟩 🟦 🟪 ]", color=discord.Color.purple())
    msg = await ctx.send(embed=embed)
    
    spin_emojis = ["[ 🟥 🟨 🟩 🟦 🟪 ]", "[ 🟪 🟥 🟨 🟩 🟦 ]", "[ 🟦 🟪 🟥 🟨 🟩 ]"]
    
    # 룰렛 애니메이션 도중 멈추던 부분 수정 (embed 객체를 올바르게 전달하도록 교정)
    for i in range(4):
        await asyncio.sleep(0.6)
        embed.description = f"🔮 과연 결과는?! \n\n{spin_emojis[i % len(spin_emojis)]}"
        await msg.edit(embed=embed)

    await asyncio.sleep(0.6)
    chosen_item = random.choice(choices)
    winner = random.choice(participants)
    
    # 자산 정산
    user_money[winner.id] = user_money.get(winner.id, 1000) + total_pool
    p_mentions = ", ".join([p.mention for p in participants])

    result_embed = discord.Embed(title="🎯 룰렛 배팅 결과 발표", color=discord.Color.green())
    result_embed.add_field(name="총 베팅 규모", value=f"💵 인당 {bet}원 (총 {len(participants)}명 참여) ➡️ 총 상금 **{total_pool}원**", inline=False)
    result_embed.add_field(name="👥 모든 참여자", value=p_mentions, inline=False)
    result_embed.add_field(name="🎯 당첨된 룰렛 항목", value=f"✨ **{chosen_item}** ✨", inline=True)
    result_embed.add_field(name="🏆 최종 상금 수령자", value=f"🎉 {winner.mention} 님 전액 획득!", inline=True)
    result_embed.add_field(name="🏦 승리자 잔액", value=f"{user_money[winner.id]}원", inline=False)
    
    # 결과가 나온 후 이전 대기용 임베드 메시지를 결과창으로 깔끔하게 교체합니다.
    await msg.edit(content=f"🔔 {winner.mention} 축하합니다! 대박 룰렛의 주인공이 되셨습니다!", embed=result_embed)

# --- 📅 추가 기능: 출석 체크 시스템 ---
@bot.command()
async def 출석(ctx):
    uid = ctx.author.id
    user_names[uid] = ctx.author.name
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    
    if uid not in attendance_data:
        attendance_data[uid] = {"streak": 0, "total": 0, "last_date": ""}
        
    user_att = attendance_data[uid]
    if user_att["last_date"] == today_str:
        return await ctx.send(f"⚠️ {ctx.author.name}님, 오늘은 이미 출석체크를 완료하셨습니다!")
        
    yesterday_str = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    if user_att["last_date"] == yesterday_str: user_att["streak"] += 1
    else: user_att["streak"] = 1
        
    user_att["total"] += 1
    user_att["last_date"] = today_str
    
    base_reward = 10000
    bonus = min(user_att["streak"] * 2000, 20000)
    total_reward = base_reward + bonus
    user_money[uid] = user_money.get(uid, 1000) + total_reward
    
    embed = discord.Embed(title="📅 오늘의 출석 체크 완료! 📅", color=discord.Color.green())
    embed.description = f"**{ctx.author.name}**님이 출석 도장을 찍었습니다!\n🔥 연속 {user_att['streak']}일 | 보상: +{total_reward}원"
    await ctx.send(embed=embed)

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
    await ctx.send(f"🎁 깜짝 보상 도착! **{ctx.author.name}**님에게 **+{reward}원**이 지급되었습니다.")

# --- 🚨 신규 기능: 올인 구제 재난지원금 기능 ---
@bot.command()
async def 재난지원금(ctx):
    uid = ctx.author.id
    if user_money.get(uid, 1000) > 0: return await ctx.send("❌ 돈이 남아있어 신청할 수 없습니다.")
    now = datetime.datetime.now()
    if uid in disaster_cooldowns:
        if now - disaster_cooldowns[uid] < datetime.timedelta(hours=12):
            return await ctx.send("⚠️ 12시간 구제 제한에 걸려있습니다.")
            
    reward = random.randint(10000, 100000)
    user_money[uid] = reward
    disaster_cooldowns[uid] = now
    await ctx.send(f"🚨 파산 복구 완료! **{ctx.author.name}**님에게 긴급 지원금 **+{reward}원**이 지급되었습니다.")

# --- 🏆 추가 기능 5: 통합 랭킹 시스템 ---
@bot.command()
async def 랭킹(ctx):
    sorted_money = sorted(user_money.items(), key=lambda x: x[1], reverse=True)[:5]
    embed = discord.Embed(title="🏆 우리 서버 자산가 랭킹", color=discord.Color.gold())
    money_text = ""
    for idx, (uid, money) in enumerate(sorted_money, 1):
        name = user_names.get(uid, f"유저({uid})")
        money_text += f"**{idx}위**. {name} : {money}원\n"
    embed.description = money_text if money_text else "기록이 없습니다."
    await ctx.send(embed=embed)

# --- 📊 데이터 조회 시스템 (!데이터) ---
@bot.command()
async def 데이터(ctx):
    uid = ctx.author.id
    money = user_money.get(uid, 1000)
    await ctx.send(f"📋 **{ctx.author.name}**님의 현재 자고 있는 자산은 **{money}원**입니다.")

# --- 유튜브 실시간 감지 태스크 ---
@tasks.loop(minutes=5)
async def check_youtube_live():
    global IS_LIVE_NOW
    if not YOUTUBE_CHANNEL_URL or "http" not in YOUTUBE_CHANNEL_URL or not NOTICE_CHANNEL_ID: return
    def fetch_html():
        try:
            req = urllib.request.Request(YOUTUBE_CHANNEL_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response: return response.read().decode('utf-8')
        except: return ""
    loop = asyncio.get_event_loop()
    html = await loop.run_in_executor(None, fetch_html)
    if html:
        is_live = '\"isLive\":true' in html or 'liveStreamability' in html
        if is_live and not IS_LIVE_NOW:
            IS_LIVE_NOW = True
            try:
                channel = bot.get_channel(int(NOTICE_CHANNEL_ID))
                if channel: await channel.send(embed=discord.Embed(title="🔴 유튜브 실시간 방송 시작!", url=YOUTUBE_CHANNEL_URL, color=discord.Color.red()))
            except: pass
        elif not is_live: IS_LIVE_NOW = False

@bot.event
async def on_ready():
    print(f"✅ 디스코드 로그인 성공: {bot.user.name}")
    if not check_youtube_live.is_running(): check_youtube_live.start()

@bot.command()
async def 블랙잭(ctx, bet: int = 1000): await play_blackjack(ctx, bet)

@bot.command()
async def 잔액(ctx): await ctx.send(f"💰 {ctx.author.name}님의 총 자산은 {user_money.get(ctx.author.id, 1000)}원입니다.")

@bot.command()
@commands.has_permissions(administrator=True)
async def 입금(ctx, m: discord.Member, a: int):
    user_money[m.id] = user_money.get(m.id, 1000) + a
    await ctx.send(f"💵 지급 완료. {m.mention} 총 자산: {user_money[m.id]}원")

@bot.command()
@commands.has_permissions(administrator=True)
async def 회수(ctx, m: discord.Member, a: int):
    user_money[m.id] = user_money.get(m.id, 1000) - a
    await ctx.send(f"🛑 회수 완료. {m.mention} 총 자산: {user_money[m.id]}원")

@bot.command()
@commands.has_permissions(administrator=True)
async def 청소(ctx, n: int): await ctx.channel.purge(limit=n + 1)

async def main():
    token = os.environ.get('BOT_TOKEN')
    if not token or len(token.strip()) < 10:
        while True: await asyncio.sleep(3600)
    try:
        async with bot: await bot.start(token)
    except:
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    from threading import Thread
    port = int(os.environ.get("PORT", 10000))
    server_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False))
    server_thread.daemon = True
    server_thread.start()
    asyncio.run(main())