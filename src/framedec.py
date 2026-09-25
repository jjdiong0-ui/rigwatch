#!/usr/bin/env python3
"""framedec.py — game-event WebSocket frame decoder (white-label live-dealer family)
帧格式: 二进制长度前缀包头(常见 0xd9 1字节 / 0xda 0x01 多字节) + JSON 明文
本文件同时提供 postMessage 大厅广播(roadInfo/betInfo/dealerEvent)的解析。
"""
import base64, json

def decode_frame(payload):
    """CDP payloadData -> dict | None. 文本帧直接 JSON, 二进制帧 base64+包头剥离。"""
    if not payload: return None
    try:
        return json.loads(payload)
    except Exception:
        pass
    try:
        b = base64.b64decode(payload)
    except Exception:
        return None
    i = b.find(b'{')
    if i < 0: return None
    try:
        return json.loads(b[i:])
    except Exception:
        return None

GP_EVENTS = ('GP_NEW_GAME_START','GP_RANDOM_PAY','GP_ONE_CARD_DRAWN','GP_WINNER','GP_CHANGE_STATE')

def parse_game_event(j):
    """下行游戏事件 -> dict{eventType, tableID, shoe, round, cards, winner, playerHand, bankerHand, pair, stamps}"""
    msg = j.get('message') or {}
    et = msg.get('eventType') or j.get('messageType')
    if not et: return None
    return {
        'eventType': et,
        'tableID': msg.get('tableID'),
        'shoe': msg.get('gameShoe'),
        'round': msg.get('gameRound'),
        'cards': msg.get('tableCards'),           # seats 0-2 player, 3-5 banker, 255 undealt
        'stamps': msg.get('tableCardStampTimes'),
        'winner': msg.get('winner'),              # 1=banker 2=player (settlement)
        'playerHand': msg.get('playerHandValue'),
        'bankerHand': msg.get('bankerHandValue'),
        'pair': msg.get('pairState'),
        'deliver': msg.get('deliverTime'),
    }

def card_points(v):
    """牌值 0-51 -> 百家乐点数: (v+1)%13, r=0 记 10, J/Q/K(r>=10) 记 0"""
    r = (v+1) % 13
    if r == 0: r = 13
    return r if r <= 9 else 0

def hand_value(cards, seats=(0,1,2)):
    return sum(card_points(c) for c in (cards[i] for i in seats if i < len(cards) and cards[i] != 255)) % 10

def parse_postmessage(d):
    """大厅广播 postMessage -> {type, tableID, shoe, round, winCounts|bet|event}"""
    if isinstance(d, str):
        try: d = json.loads(d)
        except Exception: return None
    if not isinstance(d, dict): return None
    t = d.get('type'); data = d.get('data')
    if t == 'roadInfo' and isinstance(data, dict):
        return {'type': 'road', 'tableID': data.get('tableID'), 'shoe': data.get('gameShoe'),
                'round': data.get('gameRound'), 'winCounts': data.get('winCounts'),
                'bigRoads': data.get('bigRoads')}
    if t == 'betInfo' and isinstance(data, dict):
        return {'type': 'bet', 'tableID': data.get('tableID'), 'shoe': data.get('gameShoe'),
                'round': data.get('gameRound'), 'betCount': data.get('betCount'),
                'currentBet': data.get('currentBet')}
    if t == 'dealerEvent' and isinstance(data, dict):
        return {'type': 'event', 'tableID': data.get('tableID'), 'shoe': data.get('gameShoe'),
                'round': data.get('gameRound'), 'eventType': data.get('eventType')}
    if t == 'tableInfo' and isinstance(data, dict):
        return {'type': 'table', 'tableID': data.get('tableID'), 'name': data.get('tableName'),
                'shoe': data.get('gameShoe'), 'round': data.get('gameRound'), 'dealer': data.get('dealerID')}
    return None

if __name__ == '__main__':
    import sys
    for line in sys.stdin:
        j = decode_frame(line.strip())
        ev = parse_game_event(j) if j else None
        if ev: print(json.dumps(ev, ensure_ascii=False))