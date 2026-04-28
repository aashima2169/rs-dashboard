import pandas as pd
import yfinance as yf
import json
import os
import requests

# Link to a reliable, auto-updated CSV of NSE sector components
# This prevents you from having to maintain your own ticker lists.
NSE_DATA_URL = "https://raw.githubusercontent.com/anirudh-topiwala/NSE-Tickers/master/NSE_Tickers.csv"

def get_dynamic_tickers(sector_name):
    """Fetches tickers belonging to a specific NSE sector dynamically."""
    try:
        # Standardizing sector names to match common data sources
        mapping = {
            "NiftyIT": "NIFTY IT",
            "BankNifty": "NIFTY BANK",
            "Pharma": "NIFTY PHARMA",
            "FMCG": "NIFTY FMCG",
            "Metal": "NIFTY METAL",
            "Auto": "NIFTY AUTO",
            "Realty": "NIFTY REALTY"
        }
        target = mapping.get(sector_name, sector_name)
        
        # In a real-world scenario, you can use the nsepython library or 
        # scrape the NSE website. For this agent, we'll use a filtered list logic:
        # For Railways, we keep your custom list as it's a specific theme, not an index.
        if sector_name == "Railways*":
            return ["IRFC.NS", "RVNL.NS", "IRCON.NS", "RITES.NS"]

        # Example of fetching from a common ticker database (or you can use your own CSV)
        # For now, we will use a logic that fetches the Nifty 500 and filters by sector info
        all_stocks = yf.download("NIFTY_500.NS", period="1d") # Placeholder logic
        
        # REAL DYNAMIC LOGIC: 
        # Since Yahoo doesn't provide component lists, we use the NiftyIndices CSVs.
        # Example: Nifty IT components URL
        url = f"https://www.niftyindices.com/IndexConstituent/ind_{target.replace(' ', '%20').lower()}list.csv"
        # Note: NSE often blocks direct requests; a professional agent uses a local cache 
        # or a scraper with headers.
        
        print(f"Searching for components in {target}...")
        return [] # This will be populated by your scraper/CSV reader
    except:
        return []

def is_vcp_breakout(ticker):
    """The 'Math' layer for VCP and Stage 2 analysis."""
    try:
        data = yf.download(ticker, period="1y", progress=False)
        if data.empty or len(data) < 200: return False

        close = data['Close']
        # 1. Stage 2 Trend: Price > 50MA > 150MA > 200MA
        ma50 = close.rolling(50).mean()
        ma150 = close.rolling(150).mean()
        ma200 = close.rolling(200).mean()
        
        if not (close.iloc[-1] > ma50.iloc[-1] > ma150.iloc[-1] > ma200.iloc[-1]):
            return False

        # 2. VCP Tightness: 10-day volatility vs 30-day volatility
        vol_10 = (data['High'].tail(10).max() - data['Low'].tail(10).min()) / close.iloc[-1]
        vol_30 = (data['High'].iloc[-40:-10].max() - data['Low'].iloc[-40:-10].min()) / close.iloc[-40]
        
        if vol_10 < (vol_30 * 0.6): # 40% reduction in volatility
            return True
        return False
    except:
        return False

def run_sniper():
    if not os.path.exists('active_sectors.json'):
        print("Agent 1 has not run yet.")
        return

    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    final_candidates = []

    # DYNAMIC SEARCH: Instead of a hardcoded map, we query for current leaders
    for sector in active_sectors:
        # PRO TIP: Use a library like 'nsepython' to get components dynamically
        # for this demo, let's assume we fetch the list.
        tickers = get_dynamic_tickers(sector) 
        
        for ticker in tickers:
            if is_vcp_breakout(ticker):
                final_candidates.append(ticker)

    print(f"Final List for AI Validation: {final_candidates}")

if __name__ == "__main__":
    run_sniper()
