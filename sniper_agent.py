import os, requests, json, time
import pandas as pd
import yfinance as yf
import numpy as np
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
    print("\n🎯 --- SNIPER MISSION: EMA TREND + SCALABLE METRICS ---")
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
                
                # --- CORE TREND RULES (The only hard filters left) ---
                ema10 = close.ewm(span=10).mean().iloc[-1]
                ema21 = close.ewm(span=21).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]
                
                # We only filter for the basic uptrend you requested
                if ema10 > ema21 > ema50 and cmp > ema50:
                    
                    # --- CALCULATE METRICS (Instead of filtering by them) ---
                    # 1. Volume Dry-up (VDU): Lower is better
                    avg_vol_20 = volume.rolling(20).mean().iloc[-1]
                    curr_vol_3 = volume.tail(3).mean()
                    vdu_ratio = round(curr_vol_3 / avg_vol_20, 2)
                    
                    # 2. Tightness (VCP): Current 10-day volatility vs 40-day volatility
                    std_10 = close.tail(10).std()
                    std_40 = close.tail(40).std()
                    vcp_ratio = round(std_10 / std_40, 2) if std_40 > 0 else 1.0

                    all_data.append({
                        "Ticker": t,
                        "Sector": sector,
                        "CMP": round(cmp, 2),
                        "EMA10": round(ema10, 2),
                        "EMA21": round(ema21, 2),
                        "EMA50": round(ema50, 2),
                        "VDU_Ratio": vdu_ratio,
                        "VCP_Tightness": vcp_ratio
                    })
            except: continue
            time.sleep(0.05)

    if all_data:
        # Sort by VDU_Ratio so the "Dry-up" candidates are at the top
        all_data = sorted(all_data, key=lambda x: x['VDU_Ratio'])
        df_results = pd.DataFrame(all_data)
        df_results.to_csv(filename, index=False)
        
        # Send File to Telegram
        url_doc = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(filename, "rb") as file:
            requests.post(url_doc, data={"chat_id": CHAT_ID}, files={"document": file})
            
        msg = f"🎯 **SCAN COMPLETE: {len(all_data)} MATCHES**\n"
        msg += "List sorted by lowest Volume Dry-up (VDU).\n"
        msg += "`TICKER   CMP      VDU    TIGHT` \n"
        for c in all_data[:12]:
            msg += f"`{c['Ticker'].ljust(8)} {str(c['CMP']).ljust(8)} {str(c['VDU_Ratio']).ljust(6)} {str(c['VCP_Tightness']).ljust(5)}` \n"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    else:
        # Always create file for YAML safety
        pd.DataFrame(columns=["Ticker"]).to_csv(filename, index=False)
        print("ℹ️ No trending stocks found (EMA 10>21>50 failed).")

if __name__ == "__main__":
    run_sniper()
