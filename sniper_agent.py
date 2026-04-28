import os
import requests
import pandas as pd
import json
import yfinance as yf
from nsepython import nse_get_index_quote

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_nifty_constituents(sector_key):
    """Fetch live from NSE, with a Hardcoded Fallback for GitHub Actions/Cloud blocks"""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        official_name = config["nse_index_mapping"].get(sector_key)
        
        # 1. Try Dynamic Fetch
        try:
            payload = nse_get_index_quote(official_name)
            if payload and 'data' in payload:
                print(f"  🌐 Dynamic Fetch Successful for {sector_key}")
                return [f"{s['symbol']}.NS" for s in payload['data'] if s['symbol'] != official_name]
        except Exception:
            print(f"  ⚠️ NSE Blocked/Refused connection for {sector_key}. Using Fallback.")

        # 2. Use Fallback from Config if Dynamic fails
        return config.get("fallback_constituents", {}).get(sector_key, [])

    except Exception as e:
        print(f"  ❌ Critical error in constituent fetch: {e}")
        return []

def professional_screen(ticker):
    """VCP & Trend Sniper Logic"""
    try:
        df = yf.download(ticker, period="1y", progress=False)
        if df.empty or len(df) < 100: return None
        
        close = df['Close']
        curr_price = float(close.iloc[-1])
        vol_today = float(df['Volume'].iloc[-1])
        avg_vol = float(df['Volume'].rolling(20).mean().iloc[-1])
        
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        ema100 = close.ewm(span=100).mean().iloc[-1]
        
        # Stage 2 Uptrend + Close to EMA 20
        if not (curr_price > ema20 > ema50 > ema100): return None
        if curr_price > (ema20 * 1.07): return None

        # VCP Tightness
        high10, low10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
        high30, low30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
        tightness = (high10 - low10) / (high30 - low30)

        is_breakout = vol_today > (avg_vol * 1.5)

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
    if not os.path.exists('active_sectors.json'): return

    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)
    
    with open('config.json', 'r') as f:
        config = json.load(f)

    # Combine active sectors with 'Always Scan' themes
    scan_list = list(set(active_sectors + config.get("always_scan", [])))
    all_candidates = []
    
    for sector in scan_list:
        tickers = get_nifty_constituents(sector)
        for t in tickers:
            res = professional_screen(t)
            if res:
                res['sector'] = sector
                all_candidates.append(res)
                print(f"  🎯 Hit: {t}")

    # Sort and Report
    if all_candidates:
        all_candidates = sorted(all_candidates, key=lambda x: x['tightness'])
        msg = "🎯 **SNIPER REPORT**\n\n`TICKER  SECTOR   PRICE    TIGHT`\n"
        for c in all_candidates[:15]:
            msg += f"`{c['ticker'].ljust(7)} {c['sector'].ljust(8)} {str(c['price']).ljust(8)} {str(c['tightness']).ljust(5)}`\n"
    else:
        msg = "🎯 **SNIPER REPORT**: No setups found today."

    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                 json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    run_sniper()
