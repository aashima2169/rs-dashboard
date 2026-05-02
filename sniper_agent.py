import os, requests, json, time
import pandas as pd
import yfinance as yf
import warnings

# Suppress warnings for cleaner logs
warnings.simplefilter(action='ignore', category=FutureWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_stocks(sector_key):
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        
        headers = {"User-Agent": "Mozilla/5.0"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        response = session.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            stocks = [f"{s['symbol']}.NS" for s in response.json()['data'] if s['symbol'] != official_name]
            return list(set(stocks))
        return []
    except Exception as e:
        print(f"   ❌ NSE Fetch Error: {e}")
        return []

def run_sniper():
    print("\n🎯 --- SNIPER MISSION: EMA TREND CHECK ---")
    
    if not os.path.exists('active_sectors.json'):
        print("❌ ERROR: No handoff file found.")
        return
        
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)
    
    print(f"📦 RECEIVED FROM SCOUT: {active_sectors}")

    all_candidates = []
    
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"\n📂 Sector [{sector}]: Received {tickers}")
        
        for t in tickers:
            try:
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if df.empty or len(df) < 50: continue
                
                close = df['Close'].dropna()
                curr_price = float(close.iloc[-1])
                ema20 = close.ewm(span=20).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]
                
                # --- TREND CHECK ONLY ---
                if curr_price > ema20 > ema50:
                    print(f"   ✅ TREND MATCH: {t.ljust(12)} (Price > EMA20 > EMA50)")
                    
                    # We still calculate tightness just to see it in the log
                    h10, l10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
                    h30, l30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
                    denom = (h30 - l30) if (h30 - l30) != 0 else 1.0
                    tightness = round(float((h10 - l10) / denom), 2)

                    all_candidates.append({
                        "ticker": t, "sector": sector, 
                        "price": round(curr_price, 2), "tight": tightness
                    })
            except:
                continue
            time.sleep(0.1)

    print(f"\n✅ SCAN COMPLETE. Trend matches found: {len(all_candidates)}")
    
    if all_candidates:
        msg = "🎯 **SNIPER TREND REPORT**\n\n"
        msg += "`TICKER   SECTOR   PRICE    TIGHT`\n"
        # Showing top 20 matches based on trend
        for c in all_candidates[:20]:
            msg += f"`{c['ticker'].ljust(8)} {c['sector'].ljust(8)} {str(c['price']).ljust(8)} {str(c['tight']).ljust(5)}` \n"
    else:
        msg = "🎯 **SNIPER REPORT**: No stocks are currently in a Price > EMA20 > EMA50 uptrend."

    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                 json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    run_sniper()
