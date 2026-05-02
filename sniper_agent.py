import os, requests, json, time
import pandas as pd
import yfinance as yf
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_stocks(sector_key):
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        response = session.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return [f"{s['symbol']}.NS" for s in response.json()['data'] if s['symbol'] != official_name]
        return []
    except: return []

def run_sniper():
    print("\n🎯 --- HTF STEP 1: POLE DETECTION ONLY ---")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂 Sector [{sector}]: Analyzing {len(tickers)} tickers...")
        
        for t in tickers:
            try:
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if df.empty or len(df) < 40: continue
                
                close = df['Close']
                cmp = float(close.iloc[-1])

                # --- THE POLE CALCULATION ---
                # Check performance over the last 30 trading days (~6 weeks)
                price_30_days_ago = float(close.iloc[-30])
                pole_pct = ((cmp - price_30_days_ago) / price_30_days_ago) * 100
                
                # --- EMA TREND BASELINE ---
                ema10 = close.ewm(span=10).mean().iloc[-1]
                ema21 = close.ewm(span=21).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]

                # FILTER: Only Pole strength + EMA Trend (No consolidation/VDU yet)
                if pole_pct >= 20.0 and ema10 > ema21 > ema50 and cmp > ema50:
                    all_data.append({
                        "Ticker": t, 
                        "Sector": sector,
                        "CMP": round(cmp, 2),
                        "Pole_%": round(pole_pct, 2)
                    })
            except: continue
            time.sleep(0.05)

    if all_data:
        # Sort by strongest Pole first
        all_data = sorted(all_data, key=lambda x: x['Pole_%'], reverse=True)
        filename = "pole_results.csv"
        pd.DataFrame(all_data).to_csv(filename, index=False)
        
        # Send to Telegram
        url_doc = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(filename, "rb") as file:
            requests.post(url_doc, data={"chat_id": CHAT_ID}, files={"document": file})
            
        msg = "🚩 **HTF STEP 1: STRONG POLES FOUND**\n`TICKER   CMP      POLE%` \n"
        for c in all_data[:12]:
            msg += f"`{c['Ticker'].ljust(8)} {str(c['CMP']).ljust(8)} {str(c['Pole_%']).ljust(6)}` \n"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    else:
        print("ℹ️ No stocks found with a 20%+ pole in 30 days.")

if __name__ == "__main__":
    run_sniper()
