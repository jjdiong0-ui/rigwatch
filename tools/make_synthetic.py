#!/usr/bin/env python3
"""make_synthetic.py — 生成合成投注记录(两种模式: fair / rigged), 供管线复现与检验力演示
  fair:   胜率 ~0.507, 独立
  rigged: 首日 0.49 → 之后 0.30, 输后加注倍投, 输赢成串(正自相关)
"""
import json, random, argparse, datetime

def gen(mode, n_days=24, rounds_per_day=(30, 400), out='data/synthetic_bets.json'):
    rng = random.Random(42)
    bets = []
    t0 = datetime.datetime(2026, 9, 1, 10, 0, 0).timestamp()*1000
    bal = 5000.0
    idx = 0
    for day in range(n_days):
        n = rng.randint(*rounds_per_day)
        # 马尔可夫: 输赢成串
        prev_win = True
        streak_p_win = 0.30 if (mode == 'rigged' and day >= 1) else 0.507
        bet = 200.0
        for i in range(n):
            ts = t0 + day*86400000 + i*45000
            if mode == 'rigged' and day >= 1:
                # 成串: 上一局结果影响本局
                p = streak_p_win if prev_win else min(0.35, streak_p_win+0.08)
                win = rng.random() < p
            else:
                win = rng.random() < 0.507
            if mode == 'rigged' and day >= 1 and bet >= 2000:
                win = rng.random() < 0.28   # 大注压制
            amt = bet
            payoff = amt*(0.95 if win and rng.random() < 0.5 else 1.0) if win else -amt
            if not win: payoff = -amt
            bets.append({
                "Id": 14000000000+idx, "GameCategory": "SE CASINO",
                "GameName": "Baccarat classic",
                "WagersTime": f"/Date({int(ts)})/",
                "BetAmount": round(amt, 2), "Commissionable": round(amt*(0.95 if win and payoff > 0 and rng.random() < 0.6 else 1.0), 2),
                "Payoff": round(payoff, 2)})
            idx += 1
            prev_win = win
            # 追损: 输后加倍概率
            bet = bet*2 if (mode == 'rigged' and not win and rng.random() < 0.4) else max(50, rng.choice([100, 200, 500, 1000]))
            if bet > 20000: bet = 200
    json.dump(bets, open(out, 'w'))
    print(f"{mode}: {len(bets)} rows -> {out}")

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='rigged', choices=['fair', 'rigged'])
    ap.add_argument('--out', default='data/synthetic_bets.json')
    a = ap.parse_args()
    gen(a.mode, out=a.out)