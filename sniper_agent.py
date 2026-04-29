import os
import requests
import pandas as pd
import json
import yfinance as yf
import time
from nsepython import nse_get_index_quote

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_nifty_constituents(sector_key):
    """Fetch live stock list from NSE. Zero hardcoded tickers."""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        # Get the official NSE name from config (e.g., "NIFTY METAL")
        # Structure assumed: "SectorName": ["YahooTicker", "NSEName"]
        mapping = config.get("sectors", {}).get(sector_key)
        if not mapping or len(mapping) < 2:
            print(f"  ⚠️ No NSE mapping found for {sector_key}")
            return []

        official_name = mapping[1]
        
        # Live Fetch
        payload = nse_get_index_quote(official_name)
        if payload and 'data' in payload:
            print(f"  🌐 Dynamic Fetch Successful: {len(payload['data'])} stocks in {sector_key}")
            return [f"{s['symbol']}.NS" for s in payload['data'] if s['symbol'] != official_name]
        
        print(f"  ⚠️ NSE returned empty data for {sector_key}")
        return []
    except Exception as e:
        print(f"  ❌ NSE Connection Error for {sector_key}: {e}")
        return []

def professional_screen(ticker):
    """VCP & Stage 2 Trend Filter with Yahoo 404 & FutureWarning Fixes"""
    try:
        # Create session to avoid 'Delisted/404' Yahoo blocks
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})

        df = yf.download(ticker, period="1y", progress=False, session=session, auto_adjust=True)
        
        if df.empty or len(df) < 100: 
            return None
        
        # Fix for Multi-Index Columns in new yfinance versions
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close'].dropna()
        # .item() fixes the "Calling float on single element Series" FutureWarning
        curr_price = float(close.iloc[-1].item())
        vol_today = float(df['Volume'].iloc[-1].item())
        avg_vol = float(df['Volume'].rolling(20).mean().iloc[-1].item())
        
        # EMA Calculations
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        ema100 = close.ewm(span=100).mean().iloc[-1]
        
        # Filter 1: Stage 2 Alignment (Uptrend)
        if not (curr_price > ema20 > ema50 > ema100): return None
        
        # Filter 2: Proximity (Don't buy the "extended" stocks)
        if curr_price > (ema20 * 1.08): return None

        # Filter 3: VCP Tightness Logic
        high10, low10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
        high30, low30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
        tightness = (high10 - low10) / (high30 - low30)

        is_breakout = vol_today > (avg_vol * 1.5)

        # Final Match Condition
        if tightness < 0.9 or is_breakout:
            return {
                "ticker": ticker, 
                "price": round(curr_price, 2),
                "tightness": round(float(tightness), 2),
                "type": "Breakout" if is_breakout else "VCP"
            }
    except:
        return None

def run_sniper():
    print("🔫 SNIPER AGENT STARTED...")
    if not os.path.exists('active_sectors.json'):
        print("❌ No active_sectors.json found. Run Scout Agent first.")
        return

    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)
    
    with open('config.json', 'r') as f:
        config = json.load(f)

    # Combine results from Scout with your 'Always Scan' themes
    scan_list = list(set(active_sectors + config.get("always_scan", [])))
    all_candidates = []
    
    for sector in scan_list:
        print(f"🔍 Processing Sector: {sector}")
        tickers = get_nifty_constituents(sector)
        
        # Sleep briefly to avoid triggering rate limits
        time.sleep(1)

        for t in tickers:
            res = professional_screen(t)
            if res:
                res['sector'] = sector
                all_candidates.append(res)
                print(f"   ✅ Hit: {t}")

    # Build and Send Telegram Message
    if all_candidates:
        # Sort by tightness (the lower/tighter the better)
        all_candidates = sorted(all_candidates, key=lambda x: x['tightness'])
        msg = "🎯 **SNIPER REPORT**\n\n`TICKER
