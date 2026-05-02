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
    print("\n🎯 --- SNIPER MISSION: VOLUME LOGIC FIX ---")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    filename = "sniper_candidates.csv"
    
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂 Sector [{sector}]: Screening...")
        
        for t in tickers:
            try:
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if df.empty or len(df) < 60: continue
                
                close = df['Close']
                volume = df['Volume']
                cmp = float(close.iloc[-1])
                
                # --- RULE 1: THE TREND (EMA 10 > 21 > 50) ---
                ema10 = close.ewm(span=10).mean().iloc[-1]
                ema21 = close.ewm(span=21).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]
                
                if not (ema10 > ema21 > ema50 and cmp > ema50):
                    continue

                # --- RULE 2: VOLUME DRY-UP (VDU) CALCULATION ---
                avg_vol_20 = volume.rolling(20).mean().iloc[-1]
                curr_vol_3 = volume.tail(3).mean()
                vdu_ratio = curr_vol_3 / avg_vol_20
                
                # REMOVED HARD FILTER: We allow anything up to 1.1x average volume
                # This ensures we get a list to look at even in active markets
                if vdu_ratio <= 1.1: 
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
        # Sort by VDU_Ratio (Lowest volume relative to average at the top)
        all_data = sorted(all_data, key=lambda x: x['VDU_Ratio'])
        df_results = pd.DataFrame(all_data)
        df_results.to_csv(filename, index=False)
        
        # Send File to Telegram
        url_doc = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(filename, "rb") as file:
            requests.post(url_doc, data={"chat_id": CHAT_ID}, files={"document": file})
            
        msg = "🎯 **VCP SNIPER: VOLUME SORTED**\n"
        msg += "`TICKER   CMP      VDU` \n"
        for c in all_data[:12]:
            msg += f"`{c['Ticker'].ljust(8)} {str(c['CMP']).ljust(8)} {str(c['VDU_Ratio']).ljust(5)}` \n"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    else:
        pd.DataFrame(columns=["Ticker"]).to_csv(filename, index=False)
        print("ℹ️ Zero matches found.")

if __name__ == "__main__":
    run_sniper()
