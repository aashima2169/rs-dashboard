import pandas as pd
import yfinance as yf
import json
import os

# --- MAPPING SECTORS TO TICKERS ---
# You can expand this list with more tickers for each sector
SECTOR_MAP = {
    "NiftyIT": ["NETWEB.NS", "TCS.NS", "INFY.NS", "KPITTECH.NS", "TATAELXSI.NS"],
    "Pharma": ["SUNPHARMA.NS", "DIVISLAB.NS", "CIPLA.NS", "TORNTPHARM.NS"],
    "Realty": ["DLF.NS", "LODHA.NS", "OBEROIRLTY.NS", "GODREJPROP.NS"],
    "FMCG": ["CUPID.NS", "TATACONSUM.NS", "VBL.NS", "BRITANNIA.NS"],
    "Railways*": ["IRFC.NS", "RVNL.NS", "IRCON.NS", "RITES.NS"]
}

def is_stage2_vcp(ticker):
    """Checks if a stock is in a Stage 2 Uptrend and showing VCP-like tightness."""
    try:
        df = yf.download(ticker, period="1y", progress=False)
        if len(df) < 200: return False

        # 1. Trend Filter (Minervini Stage 2 Template)
        current_price = df['Close'].iloc[-1]
        sma50 = df['Close'].rolling(window=50).mean().iloc[-1]
        sma150 = df['Close'].rolling(window=150).mean().iloc[-1]
        sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
        
        is_uptrend = (current_price > sma50 > sma150 > sma200)

        # 2. VCP Filter (Volatility Contraction)
        # We look for the 10-day price range getting 'tighter' than the 30-day range
        recent_range = (df['High'].tail(10).max() - df['Low'].tail(10).min()) / df['Close'].iloc[-1]
        prior_range = (df['High'].iloc[-40:-10].max() - df['Low'].iloc[-40:-10].min()) / df['Close'].iloc[-40]
        
        is_tight = recent_range < (prior_range * 0.7) # 30% contraction

        return is_uptrend and is_tight
    except:
        return False

def run_sniper():
    # 1. Load active sectors from Agent 1
    if not os.path.exists('active_sectors.json'):
        print("Waiting for Agent 1 to generate sector data...")
        return

    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    print(f"🎯 Sniper Agent starting scan for: {active_sectors}")
    
    candidates = []
    for sector in active_sectors:
        tickers = SECTOR_MAP.get(sector, [])
        for ticker in tickers:
            if is_stage2_vcp(ticker):
                candidates.append(ticker)

    # 2. Output the findings
    if candidates:
        print(f"🚀 VCP Breakout Candidates Found: {candidates}")
        # Here you can add your Telegram call or move to a Vision Agent
    else:
        print("No high-conviction VCP setups found today.")

if __name__ == "__main__":
    run_sniper()
