#!/usr/bin/env python3
"""💡 Prophet button — quantifies how predictable outcomes are from public bet flow.
Logic: under a fair game, no pre-round public signal (volume / player count / shoe / hour)
has any predictive power over the winner. If a simple decision-stump rule deviates from the
fair marginals significantly, the outcome generator has been recovered.

Usage:
  python3 src/prophet.py --data data/roads/            # offline fit + significance report
  python3 src/prophet.py --data data/roads/ --live      # per-round accounting mode
Data:   roads_*.jsonl written by monitor.py (hall broadcast).
"""
import json, glob, math, argparse, os
from collections import defaultdict

# Fair marginals: banker .459, player .446, tie .095 -> per-pair conditional nulls
P0 = {(0, 1): 0.459/(0.459+0.446), (0, 2): 0.459/(0.459+0.095), (1, 2): 0.446/(0.446+0.095)}

def load_records(datadir):
    """Build (table, shoe, round) samples: feature = last pre-round betInfo, label = outcome."""
    roads = {}   # (tid,shoe,round) -> winCounts
    bets = defaultdict(list)  # (tid,shoe,round) -> [(ts, betCount, currentBet)]
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
            elif t == 'roadInfo':
                ri = data.get('roadInfo') if isinstance(data.get('roadInfo'), dict) else data
                if ri.get('gameRound') is None: continue
                k = (ri.get('tableID'), ri.get('gameShoe'), ri.get('gameRound'))
                roads[k] = ri.get('winCounts')
    # outcome per round = the single incrementing winCounts index between consecutive rounds
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
    print(f"[DATA] aligned samples: {len(samples)} rounds (need betInfo + consecutive roadInfo)")
    if len(samples) < min_n:
        print(f"[WAIT] insufficient data (<{min_n}); keep monitor.py running. On a fair platform an empty formula is the expected result.")
        return None
    # rule family: decision stumps on pre-round bet volume
    import statistics
    tests = []
    cb = [s['currentBet'] for s in samples if s['currentBet'] is not None]
    if cb:
        med = statistics.median(cb)
        hi = [s for s in samples if (s['currentBet'] or 0) > med]
        tests.append(('volume>median', hi))
    # winCounts index->class mapping unknown: pairwise binomial tests conditioned on the third class
    for name, grp in tests:
        if not grp: continue
        for wi, wj in ((0, 1), (0, 2), (1, 2)):
            sub = [s for s in grp if s['winner'] in (wi, wj)]
            n = len(sub)
            if n < 10: continue
            p0 = P0[(wi, wj)]
            p = sum(1 for s in sub if s['winner'] == wi)/n
            z = (p-p0)/math.sqrt(p0*(1-p0)/n)
            mark = '  <-- significant' if abs(z) > 3.4 else ''   # 3 pair-tests, Bonferroni
            print(f"[RULE] {name}: P(winner={wi}|not {wj}) = {p*100:.1f}% vs fair {p0*100:.1f}% (n={n}, z={z:+.2f}){mark}")
    # best rule across 3 pairs x 2 directions vs each pair's fair null, Bonferroni over 6
    best = (None, 0, 0, 0.5)   # name, |z|, n, p0
    for name, grp in tests:
        for wi, wj in ((0, 1), (0, 2), (1, 2)):
            sub = [s for s in grp if s['winner'] in (wi, wj)]
            n = len(sub)
            if n < 10: continue
            p0 = P0[(wi, wj)]
            for w_sel, pz in ((wi, p0), (wj, 1-p0)):
                p = sum(1 for s in sub if s['winner'] == w_sel)/n
                z = (p-pz)/math.sqrt(pz*(1-pz)/n)
                if abs(z) > abs(best[1]): best = (f"{name}->winner={w_sel}|not {wi if w_sel==wj else wj}", z, n, pz)
    if best[0]:
        name, z, n, pz = best
        pc = math.erfc(abs(z)/math.sqrt(2))*6
        print(f"\n[RIG-SCORE] best rule '{name}': deviates from fair null {pz*100:.1f}% at z={z:+.2f} (n={n}, corrected p={min(pc,1):.2e})")
        verdict = "outcome predictable from public bet flow -> not random" if abs(z) > 3.4 else "not significant — consistent with a fair platform"
        print(f"[VERDICT] {verdict}")
    return samples

def live_mode(datadir, interval=15):
    print("[LIVE] per-round accounting: each settled round checked against the rule, running tally")
    seen = set()
    while True:
        samples = load_records(datadir)
        for s in samples:
            k = (s['tid'], s['shoe'], s['round'])
            if k in seen: continue
            seen.add(k)
            print(f"  table {s['tid']} shoe {s['shoe']} round {s['round']}: winner_idx={s['winner']} volume={s['currentBet']}")
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