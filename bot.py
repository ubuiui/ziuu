# --- 🚀 [공통 시스템] 미니게임용 묻고 더블로 가! 로직 ---
async def start_double_or_nothing(ctx, current_win_prize, original_bet, game_name):
    uid = ctx.author.id
    current_prize = current_win_prize
    stage = 1

    while True:
        # 단계별 확률 계산: 기본 70%에서 단계당 10%씩 감소 (최하 10% 보장)
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
                # 가변 확률 적용
                if random.random() < success_rate:
                    current_prize = int(current_prize * 2.5)
                    stage += 1
                    continue
                else:
                    user_money[uid] = user_money.get(uid, 1000) - original_bet
                    fail_embed = discord.Embed(title="💥 묻더 실패! 올인 파산", color=discord.Color.dark_gray())
                    fail_embed.description = f"앗.. {fail_percentage}%의 실패 확률에 걸려 묻더에 실패했습니다.\n상금은 공중분해되었으며 배팅 원금 **-{original_bet:,}원**이 차감됩니다.\n현재 잔액: {user_money[uid]:,}원"
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