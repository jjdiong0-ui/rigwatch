#!/usr/bin/env python3
"""make_roads_synthetic.py — synthetic hall broadcast (roadInfo+betInfo) with a planted volume->outcome rule
供 src/prophet.py 端到端自检: 公平平台跑分应≈50%, 植入规则后应被 RIG-SCORE 检出。
"""
import json, random, argparse, os, datetime

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='data/roads')
ap.add_argument('--mode', default='rigged', choices=['fair', 'rigged'])
ap.add_argument('--shoes', type=int, default=4)
ap.add_argument('--rounds', type=int, default=60)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
rng = random.Random(42)
t0 = int(datetime.datetime(2026, 9, 25, 20, 0, 0).timestamp()*1000)
out = []
for shoe in range(1, a.shoes+1):
    wc = [0, 0, 0]
    for rnd in range(1, a.rounds+1):
        bet = rng.uniform(50, 3000)
        if a.mode == 'rigged':
            wi = 0 if rng.random() < (0.7 if bet > 1500 else 0.4) else rng.choice([1, 2])
        else:
            # real-world marginals: tie~9.5%, banker~45.9%, player~44.6%
            u = rng.random()
            wi = 2 if u < 0.095 else (0 if u < 0.095+0.459 else 1)
        wc[wi] += 1
        out.append({"t": t0+rnd*3000, "d": json.dumps({"type": "betInfo", "data": {
            "tableID": 1001, "gameShoe": shoe, "gameRound": rnd,
            "betCount": rng.randint(10, 600), "currentBet": round(bet, 2)}})})
        out.append({"t": t0+rnd*3000+500, "d": json.dumps({"type": "roadInfo", "data": {
            "tableID": 1001, "gameShoe": shoe, "gameRound": rnd,
            "winCounts": list(wc), "bigRoads": []}})})
fn = os.path.join(a.out, datetime.datetime.fromtimestamp(t0/1000).strftime('roads_%Y%m%d_%H.jsonl'))
with open(fn, 'w') as f:
    for m in out: f.write(json.dumps(m)+"\n")
print(f"{a.mode}: {len(out)} msgs -> {fn}")