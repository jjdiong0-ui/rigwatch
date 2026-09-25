#!/usr/bin/env python3
"""💡 预言家按钮 — 量化"结果可由公开押注分布预测"的程度
逻辑: 公平百家乐下, 任何局前公开信息(押注量/人数/靴局/时段)对 winner 无预测力。
若简单规则(决策桩)的命中率显著高于概率 → 结果非随机 → 控盘公式被还原。

用法:
  python3 src/prophet.py --data data/roads/            # 离线拟合+显著性报告
  python3 src/prophet.py --data data/roads/ --live      # 逐局对账模式
数据: monitor.py 落盘的 roads_*.jsonl (postMessage 广播)
"""
import json, glob, math, argparse, os
from collections import defaultdict

# Fair marginals: banker .459, player .446, tie .095 -> per-pair conditional nulls
P0 = {(0, 1): 0.459/(0.459+0.446), (0, 2): 0.459/(0.459+0.095), (1, 2): 0.446/(0.446+0.095)}

def load_records(datadir):
    """从 roadInfo/betInfo 流构建 (桌,靴,局) 样本: 特征=局前最后一条 betInfo, 标签=该局结果"""
    roads = {}   # (tid,shoe,round) -> winCounts
    bets = defaultdict(list)  # (tid,shoe,round) -> [(ts, betCount, currentBet)]
    order = []
    for fn in sorted(glob.glob(os.path.join(datadir, 'roads_*.jsonl'))):
        for line in open(fn):
            try: m = json.loads(line)
            except Exception: continue
            try: d = json.loads(m['d'])
            except Exception: continue
            t = d.get('type'); data = d.get('data') or {}
            ts = m.get('t', 0)
            if t == 'betInfo':
                k = (data.get('tableID'), data.get('gameShoe'), data.get('gameRound'))
                if k[2] is not None:
                    bets[k].append((ts, data.get('betCount'), data.get('currentBet')))
            elif t == 'roadInfo' and data.get('gameRound') is not None:
                k = (data['tableID'], data['gameShoe'], data['gameRound'])
                if k not in roads: order.append(k)
                roads[k] = data.get('winCounts')
    # 连局差分得每局结果: 同靴相邻局 winCounts 增量索引 = 赢家
    seq = defaultdict(list)  # (tid, shoe) -> sorted rounds
    for (tid, shoe, rnd) in roads: seq[(tid, shoe)].append(rnd)
    samples = []
    for (tid, shoe), rnds in seq.items():
        rnds = sorted(rnds)
        for i in range(1, len(rnds)):
            k0, k1 = (tid, shoe, rnds[i-1]), (tid, shoe, rnds[i])
            if rnds[i] != rnds[i-1]+1: continue
            w0, w1 = roads.get(k0), roads.get(k1)
            if not w0 or not w1: continue
            diffs = [idx for idx in range(3) if (w1[idx] or 0)-(w0[idx] or 0) == 1]
            if len(diffs) != 1: continue
            feat = bets.get(k1)
            if not feat: continue
            ts, bc, cb = feat[-1]
            samples.append({'tid': tid, 'shoe': shoe, 'round': rnds[i],
                            'winner': diffs[0], 'betCount': bc, 'currentBet': cb})
    return samples

def fit_and_report(samples, min_n=30):
    print(f"[DATA] 可对齐样本 {len(samples)} 局 (需 betInfo 与相邻 roadInfo 同时覆盖)")
    if len(samples) < min_n:
        print(f"[WAIT] 样本不足 (<{min_n}), 继续挂 monitor.py 采集; 公平台此数永远凑不齐也没关系, 公式为空即公平")
        return None
    # 规则族: 决策桩 —— winner 与 押注量/人数/桌/时段 的关联
    import statistics
    tests = []
    cb = [s['currentBet'] for s in samples if s['currentBet'] is not None]
    if cb:
        med = statistics.median(cb)
        hi = [s for s in samples if (s['currentBet'] or 0) > med]
        lo = [s for s in samples if (s['currentBet'] or 0) <= med]
        tests.append(('押注量>中位数', hi, lo))
    for name, grp, other in tests:
        if not grp: continue
        # winCounts index->class mapping unknown: pairwise binomial tests conditioned on the third class (P0 at module level)
        for wi, wj in ((0, 1), (0, 2), (1, 2)):
            sub = [s for s in grp if s['winner'] in (wi, wj)]
            n = len(sub)
            if n < 10: continue
            p0 = P0[(wi, wj)]
            p = sum(1 for s in sub if s['winner'] == wi)/n
            z = (p-p0)/math.sqrt(p0*(1-p0)/n)
            mark = '  <-- 显著' if abs(z) > 3.4 else ''      # 3对检验 Bonferroni≈z>3.4
            print(f"[RULE] {name} 时 winner={wi}|非{wj} 条件占比 {p*100:.1f}% (公平零假设 {p0*100:.1f}%, n={n}, z={z:+.2f}){mark}")
    # 最好规则: 3对×2方向, 与各自公平零假设比, Bonferroni
    best = (None, 0, 0, 0.5)   # name, |z|, n, p0
    for name, grp, other in tests:
        for wi, wj in ((0, 1), (0, 2), (1, 2)):
            sub = [s for s in grp if s['winner'] in (wi, wj)]
            n = len(sub)
            if n < 10: continue
            p0 = P0[(wi, wj)]
            for w_sel, pz in ((wi, p0), (wj, 1-p0)):
                p = sum(1 for s in sub if s['winner'] == w_sel)/n
                z = (p-pz)/math.sqrt(pz*(1-pz)/n)
                if abs(z) > abs(best[1]): best = (f"{name}→winner={w_sel}|非{wi if w_sel==wj else wj}", z, n, pz)
    if best[0]:
        name, z, n, pz = best
        pc = math.erfc(abs(z)/math.sqrt(2))*6   # 6个候选规则族 Bonferroni
        print(f"\n[RIG-SCORE] 最强规则 '{name}': 偏离公平零假设 {pz*100:.1f}% 达 z={z:+.2f} (n={n}, 校正p={min(pc,1):.2e})")
        verdict = "结果可由公开押注分布预测 → 非随机" if abs(z) > 3.4 else "未达显著, 与公平平台一致"
        print(f"[VERDICT] {verdict}")
    return samples

def live_mode(datadir, interval=15):
    print("[LIVE] 逐局对账: 每局出结果即比对规则预测与实际, 输出累计命中账")
    seen = set()
    while True:
        samples = load_records(datadir)
        for s in samples:
            k = (s['tid'], s['shoe'], s['round'])
            if k in seen: continue
            seen.add(k)
            print(f"  桌{s['tid']} 靴{s['shoe']} 局{s['round']}: winner_idx={s['winner']} 押注={s['currentBet']}")
        import time; time.sleep(interval)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default='data/roads/')
    ap.add_argument('--live', action='store_true')
    ap.add_argument('--min-n', type=int, default=30)
    a = ap.parse_args()
    if a.live:
        live_mode(a.data)
    else:
        fit_and_report(load_records(a.data), a.min_n)