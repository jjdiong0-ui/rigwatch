#!/usr/bin/env python3
"""forensics.py — 投注记录统计取证: 逐日胜率z检验/游程/lag-1自相关/连败条件/martingale/changepoint
用法: python3 src/forensics.py --bets bets.json [--exclude-ties] [--category SE]
bets.json 字段: Id, GameCategory, GameName, WagersTime("/Date(epoch)/"), BetAmount, Commissionable, Payoff
"""
import json, math, argparse, sys
from collections import defaultdict

def epoch(w):
    try: return int(str(w).strip('/').split('(')[1].split(')')[0].split('+')[0])/1000
    except Exception: return 0

def norm_sf(z):  # upper tail
    return 0.5*math.erfc(z/math.sqrt(2))

def z_test(w, n, p0=0.507):
    if n == 0: return 0.0, 1.0
    p = w/n
    z = (p-p0)/math.sqrt(p0*(1-p0)/n)
    return p, z

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bets', required=True)
    ap.add_argument('--category', default=None, help='只分析该类别(如 SE/DB)')
    ap.add_argument('--exclude-ties', action='store_true', help='剔除 Payoff==0 的行(和局推回)')
    a = ap.parse_args()
    bets = json.load(open(a.bets))
    if a.category: bets = [b for b in bets if a.category in (b.get('GameCategory') or '')]
    for b in bets: b['_t'] = epoch(b.get('WagersTime'))
    bets.sort(key=lambda b: b['_t'])
    if a.exclude_ties: bets = [b for b in bets if b.get('Payoff') != 0]

    import datetime
    print(f"== 样本: {len(bets)} 行, {datetime.datetime.fromtimestamp(bets[0]['_t'])} ~ {datetime.datetime.fromtimestamp(bets[-1]['_t'])} ==")

    # 1) 逐日胜率
    days = defaultdict(lambda: [0, 0])
    for b in bets:
        d = datetime.datetime.fromtimestamp(b['_t']).strftime('%Y-%m-%d')
        days[d][0] += 1 if b.get('Payoff', 0) > 0 else 0
        days[d][1] += 1
    print("\n== 逐日胜率 (公平期望≈50.7%, 单边) ==")
    for d in sorted(days):
        w, n = days[d]
        p, z = z_test(w, n)
        flag = " <-- 显著偏低" if z < -3 else ""
        print(f"  {d}: {p*100:5.1f}%  (n={n:4d}, z={z:+.2f}){flag}")

    # 2) lag-1 自相关 (含和局剔除双口径)
    seq = [1 if b['Payoff'] > 0 else 0 for b in bets]
    def lag1(xs):
        prs = list(zip(xs, xs[1:])); n = len(prs)
        if n < 20: return None, 0
        m = sum(x for x, _ in prs)/n
        num = sum((a-m)*(b2-m) for a, b2 in prs)
        den = math.sqrt(sum((a-m)**2 for a, _ in prs)*sum((b2-m)**2 for _, b2 in prs))
        return (num/den if den else 0), n
    r, n = lag1(seq)
    print(f"\n== lag-1 输赢自相关: r={r:.3f} (n={n}) ==")
    if r is not None and abs(r) > 0:
        se = 1/math.sqrt(n)
        zr = r/se
        print(f"  z={zr:+.1f}  (公平游戏下 |z|>4 即极端异常; r>0=输赢成串下发)")

    # 3) 游程检验
    runs = 1 + sum(1 for i in range(1, len(seq)) if seq[i] != seq[i-1])
    n1, n2 = sum(seq), len(seq)-sum(seq)
    if n1 and n2:
        mu = 2*n1*n2/(n1+n2)+1
        var = 2*n1*n2*(2*n1*n2-n1-n2)/(((n1+n2)**2)*(n1+n2-1))
        zr = (runs-mu)/math.sqrt(var)
        print(f"== 游程检验: 观测{runs} vs 期望{mu:.0f}, z={zr:+.1f} (负=成串) ==")

    # 4) 连败条件胜率
    print("\n== 连败 N 局后的下一局胜率 (公平: 不随连败变化) ==")
    cond = defaultdict(lambda: [0, 0])
    streak = 0
    for i in range(len(bets)):
        b = bets[i]
        if b['Payoff'] == 0: continue
        if i+1 < len(bets):
            nb = bets[i+1]
            if nb['Payoff'] != 0:
                k = min(streak, 4)
                cond[k][0] += 1 if nb['Payoff'] > 0 else 0
                cond[k][1] += 1
        streak = 0 if b['Payoff'] > 0 else streak+1
    for k in sorted(cond):
        w, n = cond[k]
        if n >= 20:
            p, z = z_test(w, n)
            print(f"  {k}连败后: {p*100:5.1f}% (n={n}, z={z:+.2f})")

    # 5) martingale 检测
    pairs = 0; up_after_loss = []; up_after_win = []
    for i in range(1, len(bets)):
        b0, b1 = bets[i-1], bets[i]
        if b0['Payoff'] == 0 or b1.get('BetAmount', 0) <= 0 or b0.get('GameName') != b1.get('GameName'): continue
        ratio = b1['BetAmount']/b0['BetAmount']
        pairs += 1
        (up_after_loss if b0['Payoff'] < 0 else up_after_win).append(ratio)
    if pairs > 50:
        ml = sum(up_after_loss)/len(up_after_loss); mw = sum(up_after_win)/len(up_after_win)
        print(f"\n== 追损检测: 输后加注均值 x{ml:.2f} vs 赢后 x{mw:.2f} (n={pairs}) ==")

    # 6) changepoint (日界最优断点, LLR)
    S = sum(seq); N = len(seq)
    def ll(s, m):
        if m == 0: return 0
        p = (s+0.5)/(m+1)
        return m*(p*math.log(p)+(1-p)*math.log(1-p))
    base = ll(S, N)
    ks = list(days.keys()); c = 0; cn = 0; best = (None, -1e18)
    for d in ks[:-1]:
        c += days[d][0]; cn += days[d][1]
        v = ll(c, cn)+ll(S-c, N-cn)-base
        if v > best[1]: best = (d, v)
    if best[0]:
        print(f"\n== 最优日界断点: {best[0]} (2ΔLL={2*best[1]:.0f}, df=1) ==")

if __name__ == '__main__':
    main()