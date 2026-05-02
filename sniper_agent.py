import os, requests, json, time
import pandas as pd
import yfinance as yf
import numpy as np
import warnings

# Suppress warnings
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
    print("\n🎯 --- SNIPER MISSION: VCP & STAGE 2 LOGIC ---")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂 Sector [{sector}]: Screening {len(tickers)} tickers...")
        
        for t in tickers:
            try:
                # Need at least 200 days for Stage 2 Trend Check
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                if df.empty or len(df) < 200: continue
                
                close = df['Close'].dropna()
                highs = df['High'].dropna()
                lows = df['Low'].dropna()
                volume = df['Volume'].dropna()
                
                cmp = float(close.iloc[-1])
                ema10 = close.ewm(span=10).mean().iloc[-1]
                ema20 = close.ewm(span=20).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]
                sma200 = close.rolling(window=200).mean().iloc[-1]
                
                # --- 1. STAGE 2 STRUCTURAL FILTER ---
                # Price must be above 200 SMA, and 200 SMA must be trending up
                is_stage2 = cmp > sma200 and sma200 > sma200 * 0.98 # Not declining
                # Standard Trend Stack
                is_trending = cmp > ema10 > ema20 > ema50
                
                if not (is_stage2 and is_trending):
                    continue

                # --- 2. VOLATILITY CONTRACTION (VCP) ---
                # Measure the standard deviation of returns (Volatility)
                # We want current volatility (last 10 days) to be < 60% of recent volatility (last 40 days)
                vol_current = close.tail(10).std()
                vol_recent = close.iloc[-40:].std()
                vcp_ratio = round(vol_current / vol_recent, 2) if vol_recent > 0 else 1.0
                
                # --- 3. VOLUME DRY-UP (VDU) ---
                # Volume of last 3 days should be lower than 20-day average volume
                avg_vol_20 = volume.rolling(20).mean().iloc[-1]
                curr_vol_3 = volume.tail(3).mean()
                vdu_ratio = round(curr_vol_3 / avg_vol_20, 2)
                
                # --- 4. HIGH TIGHT FLAG (HTF) CHECK ---
                # Has the stock gained > 25% in the last 3 months? (The 'Flagpole')
                three_month_ago_price = close.iloc[-65] # approx 65 trading days
                three_month_gain = (cmp - three_month_ago_price) / three_month_ago_price
                
                # --- FINAL ELITE LOGIC ---
                # 1. Must be Stage 2
                # 2. Volatility must be contracting (vcp_ratio < 0.7)
                # 3. Volume must be drying up (vdu_ratio < 0.9)
                if vcp_ratio < 0.7 and vdu_ratio < 0.9:
                    print(f"   💎 ELITE VCP: {t.ljust(12)} | VCP: {vcp_ratio} | VDU: {vdu_ratio}")
                    all_data.append({
                        "Ticker": t,
                        "Sector": sector,
                        "CMP": round(cmp, 2),
                        "VCP_Ratio": vcp_ratio,
                        "VDU_Ratio": vdu_ratio,
                        "3M_Gain_%": round(three_month_gain * 100, 2),
                        "Dist_EMA20_%": round(((cmp - ema20)/ema20)*100, 2),
                        "Signal": "HIGH TIGHT FLAG" if three_month_gain > 0.3 else "VCP SETUP"
                    })
            except Exception as e: continue
            time.sleep(0.1)

    if all_data:
        filename = "sniper_elite_vcp.csv"
        pd.DataFrame(all_data).to_csv(filename, index=False)
        send_telegram_file(filename)
        
        msg = "🎯 **SNIPER VCP & VDU REPORT**\n"
        msg += "`TICKER   CMP      VCP    VDU    3M%` \n"
        for c in all_data[:10]:
            msg += f"`{c['Ticker'].ljust(8)} {str(c['CMP']).ljust(8)} {str(c['VCP_Ratio']).ljust(6)} {str(c['VDU_Ratio']).ljust(6)} {str(c['3M_Gain_%']).ljust(5)}%` \n"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    else:
        print("ℹ️ No structural VCP setups found today.")

if __name__ == "__main__":
    run_sniper()
