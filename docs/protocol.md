# Protocol notes — white-label "live dealer" platform (PLATFORM-X, anonymized)

All identifiers below are **deliberately genericized** (`vendor-*` hostnames, placeholder IPs).
Field names and wire formats are real and reproduced verbatim.

## Transport

- Game events ride one WebSocket, created at page load. Under Android site isolation the game
  iframe is a **separate CDP target** — page-level capture misses it entirely. Find it via
  `Target.getTargets` → `type=iframe` with a game-JSP URL, then `Runtime.enable` + per-context probes.
- Downstream frame: `[binary length-prefix header][plain JSON]`. Observed headers `0xd9` (1 byte),
  `0xda 0x01`, `0xb6`. CDP `Network.webSocketFrameReceived.response.payloadData` is base64 —
  strip the header at the first `{` and the JSON falls out.
- Upstream: Android Chrome's CDP returns **empty payload** for `webSocketFrameSent`
  (434 empty frames observed). To capture client→server traffic, inject a
  `WebSocket.prototype.send` hook into every live execution context.
- The hall broadcasts `roadInfo / betInfo / dealerEvent / tableInfo` to sibling frames via
  `postMessage` (compact variants — no card/winner payloads; full fields only inside the table WS).

## Round lifecycle (downstream events)

```
GP_NEW_GAME_START          new round, tableCards all 255
  └─ betInfo every ~3s     per-table betCount (players) and currentBet (money) per zone
GP_RANDOM_PAY              random-payout odds table armed
GP_ONE_CARD_DRAWN ×N       tableCards filled card-by-card, each with ms-precision stampTime
GP_WINNER                  winner field settles the round + playerHand/bankerHand + pairState
GP_CHANGE_STATE            state transition
```

## Field semantics (brute-force fit, unique solution, 5/5 rounds consistent)

| Field | Meaning |
|---|---|
| `tableCards[0..2]` | player-side seats (255 = not dealt) |
| `tableCards[3..5]` | banker-side seats |
| card value v (0–51) | standard encoding; points = (v+1)%13, r=0 counts 10, J/Q/K count 0 |
| `winner` | 1 = banker, 2 = player (tie value not yet calibrated) |
| `pairState` | 2 = player pair (validated on a player-AA round) |
| `winCounts[3]` | per-shoe cumulative tallies; index↔road-code mapping closes with more data |

## Upstream router table

| router | cadence | payload |
|---|---|---|
| `userPlainBalance` | 3 s | balance request (timestamp only; server replies downstream) |
| `serverInfo` | 3 s | server poll |
| `heartbeat` | periodic | bare + keyed-auth variants |
| `cdnInfo` / `apiTestInfo` / `flvTestInfo` | periodic | telemetry: player uid, server node, CDN vendor, channel tag |
| `streamingInfo` | on table entry | stream name, server-time sync |
| `gameError` / `txnSupplement` | event | base64-embedded JSON (player id, operator-cafe id) |

## stampTime observation ("outcome-first" lead, 5-round sample)

In 2/5 rounds the `GP_WINNER` event's `tableCardStampTimes` are **130–180 ms earlier** than the
same cards' `GP_ONE_CARD_DRAWN` stamps; 3/5 identical. Timestamps are generated server-side, not
measured — the winner record may be created before the animation events are pushed. Small sample:
treat as a lead, not a finding.

## Video layer

- FLV/H.264 via a commercial cloud-CDN edge, signed URL `?txSecret=…&txTime=<hex epoch>`
- Tokens are single-use and expire in ~36 minutes; once the player consumes a URL, raw curl returns 0 bytes
- Physically separated from the result dataflow (different domains, IPs, connection pools)

## Chain topology (anonymized)

```
Front shell site (CDN-fronted, licensed-looking façade)
  └─ login-broker host (cloud provider A; TLS cert CN shared with a sibling domain
     registered in the same minute — classic white-label sibling infrastructure)
      └─ game-hall host + result-API host (same IP behind a WAF vendor; hall API + result WS)
          └─ video edge (commercial cloud CDN; streaming domain registered to a real-world company)
Engine signature: a known white-label live-dealer vendor family; players hold hosted accounts
(no independent passwords — operator staff can act on funds directly).
```