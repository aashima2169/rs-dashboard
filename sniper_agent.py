import os
import requests
import pandas as pd
import subprocess
import sys
import json

# Ensure required libraries are installed
for lib in ["yfinance", "nsepython"]:
    try:
        __import__(lib)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

import yfinance as yf
from nsepython import nse_get_index_quote

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Ticker mapping to fix common Yahoo Finance mismatches
YF_MAPPING = {
    "JSWSTEEL": "JSWSTEEL.NS",
    "IOC": "IOC.NS",
    "SAIL": "SAIL.NS",
    "TATASTEEL": "TATASTEEL.NS",
    "HINDUNILVR": "HINDUNILVR.NS",
    "MCDOWELL-N": "UNITDSPR.NS"
}

def get_nifty_constituents(sector_key):
    """Fetch live constituents from NSE dynamically based on config mapping"""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        official_name = config["nse_index_mapping"].get(sector_key)
        if not official_name:
            return []

        # Fetch live data from NSE
        payload = nse_get_index_quote(official_name)
        tickers = []
        
        for stock in payload.get('data', []):
            symbol = stock['symbol']
            # Apply custom Yahoo Finance fixes
            if symbol in YF_MAPPING:
                tickers.append(YF_MAPPING[symbol])
            else:
                tickers.append(f"{symbol}.NS")
        
        return tickers
    except Exception as e:
        print(f"⚠️ Error fetching {sector_key} constituents: {e}")
        return []

def professional_screen(ticker):
    """
    VCP Sniper Logic:
    - Stage 2 Uptrend (EMA 20 > 50 > 100)
    - Within 6% of EMA 20 (Momentum proximity)
    - Tightness < 0.9 OR 1.5x Volume Breakout
    """
    try:
        df = yf.download(ticker, period="1y", progress=False)
        if len(df) < 100: return None
        
        close = df['Close']
        curr_price = close.iloc[-1]
        vol_today = df['Volume'].iloc[-1]
        avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
        
        # 1. TREND: Perfect Stage 2 Alignment
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        ema100 = close.ewm(span=100).mean().iloc[-1]
        
        if not (curr_price > ema20 > ema50 > ema100):
            return None

        # 2. PROXIMITY: Anti-chasing filter (NETWEB catch)
        if curr_price > (ema20 * 1.06): 
            return None

        # 3. VCP TIGHTNESS (Loosened to 0.9 for trending stocks)
        high10, low10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
        high30, low30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
        tightness = (high10 - low10) / (high30 - low30)

        # 4. VOLUME EXCEPTION (SCI catch)
        is_breakout = vol_today > (avg_vol * 1.5)

        if tightness < 0.9 or is_breakout:
            return {
                "ticker": ticker, 
                "price": round(curr_price, 2),
                "tightness": round(tightness, 2),
                "type": "Breakout" if is_breakout else "VCP"
            }
        return None
    except:
        return None

def run_sniper():
    try:
        print("🔫 SNIPER AGENT STARTED...")
        
        # Load active sectors and config
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        if not os.path.exists('active_sectors.json'):
            print("ERROR: active_sectors.json not found!")
            return

        with open('active_sectors.json', 'r') as f:
            active_sectors = json.load(f)

        # Force 'Always Scan' sectors (Defence, Digital) to be included
        always_scan = config.get("always_scan", [])
        scan_list = list(set(active_sectors + always_scan))

        print(f"📊 Scanning sectors: {scan_list}")
        
        all_candidates = []
        total_screened = 0
        
        for sector in scan_list:
            print(f"\n🔍 Fetching constituents for {sector}...")
            constituents = get_nifty_constituents(sector)
            
            for ticker in constituents:
                result = professional_screen(ticker)
                total_screened += 1
                if result:
                    result["sector"] = sector
                    all_candidates.append(result)
                    print(f"  ✅ {ticker}: Found!")

        # Final Report Generation
        all_candidates = sorted(all_candidates, key=lambda x: x['tightness'])
        
        if all_candidates:
            msg = f"🎯 **SNIPER REPORT**\n`Screened: {total_screened} | Qualified: {len(all_candidates)}`\n\n"
            msg += "`TICKER  SECTOR   PRICE    TIGHT TYPE`\n"
            for c in all_candidates[:12]:
                msg += f"`{c['ticker'].ljust(7)} {c['sector'].ljust(8)} {str(c['price']).ljust(8)} {str(c['tightness']).ljust(5)} {c['type']}`\n"
        else:
            msg = "🎯 **SNIPER REPORT**\n`0 Candidates found today.`"

        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        
        print(f"✅ COMPLETED. Candidates: {len(all_candidates)}")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    run_sniper()
