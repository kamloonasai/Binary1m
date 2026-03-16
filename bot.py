import time
import requests
import schedule
from datetime import datetime

# ── ตั้งค่า ──────────────────────────────────
TELEGRAM_TOKEN   = "8664989808:AAF2N16H0MqNfYjpSGMQiwv1NSQtSISgnXI"
TELEGRAM_CHAT_ID = "8028512511"
SYMBOLS = {
    "forex": [
        "EURUSD=X","GBPUSD=X","USDJPY=X",
        "AUDUSD=X","USDCHF=X","USDCAD=X",
        "NZDUSD=X","EURGBP=X","EURJPY=X",
        "GBPJPY=X","AUDJPY=X","CHFJPY=X",
        "CADJPY=X","NZDJPY=X","EURAUD=X",
        "EURCAD=X","EURCHF=X","EURNZD=X",
        "GBPAUD=X","GBPCAD=X","GBPCHF=X",
        "GBPNZD=X","AUDCAD=X","AUDCHF=X",
        "AUDNZD=X","CADCHF=X","NZDCAD=X",
        "NZDCHF=X",
        "XAUUSD=X","XAGUSD=X","BZ=F",
        "CL=F","NG=F","HG=F",
    ],
    "crypto": [
        "BTC-USD","ETH-USD","SOL-USD",
        "BNB-USD","XRP-USD","ADA-USD",
        "DOGE-USD","AVAX-USD","LTC-USD",
        "TRX-USD","ETC-USD",
    ],
    "stock": [
        "AAPL","TSLA","AMZN","GOOGL","MSFT",
        "META","NFLX","NVDA","BABA","UBER",
        "INTC","AMD","BA","GS","MS",
        "V","MA","JNJ","PFE","KO",
    ],
}

PIVOT_LEN    = 8
MIN_WAVE_PCT = 0.5
COUNT        = 200

last_fingerprint = {}

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def fetch_ohlc(sym):
    try:
        ticker = yf.Ticker(sym)
        df = ticker.history(period="1d", interval="1m")
        if df is None or len(df) < 30:
            return None
        bars = []
        for _, row in df.iterrows():
            bars.append({
                "h": row["High"],
                "l": row["Low"],
                "c": row["Close"]
            })
        return bars
    except Exception as e:
        print(f"fetch error {sym}: {e}")
        return None

def find_pivots(data, n):
    hi, lo = [], []
    for i in range(n, len(data) - n):
        win = data[i-n:i+n+1]
        maxH = max(b["h"] or 0 for b in win)
        minL = min(b["l"] if b["l"] is not None else 999999 for b in win)
        if data[i]["h"] is not None and data[i]["h"] >= maxH:
            hi.append({"i": i, "p": data[i]["h"]})
        if data[i]["l"] is not None and data[i]["l"] <= minL:
            lo.append({"i": i, "p": data[i]["l"]})
    return hi, lo

def build_swing_seq(hi, lo, max_pts):
    all_pts = [{"i": p["i"], "p": p["p"], "isHigh": True}  for p in hi] + \
              [{"i": p["i"], "p": p["p"], "isHigh": False} for p in lo]
    all_pts.sort(key=lambda x: x["i"], reverse=True)
    seq = []
    for pt in all_pts:
        if not seq or seq[-1]["isHigh"] != pt["isHigh"]:
            seq.append(pt)
        elif (pt["isHigh"] and pt["p"] > seq[-1]["p"]) or \
             (not pt["isHigh"] and pt["p"] < seq[-1]["p"]):
            seq[-1] = pt
        if len(seq) >= max_pts:
            break
    seq.reverse()
    return seq

def detect_impulse(sym, data):
    hi, lo = find_pivots(data, PIVOT_LEN)
    if len(hi) < 3 or len(lo) < 3:
        return []
    price    = data[-1]["c"]
    min_size = price * MIN_WAVE_PCT / 100
    seq      = build_swing_seq(hi, lo, 22)
    signals  = []

    for s in range(len(seq) - 5):
        p    = [seq[s+k]["p"] for k in range(6)]
        isH0 = seq[s]["isHigh"]
        fp   = "|".join(f"{seq[s+k]['i']}:{seq[s+k]['p']:.5f}" for k in range(6))

        if not isH0:
            w1, w3, w5 = p[1]-p[0], p[3]-p[2], p[5]-p[4]
            if w1>0 and w3>0 and w5>0 and p[2]>p[0] and p[4]>p[1] and w1>=min_size and not(w3<w1 and w3<w5):
                signals.append({"type":"bull","sym":sym,"price":price,
                    "detail":f"W1={w1:.4f} W3={w3:.4f} W5={w5:.4f}","fp":fp})
                break
        else:
            w1, w3, w5 = p[0]-p[1], p[2]-p[3], p[4]-p[5]
            if w1>0 and w3>0 and w5>0 and p[2]<p[0] and p[4]<p[1] and w1>=min_size and not(w3<w1 and w3<w5):
                signals.append({"type":"bear","sym":sym,"price":price,
                    "detail":f"W1={w1:.4f} W3={w3:.4f} W5={w5:.4f}","fp":fp})
                break
    return signals

def format_msg(sig):
    now   = datetime.now().strftime("%Y-%m-%d %H:%M")
    price = f"{sig['price']:.6g}"
    arrow = "📈 แนวโน้ม: <b>ขาขึ้น ▲</b>\n🎯 แนะนำ: <b>BUY</b>" if sig["type"] == "bull" \
       else "📉 แนวโน้ม: <b>ขาลง ▼</b>\n🎯 แนะนำ: <b>SELL</b>"
    return (f"🌊 <b>Impulse Wave! [1M]</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 <b>{sig['sym']}</b>\n"
            f"{arrow}\n"
            f"📊 ราคาปัจจุบัน: {price}\n"
            f"📐 {sig['detail']}\n"
            f"🕐 {now}")

def run_bot():
    now = datetime.now().strftime("%H:%M")
    print(f"=== เริ่มสแกน 1M {now} ===")

    for category, syms in SYMBOLS.items():
        for sym in syms:
            data = fetch_ohlc(sym)
            if not data:
                print(f"{sym}: ข้อมูลไม่พอ")
                continue
            sigs = detect_impulse(sym, data)
            for sig in sigs:
                key = f"{sym}:{sig['type']}"
                if last_fingerprint.get(key) != sig["fp"]:
                    last_fingerprint[key] = sig["fp"]
                    send_telegram(format_msg(sig))
                    print(f"ส่งสัญญาณใหม่: {key}")
                else:
                    print(f"ลูกศรเดิม ข้าม: {key}")
            time.sleep(0.3)

    print("=== สแกนเสร็จสิ้น ===")

print("Bot started")
run_bot()
schedule.every(1).minutes.do(run_bot)
while True:
    schedule.run_pending()
    time.sleep(10)
    
