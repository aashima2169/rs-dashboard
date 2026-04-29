import os
import requests
import pandas as pd
import json
import yfinance as yf
from nsepython import nse_get_index_quote

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_nifty_constituents(sector_key):
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        # Look up official NSE name from nse_index_mapping
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        if not official_name: 
            return []
        
        payload = nse_get_index_quote(official_name)
        if payload and 'data' in payload:
            return [f"{s['symbol']}.NS" for s in payload['data'] if s['symbol'] != official_name]
        return []
    except:
        return []

def professional_screen(ticker):
    try:
        # Session to avoid Yahoo blocks
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        
        df = yf.download(ticker, period="1y", progress=False, session=session, auto_adjust=True)
        if df.empty or len(df) < 100: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        close = df['Close'].dropna()
        curr_price = float(close.iloc[-1].item())
        
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        ema100 = close.ewm(span=100).mean().iloc[-1]
        
        if not (curr_price > ema20 > ema50 > ema100): return None
        if curr_price > (ema20 * 1.08): return None

        h10, l10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
        h30, l30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
        tightness = (h10 - l10) / (h30 - l30)

        if tightness < 0.9:
            return {"ticker": ticker, "price": round(curr_price, 2), "tight": round(float(tightness), 2)}
    except:
        return None

def run_sniper():
    print("🔫 SNIPER AGENT STARTED...")
    if not os.path.exists('active_sectors.json'): return

    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)
    
    with open('config.json', 'r') as f:
        config = json.load(f)

    scan_list = list(set(active_sectors + config.get("always_scan", [])))
    all_candidates = []
    
    for sector in scan_list:
        tickers = get_nifty_constituents(sector)
        for t in tickers:
            res = professional_screen(t)
            if res:
                res['sector'] = sector
                all_candidates.append(res)

    if all_candidates:
        all_candidates = sorted(all_candidates, key=lambda x: x['tight'])
        msg = "🎯 **SNIPER REPORT**\n\n`TICKER   SECTOR   PRICE    TIGHT`\n"
        for c in all_candidates[:15]:
            msg += f"`{c['ticker'].ljust(8)} {c['sector'].ljust(8)} {str(c['price']).ljust(8)} {str(c['tight']).ljust(5)}`\n"
    else:
        msg = "🎯 **SNIPER REPORT**: No setups found today."

    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                 json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    print("✅ SNIPER COMPLETED.")

if __name__ == "__main__":
    run_sniper()
