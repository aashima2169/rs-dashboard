import os, requests, json, time
import pandas as pd
import yfinance as yf

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_stocks(sector_key):
    """Fetches constituents with a mandatory cookie handshake to bypass NSE blocks."""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        
        # 1. Setup Session with Browser-like Headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br"
        }
        session = requests.Session()
        
        # 2. Cookie Handshake (Visit NSE home first)
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        
        # 3. Fetch the Index Data
        # We use the specific API URL for index constituents
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        response = session.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            stocks = [f"{s['symbol']}.NS" for s in data['data'] if s['symbol'] != official_name]
            # Remove duplicates and index names
            return list(set(stocks))
        
        print(f"  ⚠️ NSE returned status {response.status_code} for {official_name}")
        return []
    except Exception as e:
        print(f"  ❌ Fetch Error for {sector_key}: {e}")
        return []

def professional_screen(ticker):
    """Trend & VCP Filter"""
    try:
        # Use session to prevent Yahoo 404s
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
        
        # Filter: Price > 20 > 50 > 100 + Not extended from 20 EMA
        if not (curr_price > ema20 > ema50 > ema100): return None
        if curr_price > (ema20 * 1.09): return None

        # VCP Tightness (last 10 days vs previous 30)
        h10, l10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
        h30, l30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
        tightness = (h10 - l10) / (h30 - l30)

        if tightness < 1.0: # Good squeeze
            return {"ticker": ticker, "price": round(curr_price, 2), "tight": round(float(tightness), 2)}
    except:
        return None

def run_sniper():
    print("🔫 SNIPER AGENT STARTED...")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)
    
    all_candidates = []
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"🔍 {sector}: Found {len(tickers)} stocks")
        
        for t in tickers:
            time.sleep(0.2) # Slightly slower to be safe
            res = professional_screen(t)
            if res:
                res['sector'] = sector
                all_candidates.append(res)
                print(f"   🔥 Hit: {t}")

    if all_candidates:
        all_candidates = sorted(all_candidates, key=lambda x: x['tight'])
        msg = "🎯 **SNIPER VCP REPORT**\n\n`TICKER   SECTOR   PRICE    TIGHT`\n"
        for c in all_candidates[:15]:
            msg += f"`{c['ticker'].ljust(8)} {c['sector'].ljust(8)} {str(c['price']).ljust(8)} {str(c['tight']).ljust(5)}` \n"
    else:
        msg = "🎯 **SNIPER REPORT**: No stocks met criteria in active sectors."

    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                 json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    print("✅ DONE.")

if __name__ == "__main__":
    run_sniper()
