import os, requests, json, time
import pandas as pd
import yfinance as yf
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_stocks(sector_key):
    """Dynamic NSE fetch with robust headers to prevent '0 tickers' error."""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        
        # Enhanced headers to mimic a real browser
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
    print("\n🎯 --- SNIPER MISSION: IMPROVED EMA & VOLUME SCAN ---")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂 Sector [{sector}]: Found {len(tickers)} tickers. Analyzing...")
        
        for t in tickers:
            try:
                # Use 1y data for stable EMA calculations
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                if df.empty or len(df) < 60: continue
                
                close = df['Close'].dropna()
                volume = df['Volume'].dropna()
                
                # --- EMA LOGIC (10 > 21 > 50) ---
                cmp = round(float(close.iloc[-1]), 2)
                ema10 = round(close.ewm(span=10).mean().iloc[-1], 2)
                ema21 = round(close.ewm(span=21).mean().iloc[-1], 2)
                ema50 = round(close.ewm(span=50).mean().iloc[-1], 2)
                
                # --- VOLUME LOGIC (VDU) ---
                avg_vol_20 = volume.rolling(20).mean().iloc[-1]
                curr_vol_3 = volume.tail(3).mean()
                vdu_ratio = round(curr_vol_3 / avg_vol_20, 2)
                
                # --- TIGHTNESS & DISTANCE ---
                dist_ema21 = round(((cmp - ema21) / ema21) * 100, 2)
                
                h10, l10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
                h30, l30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
                tightness = round(float((h10 - l10) / ((h30 - l30) if (h30-l30) != 0 else 1.0)), 2)

                # --- IMPROVED FILTERS ---
                # 1. EMA Stack: Must be in a strong uptrend
                # 2. Dist < 5%: Not overextended from the 21 EMA
                # 3. Tightness < 1.35: Price is contracting
                # 4. Volume < 1.1: Volume is not spiking (Dry-up check)
                if ema10 > ema21 > ema50 and cmp > ema50 and
