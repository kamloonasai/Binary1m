import time
import requests
import schedule
from datetime import datetime

# ── ตั้งค่า ──────────────────────────────────
TELEGRAM_TOKEN   = "8664989808:AAF2N16H0MqNfYjpSGMQiwv1NSQtSISgnXI"
TELEGRAM_CHAT_ID = "8028512511"
FINNHUB_KEY      = "d6rt02pr01qrri55enhgd6rt02pr01qrri55eni0"

SYMBOLS = {
    # Forex
    "forex": [
        "OANDA:EUR_USD","OANDA:GBP_USD","OANDA:USD_JPY",
        "OANDA:AUD_USD","OANDA:USD_CHF","OANDA:USD_CAD",
        "OANDA:NZD_USD","OANDA:EUR_GBP","OANDA:EUR_JPY",
        "OANDA:GBP_JPY","OANDA:AUD_JPY","OANDA:CHF_JPY",
        "OANDA:CAD_JPY","OANDA:NZD_JPY","OANDA:EUR_AUD",
        "OANDA:EUR_CAD","OANDA:EUR_CHF","OANDA:EUR_NZD",
        "OANDA:GBP_AUD","OANDA:GBP_CAD","OANDA:GBP_CHF",
        "OANDA:GBP_NZD","OANDA:AUD_CAD","OANDA:AUD_CHF",
        "OANDA:AUD_NZD","OANDA:CAD_CHF","OANDA:NZD_CAD",
        "OANDA:NZD_CHF",
        # Commodities
        "OANDA:XAU_USD","OANDA:XAG_USD","OANDA:BCO_USD",
        "OANDA:WTICO_USD","OANDA:NATGAS_USD","OANDA:XCU_USD",
    ],
    # Crypto
    "crypto": [
        "BINANCE:BTCUSDT","BINANCE:ETHUSDT","BINANCE:SOLUSDT",
        "BINANCE:BNBUSDT","BINANCE:XRPUSDT","BINANCE:ADAUSDT",
        "BINANCE:DOGEUSDT","BINANCE:AVAXUSDT","BINANCE:LTCUSDT",
        "BINANCE:TRXUSDT","BINANCE:ETCUSDT",
    ],
    # หุ้น
    "stock": [
        "AAPL","TSLA","AMZN","GOOGL","MSFT",
        "META","NFLX","NVDA","BABA","UBER",
        "INTC","AMD","BA","GS","MS",
        "V","MA","JNJ","PFE","KO",
    ],
}

PIVOT_LEN    = 8
MIN_WAVE_PCT = 0.5
RESOLUTION   = "1"
COUNT        = 200

# ── เก็บ fingerprint ไว้ในหน่วยความจำ ────────
last_fingerprint = {}

# ── Telegram ─────────────────────────────────
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

# ── Finnhub ───────────────────────────────────
def fetch_ohlc(sym, endpoint):
    now  = int(time.time())
    frm  = now - 60 * COUNT
    url  = f"https://finnhub.io/api/v1/{endpoint}/candle"
    params = {
        "symbol": sym,
        "resolution": RESOLUTION,
        "from": frm,
        "to": now,
        "token": FINNHUB_KEY
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        d = r.json()
        if not d or d.get("s") == "no_data" or "c" not in d:
            return None
        bars = []
        for i in range(len(d["c"]) - 1):
            if d["c"][i] is not None:
                bars.append({"h": d["h"][i], "l": d["l"][i], "c": d["c"][i]})
        return bars if len(bars) >= 30 else None
    except Exception as e:
        print(f"fetch error {sym}: {e}")
        return None

# ── Pivot ─────────────────────────────────────
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

# ── Detect Impulse Wave ───────────────────────
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

# ── Format Message ────────────────────────────
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

# ── Main Scan ─────────────────────────────────
def run_bot():
    now = datetime.now().strftime("%H:%M")
    print(f"=== เริ่มสแกน 1M {now} ===")

    all_symbols = []
    for endpoint, syms in SYMBOLS.items():
        for sym in syms:
            all_symbols.append((sym, endpoint))

    for sym, endpoint in all_symbols:
        data = fetch_ohlc(sym, endpoint)
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

# ── Schedule ──────────────────────────────────
print("Bot started")
run_bot()
schedule.every(1).minutes.do(run_bot)
while True:
    schedule.run_pending()
    time.sleep(10)
