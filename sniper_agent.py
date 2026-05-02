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

def send_telegram_file(file_path):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(file_path, "rb") as file:
            requests.post(url, data={"chat_id": CHAT_ID}, files={"document": file})
    except: pass

def run_sniper():
    print("\n🎯 --- SNIPER MISSION: MINERVINI VCP SCAN ---")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂 Sector [{sector}]: Screening...")
        
        for t in tickers:
            try:
                df = yf.download(t, period="2y", progress=False, auto_adjust=True)
                if df.empty or len(df) < 250: continue
                
                close = df['Close']
                volume = df['Volume']
                cmp = float(close.iloc[-1])
                
                # --- 1. MINERVINI TREND TEMPLATE (STAGE 2) ---
                sma50 = close.rolling(50).mean().iloc[-1]
                sma150 = close.rolling(150).mean().iloc[-1]
                sma200 = close.rolling(200).mean().iloc[-1]
                low_52 = close.tail(252).min()
                high_52 = close.tail(252).max()
                
                # Structural Rules
                r1 = cmp > sma150 and cmp > sma200
                r2 = sma150 > sma200
                r3 = sma200 > close.rolling(200).mean().iloc[-22]
                r4 = sma50 > sma150 and sma50 > sma200
                r5 = cmp > sma50
                r6 = cmp >= (high_52 * 0.75) # Within 25% of 52-week high
                r7 = cmp >= (low_52 * 1.30)  # At least 30% above 52-week low
                
                if not (r1 and r2 and r3 and r4 and r5 and r6 and r7):
                    continue

                # --- 2. VCP & VDU (THE 'CHEAT' AREA) ---
                vcp_ratio = close.tail(10).std() / close.tail(40).std()
                vdu_ratio = volume.tail(3).mean() / volume.rolling(20).mean().iloc[-1]
                
                if vcp_ratio < 0.6 and vdu_ratio < 0.8:
                    all_data.append({
                        "Ticker": t, "Sector": sector, "CMP": round(cmp, 2),
                        "EMA10": round(close.ewm(span=10).mean().iloc[-1], 2),
                        "EMA20": round(close.ewm(span=20).mean().iloc[-1], 2),
                        "EMA50": round(close.ewm(span=50).mean().iloc[-1], 2),
                        "VCP_Ratio": round(vcp_ratio, 2), 
                        "VDU_Ratio": round(vdu_ratio, 2)
                    })
            except: continue
            time.sleep(0.05)

    # --- SAVE FILE (Matches YAML Path) ---
    filename = "sniper_candidates.csv"
    if all_data:
        pd.DataFrame(all_data).to_csv(filename, index=False)
        print(f"✅ Created {filename} with {len(all_data)} stocks.")
        
        # Send to Telegram
        send_telegram_file(filename)
        
        # Summary Message
        msg = "🎯 **MINERVINI VCP SHORTLIST**\n`TICKER   CMP      VCP    VDU` \n"
        for c in all_data[:10]:
            msg += f"`{c['Ticker'].ljust(8)} {str(c['CMP']).ljust(8)} {str(c['VCP_Ratio']).ljust(6)} {str(c['VDU_Ratio']).ljust(6)}` \n"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    else:
        # Create an empty file so the YAML upload doesn't error out
        pd.DataFrame(columns=["Ticker"]).to_csv(filename, index=False)
        print("ℹ️ No VCP setups found. Created empty CSV.")

if __name__ == "__main__":
    run_sniper()
