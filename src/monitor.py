#!/usr/bin/env python3
"""monitor.py — 白标"真人视讯"大厅实时监控: 采集+落盘+篡改检测+ANSI 面板
前置: Android Chrome CDP (adb forward tcp:9222 localabstract:chrome_devtools_remote)
运行: python3 src/monitor.py [--out data/roads] [--hall-url URL]
原理: 游戏大厅 iframe 通过 postMessage 广播全桌 roadInfo/betInfo/dealerEvent;
      同一 (桌,靴,局) 的历史结果前后不一致 → 红色高亮 (篡改/重绘噪音需人工分辨)。
"""
import websocket, json, time, subprocess, os, sys, datetime, signal, argparse

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='data/roads')
ap.add_argument('--hall-url', default=None, help='平台游戏入口 URL (含登录态的浏览器打开)')
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
R=lambda c,s: f"\033[{c}m{s}\033[0m"
RED,GRN,YEL,BLU,GRY,BLD = "31","32","33","34","90","1"

ws=None; mid=[0]
def fresh(): 
    global ws
    ws=websocket.create_connection("ws://127.0.0.1:9222/devtools/browser", timeout=30, suppress_origin=True)
def send(m,p=None,sid=None,retry=3):
    global ws
    for _ in range(retry):
        mid[0]+=1; msg={"id":mid[0],"method":m,"params":p or {}}
        if sid: msg["sessionId"]=sid
        try:
            ws.send(json.dumps(msg))
            while True:
                r=json.loads(ws.recv())
                if r.get("id")==mid[0]:
                    if "error" in r: raise RuntimeError(str(r["error"])[:120])
                    return r.get("result",{})
        except RuntimeError: raise
        except Exception:
            try: ws.close()
            except: pass
            subprocess.run(["adb forward tcp:9222 localabstract:chrome_devtools_remote"], shell=True, capture_output=True)
            time.sleep(2)
            try: fresh()
            except Exception: pass
    raise RuntimeError("cdp down")

TAP = r"""(()=>{ if(window.__mt) return 'ok'; window.__mt=[];
 window.addEventListener('message', function(e){ try{ window.__mt.push({t:Date.now(), d:JSON.stringify(e.data).slice(0,20000)}) }catch(x){} }, false);
 return 'ok' })()"""

taps=[]; last_nav=0
def probe_ctxs(s):
    alive=[]
    for c in range(1,40):
        try:
            rr=send("Runtime.evaluate",{"expression":"location.href.slice(0,80)","contextId":c,"returnByValue":True},sid=s)
            v=rr.get("result",{}).get("value")
            if v and 'about:blank' not in v: alive.append((c,v))
        except Exception: continue
    return alive

def reinit():
    global taps, last_nav
    tg=send("Target.getTargets")["targetInfos"]
    if a.hall_url:
        pages=[t for t in tg if t["type"]=="page" and "LoginToSupplier" in t["url"]]
        if pages:
            psid=send("Target.attachToTarget",{"targetId":pages[0]["targetId"],"flatten":True})["sessionId"]
            send("Page.enable",sid=psid)
            if time.time()-last_nav>60:
                send("Page.navigate",{"url":a.hall_url},sid=psid); last_nav=time.time(); time.sleep(15)
    tg=send("Target.getTargets")["targetInfos"]
    taps=[]
    for t in tg:
        if t["type"]=="iframe" and "jsp" in t["url"]:
            try:
                s=send("Target.attachToTarget",{"targetId":t["targetId"],"flatten":True})["sessionId"]
                send("Runtime.enable",sid=s); time.sleep(1.5)
                for c,u in probe_ctxs(s):
                    try:
                        send("Runtime.evaluate",{"expression":TAP,"contextId":c,"returnByValue":True},sid=s)
                        taps.append((s,c,u))
                    except Exception: pass
            except Exception: pass
    if not taps: raise RuntimeError("no live game contexts (先在手机浏览器打开平台大厅)")
    return taps

