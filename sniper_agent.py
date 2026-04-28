import os
import json
import pandas as pd
import yfinance as yf
import requests
import sys

# 1. SETUP & CONFIG
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CONFIG_PATH = "config.json"

if not os.path.exists(CONFIG_PATH):
    print("Config file missing.")
    sys.exit(1)

with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

def get_live_tickers(sector_name):
    """Dynamically fetches tickers based on Agent 1's lead."""
    # Check custom baskets first (e.g., Railways)
    if sector_name in config.get("custom_baskets", {}):
        return config["custom_baskets"][sector_name]
    
    # Otherwise, map to NSE index constituents
    # Note: In a production env, you'd use nsepython here to be 100% dynamic.
    # For now, we use a robust sample list based on your mapping.
    sample_mapping = {
        "NiftyIT": ["NETWEB.NS", "TCS.NS", "INFY.NS", "KPITTECH.NS", "COFORGE.NS"],
        "Pharma": ["SUNPHARMA.NS", "DIVISLAB.NS", "CIPLA.NS", "DRREDDY.NS"],
        "FMCG": ["CUPID.NS", "VBL.NS", "TATACONSUM.NS", "HUL.NS"],
        "PSE": ["SCI.NS", "PFC.NS", "RECLTD.NS", "HAL.NS"]
    }
    return sample_mapping.get(sector_name, [])

def check_vcp_math(ticker):
    """The logic applied to Netweb/SCI: Stage 2 + Tightness."""
    try:
        df = yf.download(ticker, period="1y", progress=False)
        if len(df) < 150: return None
        
        close = df['Close']
        # Stage 2 Filter: Price > 50MA > 200MA
        ma50 = close.rolling(50).mean().iloc[-1]
        ma200 = close.rolling(200).mean().iloc[-1]
        curr = close.iloc[-1]
        
        if not (curr > ma50 > ma200):
            return None

        # VCP Tightness (Volatility Contraction)
        # Looking for the 'Pivot' where 10-day volatility is 50% of 30-day volatility
        vol10 = (df['High'].tail(10).max() - df['Low'].tail(10).min()) / curr
        vol30 = (df['High'].iloc[-40:-10].max() - df['Low'].iloc[-40:-10].min()) / df['Close'].iloc[-40]
        
        tightness_score = round((vol10 / vol30), 2)
        
        if tightness_score < 0.7: # 30% or more contraction
            return {"ticker": ticker, "tightness": tightness_score, "price": round(curr, 2)}
        return None
    except:
        return None

def run_sniper():
    # 1. Read the hand-off from Agent 1
    if not os.path.exists('active_sectors.json'):
        print("No active sectors found. Run Agent 1 first.")
        return

    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    print(f"🎯 Sniper identifying setups in: {active_sectors}")
    hits = []

    for sector in active_sectors:
        tickers = get_live_tickers(sector)
        for t in tickers:
            result = check_vcp_math(t)
            if result:
                hits.append(result)

    # 2. Build Telegram Alert
    if hits:
        alert = "🎯 **VCP SNIPER ALERTS**\n*High-Tightness Setups Identified*\n\n"
        for h in hits:
            alert += f"🚀 **{h['ticker']}**\n"
            alert += f"Price: ₹{h['price']} | Tightness: {h['tightness']} (Lower is better)\n"
            alert += f"Pattern: Potential VCP/Breakout Retest\n\n"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": alert, "parse_mode": "Markdown"})
        print(f"Alerts sent for: {[h['ticker'] for h in hits]}")
    else:
        print("No VCP setups confirmed today.")

if __name__ == "__main__":
    run_sniper()
