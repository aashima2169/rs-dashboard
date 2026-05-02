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
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.nseindia.com/"
        }
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
    print("\n🎯 --- SNIPER MISSION: 6-CANDLE CONSOLIDATION SCAN ---")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂 Sector [{sector}]: Found {len(tickers)} tickers. Analyzing...")
        
        for t in tickers:
            try:
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                if df.empty or len(df) < 60: continue
                
                close = df['Close'].dropna()
                volume = df['Volume'].dropna()
                high = df['High'].dropna()
                low = df['Low'].dropna()
                
                # --- EMA LOGIC ---
                cmp = round(float(close.iloc[-1]), 2)
                ema10 = round(close.ewm(span=10).mean().iloc[-1], 2)
                ema21 = round(close.ewm(span=21).mean().iloc[-1], 2)
                ema50 = round(close.ewm(span=50).mean().iloc[-1], 2)
                dist_ema21 = round(((cmp - ema21) / ema21) * 100, 2)
                
                # --- VOLUME LOGIC (VDU) ---
                avg_vol_20 = volume.rolling(20).mean().iloc[-1]
                curr_vol_3 = volume.tail(3).mean()
                vdu_ratio = round(curr_vol_3 / avg_vol_20, 2)
                
                # --- STRICT 6-DAY CONSOLIDATION LOGIC ---
                # Find the max high and min low of the last 6 candles
                recent_high = high.tail(6).max()
                recent_low = low.tail(6).min()
                
                # Calculate the total % range of those 6 days
                consol_range_pct = round(((recent_high - recent_low) / recent_low) * 100, 2)

                # --- IMPROVED FILTERS ---
                # 1. EMA Stack: 10 > 21 > 50 and Price > 50
                # 2. Dist < 5%: Not overextended
                # 3. Consolidation < 4.5%: The last 6 candles must be trapped in a tight 4.5% box
                # 4. Volume < 1.1: Volume is drying up
                if ema10 > ema21 > ema50 and cmp > ema50 and dist_ema21 < 5.0 and consol_range_pct <= 4.5 and vdu_ratio < 1.1:
                    all_data.append({
                        "Ticker": t, "Sector": sector, "CMP": cmp,
                        "EMA10": ema10, "EMA21": ema21, "EMA50": ema50,
                        "VDU": vdu_ratio, "Consol_%": consol_range_pct,
                        "Dist_21_%": dist_ema21
                    })
            except: continue
            time.sleep(0.05)

    if all_data:
        # Sort by the tightest consolidation first
        all_data = sorted(all_data, key=lambda x: x['Consol_%'])
        
        filename = "sniper_candidates.csv"
        pd.DataFrame(all_data).to_csv(filename, index=False)
        send_telegram_file(filename)
        
        msg = "🎯 **SNIPER ELITE: TIGHT CONSOLIDATION**\n"
        msg += "`TICKER   CMP      VDU    RANGE%` \n"
        for c in all_data[:12]:
            msg += f"`{c['Ticker'].ljust(8)} {str(c['CMP']).ljust(8)} {str(c['VDU']).ljust(6)} {str(c['Consol_%']).ljust(5)}` \n"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    else:
        pd.DataFrame(columns=["Ticker"]).to_csv("sniper_candidates.csv", index=False)
        print("ℹ️ No matches found today.")

if __name__ == "__main__":
    run_sniper()
