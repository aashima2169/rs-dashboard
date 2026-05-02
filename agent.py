import os, requests, json, time
import pandas as pd
import yfinance as yf

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_stocks(sector_key):
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        
        print(f"   📡 NSE FETCH: Fetching symbols for {official_name}...")
        headers = {"User-Agent": "Mozilla/5.0"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        response = session.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            stocks = [f"{s['symbol']}.NS" for s in response.json()['data'] if s['symbol'] != official_name]
            print(f"   ✅ SUCCESS: Found {len(stocks)} stocks.")
            return stocks
        return []
    except Exception as e:
        print(f"   ❌ FETCH ERROR: {e}")
        return []

def run_sniper():
    print("\n🔫 --- SNIPER AGENT START ---")
    
    # LOG THE HANDOFF
    if not os.path.exists('active_sectors.json'):
        print("❌ ERROR: active_sectors.json is missing! Scout Agent did not run.")
        return
        
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)
    
    print(f"📦 HANDOFF DATA RECEIVED: {active_sectors}")
    
    if not active_sectors:
        print("ℹ️ LOG: Active sectors list is empty. Ending session.")
        return

    all_candidates = []
    for sector in active_sectors:
        print(f"\n📂 PROCESSING SECTOR: {sector}")
        tickers = get_stocks(sector)
        
        for t in tickers:
            try:
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if df.empty or len(df) < 50: continue
                
                close = df['Close'].dropna()
                curr_price = float(close.iloc[-1])
                ema20 = close.ewm(span=20).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]
                
                if curr_price > ema20 > ema50:
                    h10, l10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
                    h30, l30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
                    tightness = (h10 - l10) / (h30 - l30) if (h30-l30) != 0 else 2.0
                    
                    if tightness < 1.15:
                        print(f"      🔥 SETUP FOUND: {t} (Tightness: {round(tightness, 2)})")
                        all_candidates.append({"ticker": t, "sector": sector, "price": round(curr_price, 2), "tight": round(float(tightness), 2)})
            except:
                continue
            time.sleep(0.2)

    if all_candidates:
        msg = "🎯 **SNIPER REPORT**\n\n`TICKER   SECTOR   PRICE    TIGHT`\n"
        for c in sorted(all_candidates, key=lambda x: x['tight'])[:15]:
            msg += f"`{c['ticker'].ljust(8)} {c['sector'].ljust(8)} {str(c['price']).ljust(8)} {str(c['tight']).ljust(5)}` \n"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    
    print("✅ SNIPER TASK COMPLETED.")

if __name__ == "__main__":
    run_sniper()