seen={}; tamper=[]; msgs_total=0; cur_file=None
def part_file(ts):
    global cur_file
    fn=os.path.join(a.out, datetime.datetime.fromtimestamp(ts/1000).strftime('roads_%Y%m%d_%H.jsonl'))
    cur_file=fn; return fn

def parse_and_store(batch):
    global msgs_total
    for m in batch:
        ts=m.get('t',int(time.time()*1000))
        with open(part_file(ts),'a') as f: f.write(json.dumps(m)+"\n")
        msgs_total+=1
        try: d=json.loads(m['d'])
        except Exception: continue
        data=d.get('data') if isinstance(d,dict) else None
        if not isinstance(data,dict): continue
        ri=data.get('roadInfo') if d.get('type')=='roadInfo' else (data if 'roadInfo' in data else None)
        if isinstance(ri,dict) and 'roadInfo' in data: ri=data['roadInfo']
        if not isinstance(ri,dict) or ri.get('gameRound') is None: continue
        key=(ri.get('tableID'),ri.get('gameShoe'),ri.get('gameRound'))
        rec={'winCounts':ri.get('winCounts'),'roads':str(ri.get('bigRoads',''))[:200]}
        prev=seen.get(key)
        if prev:
            changed = (prev['winCounts']!=rec['winCounts'] and rec['winCounts'] is not None and prev['winCounts'] is not None) or (prev['roads']!=rec['roads'] and rec['roads']!='[]' and prev['roads']!='[]')
            if changed: tamper.append((ts,key,prev['winCounts'],rec['winCounts']))
        if prev is None or (prev['winCounts'] is None and rec['winCounts'] is not None):
            seen[key]=rec

def render():
    now=datetime.datetime.now().strftime('%H:%M:%S')
    lines=[R(BLD,f" 白标视讯监控  {R(GRY,now)}  msgs={msgs_total}  局记录={len(seen)}  篡改={R(RED,str(len(tamper))) if tamper else '0'}")]
    lines.append(R(GRY,"─"*80))
    tables=sorted(set(k[0] for k in seen if k[0] is not None))
    for tid in tables[:20]:
        ks=[k for k in seen if k[0]==tid]
        if not ks: continue
        latest=max(ks,key=lambda k:(k[1] or 0,k[2] or 0))
        wc=seen[latest]['winCounts'] or [0,0,0]
        lines.append(f" 桌{R(BLU,str(tid)):>6}  靴{latest[1]} 局{latest[2]:>4}  计数 {R(RED,str(wc[0]))}/{R(GRN,str(wc[1]))}/{R(YEL,str(wc[2]))}")
    if tamper:
        lines.append(""); lines.append(R(BLD," ⚠ 历史局结果前后不一致 (重绘噪音需人工分辨):"))
        for ts,key,old,new in tamper[-8:]:
            lines.append(R(RED,f"   {datetime.datetime.fromtimestamp(ts/1000).strftime('%H:%M:%S')} 桌{key[0]} 靴{key[1]}局{key[2]}: {old} → {new}"))
    print("\033[2J\033[H"+"\n".join(lines))

def main():
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    try: fresh()
    except Exception:
        subprocess.run(["adb forward tcp:9222 localabstract:chrome_devtools_remote"], shell=True); fresh()
    print("初始化: 挂载游戏大厅 context...")
    while True:
        try:
            if not taps: taps=reinit()
            got=[]
            for s,c,u in taps:
                try:
                    r=send("Runtime.evaluate",{"expression":"JSON.stringify(window.__mt.splice(0,window.__mt.length)).slice(0,2000000)","contextId":c,"returnByValue":True},sid=s)
                    v=r.get("result",{}).get("value")
                    if v and v!='[]': got+=json.loads(v)
                except Exception: pass
            if got: parse_and_store(got)
            render(); time.sleep(5)
        except KeyboardInterrupt: raise
        except Exception as e:
            print(R(YEL,f"[重连] {str(e)[:80]}")); taps=[]
            time.sleep(3)

main()