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
    print("\n🎯 --- SNIPER MISSION: HIGH TIGHT FLAG (HTF) ---")
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
                if df.empty or len(df) < 60: continue
                
                close = df['Close']
                high = df['High']
                low = df['Low']
                volume = df['Volume']
                cmp = float(close.iloc[-1])

                # --- 1. THE POLE CHECK (Strong Momentum) ---
                # Price must be up at least 20% in the last 30 trading days
                price_30_days_ago = float(close.iloc[-30])
                momentum_pct = ((cmp - price_30_days_ago) / price_30_days_ago) * 100
                
                # --- 2. HIGH & TIGHT CHECK (Proximity to Peak) ---
                recent_peak = high.tail(30).max()
                dist_from_peak = ((recent_peak - cmp) / recent_peak) * 100
                
                # --- 3. THE VCP (6-Day Consolidation & Volume Dry-up) ---
                last_6_high = high.tail(6).max()
                last_6_low = low.tail(6).min()
                consol_range = ((last_6_high - last_6_low) / last_6_low) * 100
                
                avg_vol_20 = volume.rolling(20).mean().iloc[-1]
                curr_vol_3 = volume.tail(3).mean()
                vdu_ratio = curr_vol_3 / avg_vol_20

                # --- 4. EMA STACK (10 > 21 > 50) ---
                ema10 = close.ewm(span=10).mean().iloc[-1]
                ema21 = close.ewm(span=21).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]

                # --- THE HARD FILTERS ---
                if (momentum_pct > 15 and           # Must have a 'Pole'
                    dist_from_peak < 8 and          # Must be 'High' (within 8% of peak)
                    consol_range < 4.0 and          # Must be 'Tight' (6-day box < 4%)
                    vdu_ratio < 0.9 and             # Volume must be 'Drying'
                    ema10 > ema21 > ema50 and       # EMA Trend Stack
                    cmp > ema10):                   # Must be riding the 10 EMA (Strength)

                    all_data.append({
                        "Ticker": t, "CMP": round(cmp, 2),
                        "Pole_%": round(momentum_pct, 1),
                        "Range_%": round(consol_range, 1),
                        "VDU": round(vdu_ratio, 2),
                        "Dist_Peak": round(dist_from_peak, 1)
                    })
            except: continue
            time.sleep(0.05)

    if all_data:
        all_data = sorted(all_data, key=lambda x: x['Range_%']) # Tightest first
        filename = "htf_candidates.csv"
        pd.DataFrame(all_data).to_csv(filename, index=False)
        
        # Send to Telegram
        url_doc = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(filename, "rb") as file:
            requests.post(url_doc, data={"chat_id": CHAT_ID}, files={"document": file})
            
        msg = "🚩 **HIGH TIGHT FLAG DETECTED**\n`TICKER   POLE%  RANGE%  VDU` \n"
        for c in all_data[:10]:
            msg += f"`{c['Ticker'].ljust(8)} {str(c['Pole_%']).ljust(6)} {str(c['Range_%']).ljust(6)} {str(c['VDU']).ljust(5)}` \n"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    else:
        print("ℹ️ No High Tight Flags found today.")

if __name__ == "__main__":
    run_sniper()
