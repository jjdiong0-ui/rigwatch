<div align="center">

# ⚖️ rigwatch

**Instrumented forensics for live-dealer gaming platforms.**

If the outcome can be predicted, it is not a game — it is a scripted transfer.

[![License: MIT](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org)
[![Status: Evidence-Grade](https://img.shields.io/badge/status-evidence--grade-8b5cf6.svg)]()
[![Ethics: Read-Only Recon](https://img.shields.io/badge/ethics-read--only%20recon-0ea5e9.svg)](#scope--ethics)

**Statistics · Protocol reverse-engineering · Live monitoring · Tamper detection · Outcome predictability scoring**

</div>

---

## Why

"Live dealer" platforms sell one promise: *a real human, real cards, streamed to you, so the result cannot be faked.*

That promise is testable. rigwatch is a portable toolkit, built during a real victim-case investigation (operator anonymized as **PLATFORM-X**, a Southeast-Asian white-label live-dealer chain), that turns a hunch into numbers:

| Layer | Question | Method |
|---|---|---|
| **1. Statistics** | Did the player win *less often than mathematics allows*? | Per-day win-rate z-tests, runs test, lag-1 autocorrelation, losing-streak conditioning, martingale detection, changepoint analysis |
| **2. Protocol** | Where does the "result" actually come from? | WebSocket frame decode: cards arrive as array fields, the winner arrives as a server-side field — video is just a rendering layer |
| **3. Oracle** | Can the outcome be predicted from public bet flow? | Decision-stump fit over spectator-collected betInfo→winner streams. On a fair platform this is always ≈ a coin flip. Any significant lift = a recovered decision rule |

## The headline numbers (real case, anonymized)

```
Per-day win rate vs fair expectation (50.7%):   49.0% day-1  →  28–43% from day 13
z = −9.3 … −12.0   p < 1e-20                    (n = 9,527 settled bets)
Win/loss sequence lag-1 autocorrelation:        r = +0.456   runs-test p < 1e-97
Losing-streak conditioning:                     win rate falls monotonically with streak depth
Post-loss bet escalation:                       ×6.84 average (system reads chasing behavior)
```

And the oracle on a planted-rule synthetic stream (end-to-end self-test):

```
[RIG-SCORE] best rule 'bet volume > median → winner≠1': hit 86.4% (n=59, z=+5.60, p=2e-08)
[VERDICT] outcome is predictable from public bet flow → not random
```

## Quickstart

```bash
git clone https://github.com/<you>/rigwatch && cd rigwatch

# 1) Reproduce the statistics pipeline on synthetic data (rigged mode)
python3 tools/make_synthetic.py --mode rigged
python3 src/forensics.py --bets data/synthetic_bets.json

# 2) Prove the oracle detects a planted rule
python3 tools/make_roads_synthetic.py          # writes data/roads/
python3 src/prophet.py   --data data/roads/

# 3) Run it against a real platform you have lawful read access to
#    (Android Chrome + CDP; see docs/protocol.md)
python3 src/monitor.py                          # live panel + hourly-partitioned capture + tamper diff
python3 src/prophet.py --data data/roads/ --live
```

## What each component does

```
src/forensics.py    statistical battery for one player's full bet history (JSON in, verdict out)
src/framedec.py     WS frame decoder: length-prefixed header → JSON, game-event parser, card-point model
src/monitor.py      hall-broadcast collector (roadInfo / betInfo / dealerEvent), ANSI panel,
                    per-(table,shoe,round) history diff — any retro-edit of a settled round lights up red
src/prophet.py      the oracle: aligns pre-round bet flow with settled outcomes, fits simple rules,
                    reports hit-rate with significance; --live streams a running account
docs/protocol.md    full protocol field map, event lifecycle, upstream router table, chain topology
tools/              synthetic generators (fair & rigged) so every test is reproducible offline
```

## Key protocol findings (anonymized)

- Every round's cards and winner are **server-side data fields** (`GP_ONE_CARD_DRAWN` fills a 6-slot array; `GP_WINNER` delivers `winner=1|2`), streamed over one WebSocket — the dealer video is a rendering layer on top of that data, on separate infrastructure.
- The client reports bet flow to the operator every ~3 s (`betInfo` per table), so the operator observes the full table position **before** settling the round. Whether a "look-then-decide" policy exists is exactly what the oracle quantifies.
- In a 5-round sample, 2/5 rounds carried winner-side card timestamps *earlier* than the animation events for the same cards — timestamps are generated values, not measurements. (Lead, not proof; small sample.)
- Full field map, upstream router table, and chain topology: [`docs/protocol.md`](docs/protocol.md)

## Honest limits

- TLS stays encrypted; how cards are *chosen* (deal interference vs pre-sequenced shoe) requires law-enforcement server access to settle.
- The oracle works **only as a spectator**. The operator sees bets before settling, so your own bet changes the outcome — this is a rigging detector, not a winning tool. That asymmetry is the finding.
- Dual-timeline video-hash comparison (2×50 s, 50 fps, 2,550 frame pairs) found **no** pre-recorded loop at 40-minute scale. Video-layer pre-recording is neither proven nor excluded; the architecture decoupling is what's proven.

## Scope & ethics

rigwatch is for **read-only forensics**: your own (or a consenting family member's) account data, spectator-level public broadcasts, and evidence preparation for authorities.

It contains no exploits, no intrusion tooling, no credential handling, and no betting automation. Do not use it to gamble or on platforms you have no lawful basis to inspect. Real case data contains PII and is deliberately absent from this repository; synthetic data reproduces every analytic.

## License

MIT. Analyses and conclusions are the responsibility of each contributor. No warranty.