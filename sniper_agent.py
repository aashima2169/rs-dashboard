import os, requests, json, time
import pandas as pd
import yfinance as yf
import numpy as np
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_stocks(sector_key):
    """Resilient fetcher for NSE index constituents."""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        if not official_name:
            print(f"⚠️ No mapping found for {sector_key} in config.json")
            return []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.nseindia.com/"
        }
        
        session = requests.Session()
        # Hit home page to get session cookies
        session.get("https://www.nseindia.com", headers=headers, timeout=15)
        
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        response = session.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            # Extract symbols and append .NS for Yahoo Finance compatibility
            symbols = [f"{s['symbol']}.NS" for s in data['data'] if s['symbol'] != official_name]
            return symbols
        else:
            print(f"❌ NSE API Error for {sector_key}: Status {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Error fetching {sector_key}: {e}")
        return []

def run_sniper():
    print("\n🎯 --- SNIPER MISSION: EMA TREND SCAN ---")
    if not os.path.exists('active_sectors.json'):
        print("❌ active_sectors.json not found!")
        return
        
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    filename = "sniper_candidates.csv"
    
    for sector in active_sectors:
        tickers = get_stocks(sector)
        # Fix: Added back the ticker count to debug if get_stocks is failing
        print(f"📂 Sector [{sector}]: Found {len(tickers)} tickers. Starting analysis...")
        
        for t in tickers:
            try:
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if df.empty or len(df) < 60: continue
                
                close = df['Close']
                volume = df['Volume']
                cmp = float(close.iloc[-1])
                
                # --- CORE TREND RULES (EMA 10 > 21 > 50) ---
                ema10 = close.ewm(span=10).mean().iloc[-1]
                ema21 = close.ewm(span=21).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]
                
                # Logic per your requirement: Stacked EMAs and Price above EMA50
                if ema10 > ema21 > ema50 and cmp > ema50:
                    
                    # Metrics for your CSV 
                    avg_vol_20 = volume.rolling(20).mean().iloc[-1]
                    curr_vol_3 = volume.tail(3).mean()
                    vdu_ratio = round(curr_vol_3 / avg_vol_20, 2)
                    
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
        # Sort by VDU for the CSV export
        all_data = sorted(all_data, key=lambda x: x['VDU_Ratio'])
        pd.DataFrame(all_data).to_csv(filename, index=False)
        
        # Send to Telegram
        url_doc = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(filename, "rb") as file:
            requests.post(url_doc, data={"chat_id": CHAT_ID}, files={"document": file})
            
        msg = f"🎯 **SCAN COMPLETE: {len(all_data)} MATCHES**\n"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg})
    else:
        pd.DataFrame(columns=["Ticker"]).to_csv(filename, index=False)
        print("ℹ️ No trending stocks found (EMA 10>21>50 failed).")

if __name__ == "__main__":
    run_sniper()
