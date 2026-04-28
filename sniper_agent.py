import os
import json
import pandas as pd
import yfinance as yf
from nsepython import nse_get_index_quote

def get_sector_tickers(sector_name):
    """Dynamically pulls every stock in the sector from NSE."""
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    # Map 'NiftyIT' -> 'NIFTY IT'
    official_name = config.get("nse_index_mapping", {}).get(sector_name)
    if not official_name: return []

    try:
        # Dynamic fetch - no more hardcoded lists!
        payload = nse_get_index_quote(official_name)
        return [stock['symbol'] + ".NS" for stock in payload['data'] if stock['symbol'] != official_name]
    except:
        return []

def professional_screen(ticker):
    """The Multi-Stage Filter."""
    try:
        df = yf.download(ticker, period="1y", progress=False)
        if len(df) < 200: return None

        curr = df['Close'].iloc[-1]
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        ma150 = df['Close'].rolling(150).mean().iloc[-1]
        avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
        recent_vol = df['Volume'].tail(3).mean()

        # FILTER 1: Trend Check (Is it a Leader?)
        is_leader = curr > ma50 > ma150
        
        # FILTER 2: Volume Dry-up (Is it resting?)
        # VCP requires 'quiet' volume before the blast
        is_quiet = recent_vol < (avg_vol * 0.8)

        # FILTER 3: VCP Math (Tightness)
        vol10 = (df['High'].tail(10).max() - df['Low'].tail(10).min()) / curr
        vol30 = (df['High'].iloc[-40:-10].max() - df['Low'].iloc[-40:-10].min()) / df['Close'].iloc[-40]
        tightness = vol10 / vol30

        if is_leader and is_quiet and tightness < 0.7:
            return {"ticker": ticker, "tightness": round(tightness, 2), "price": round(curr, 2)}
        return None
    except:
        return None

def run_sniper():
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    final_list = []
    for sector in active_sectors:
        print(f"📡 Scanning ALL stocks in {sector}...")
        tickers = get_sector_tickers(sector)
        for t in tickers:
            # Skip the specific broken HUL if it appears
            if "HUL" in t: continue 
            
            res = professional_screen(t)
            if res: final_list.append(res)

    # Telegram Output logic here...
    print(f"Found {len(final_list)} VCP candidates.")

if __name__ == "__main__":
    run_sniper()
