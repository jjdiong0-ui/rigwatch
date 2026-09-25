import sys, os, json, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import framedec

# 1) 卡牌点数模型
assert framedec.card_points(0) == 1      # A
assert framedec.card_points(8) == 9
assert framedec.card_points(9) == 0       # 10 -> 0
assert framedec.card_points(10) == 0      # J -> 0
assert framedec.card_points(12) == 0      # K
assert framedec.card_points(48) == 0      # rank-10 card across suits -> 0

# 2) 三张手牌点数 (mod 10)
assert framedec.hand_value([4, 30, 51], (0, 1, 2)) == (5 + 5 + 0) % 10 == 0

# 3) 帧解码: 明文 JSON / base64+0xd9 包头
assert framedec.decode_frame('{"a":1}') == {"a": 1}
import base64
raw = b'\xd9' + b'{"router":"heartbeat"}'
assert framedec.decode_frame(base64.b64encode(raw).decode()) == {"router": "heartbeat"}

# 4) 游戏事件解析 (winner 语义)
ev = framedec.parse_game_event({"message": {"eventType": "GP_WINNER", "tableID": 1001,
    "gameShoe": 5, "gameRound": 3, "tableCards": [1,2,255,4,255,255], "winner": 2}})
assert ev and ev['winner'] == 2 and ev['shoe'] == 5

# 5) postMessage 广播解析
m = framedec.parse_postmessage({"type": "betInfo", "data": {"tableID": 9, "gameShoe": 33,
    "gameRound": 3, "betCount": 4, "currentBet": 2500}})
assert m and m['type'] == 'bet' and m['currentBet'] == 2500

print("all unit checks passed")