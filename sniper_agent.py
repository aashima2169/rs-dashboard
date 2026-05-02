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
        headers = {"User-Agent": "Mozilla/5.0"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        response = session.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return [f"{s['symbol']}.NS" for s in response.json()['data'] if s['symbol'] != official_name]
        return []
    except: return []

def run_sniper():
    print("\n🎯 --- SNIPER MISSION: DEBUG MODE (EMA + VOLUME) ---")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    filename = "sniper_candidates.csv"
    
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂 Sector [{sector}]: Screening {len(tickers)} tickers...")
        
        for t in tickers:
            try:
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if df.empty or len(df) < 50: continue
                
                close = df['Close']
                volume = df['Volume']
                cmp = float(close.iloc[-1])
                
                # --- RULE 1: EMA STACK (10 > 21 > 50) ---
                ema10 = close.ewm(span=10).mean().iloc[-1]
                ema21 = close.ewm(span=21).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]
                
                is_ema_stacked = ema10 > ema21 > ema50
                
                # --- RULE 2: PRICE > EMA 50 ---
                is_above_ema50 = cmp > ema50
                
                # --- RULE 3: VOLUME DRY-UP (VDU) ---
                # Average volume of last 20 days vs average of last 3 days
                avg_vol_20 = volume.rolling(20).mean().iloc[-1]
                curr_vol_3 = volume.tail(3).mean()
                vdu_ratio = curr_vol_3 / avg_vol_20
                
                # We use a very loose volume check (0.95) to see what passes
                is_vdu = vdu_ratio < 0.95 

                # --- APPLYING RULES 1 BY 1 ---
                if is_ema_stacked and is_above_ema50 and is_vdu:
                    all_data.append({
                        "Ticker": t,
                        "Sector": sector,
                        "CMP": round(cmp, 2),
                        "EMA10": round(ema10, 2),
                        "EMA21": round(ema21, 2),
                        "EMA50": round(ema50, 2),
                        "VDU_Ratio": round(vdu_ratio, 2)
                    })
            except: continue
            time.sleep(0.05)

    if all_data:
        pd.DataFrame(all_data).to_csv(filename, index=False)
        print(f"✅ Found {len(all_data)} stocks matching current criteria.")
        
        # Send File and Summary to Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(filename, "rb") as file:
            requests.post(url, data={"chat_id": CHAT_ID}, files={"document": file})
            
        msg = f"🎯 **DEBUG REPORT: EMA + VOL**\nFound {len(all_data)} matches.\n"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg})
    else:
        pd.DataFrame(columns=["Ticker"]).to_csv(filename, index=False)
        print("ℹ️ Zero matches with EMA + Volume rules.")

if __name__ == "__main__":
    run_sniper()
