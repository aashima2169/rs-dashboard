import os, requests, json, time
import pandas as pd
import yfinance as yf

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_stocks(sector_key):
    """Fetches stock list with detailed connection logging."""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.nseindia.com/market-data/live-equity-market"
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        response = session.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            stocks = [f"{s['symbol']}.NS" for s in data['data'] if s['symbol'] != official_name]
            print(f"   ✅ RECEIVED: {len(stocks)} symbols from NSE for {sector_key}")
            return list(set(stocks))
        else:
            print(f"   ❌ NSE API Error for {sector_key}: Status {response.status_code}")
            return []
    except Exception as e:
        print(f"   ❌ Connection Error for {sector_key}: {e}")
        return []

def run_sniper():
    print("\n🔫 --- SNIPER AGENT START ---")
    
    # 1. LOG: Handoff Verification
    if not os.path.exists('active_sectors.json'):
        print("❌ ERROR: 'active_sectors.json' is missing! Scout did not hand over data.")
        return
        
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)
    
    print(f"📦 DATA RECEIVED FROM SCOUT: {active_sectors}")
    
    if not active_sectors:
        print("ℹ️ LOG: Active sectors list is empty. No sectors met the momentum criteria.")
        return

    all_candidates = []
    
    # 2. LOG: Individual Sector Processing
    for sector in active_sectors:
        print(f"\n📂 TARGETING SECTOR: {sector}")
        tickers = get_stocks(sector)
        
        if not tickers:
            print(f"   ⚠️ Skipping {sector}: No tickers found.")
            continue
            
        print(f"   🔍 Screening {len(tickers)} stocks for VCP setups...")
        hits_in_sector = 0
        
        for t in tickers:
            try:
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if df.empty or len(df) < 50:
                    continue
                
                # Check for Trend (Price > EMA20 > EMA50)
                close = df['Close'].dropna()
                curr_price = float(close.iloc[-1])
                ema20 = close.ewm(span=20).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]
                
                if curr_price > ema20 > ema50:
                    # Check for Volatility Contraction (Tightness)
                    h10, l10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
                    h30, l30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
                    
                    # Prevent division by zero
                    denominator = (h30 - l30) if (h30 - l30) != 0 else 1.0
                    tightness = (h10 - l10) / denominator

                    if tightness < 1.15: # 15% volatility contraction compared to base
                        print(f"      🔥 HIT: {t.ljust(12)} | Tightness: {round(tightness, 2)}")
                        all_candidates.append({
                            "ticker": t, 
                            "sector": sector, 
                            "price": round(curr_price, 2), 
                            "tight": round(float(tightness), 2)
                        })
                        hits_in_sector += 1
            except:
                continue
            time.sleep(0.3) # API Safety
        
        print(f"   📊 Finished {sector}: Found {hits_in_sector} setups.")

    # 3. Final Report
    print(f"\n✅ SCAN COMPLETE. Total candidates found: {len(all_candidates)}")
    
    if all_candidates:
        # Sort by best tightness first
        all_candidates = sorted(all_candidates, key=lambda x: x['tight'])
        msg = "🎯 **SNIPER VCP REPORT**\n\n"
        msg += "`TICKER   SECTOR   PRICE    TIGHT`\n"
        for c in all_candidates[:15]:
            msg += f"`{c['ticker'].ljust(8)} {c['sector'].ljust(8)} {str(c['price']).ljust(8)} {str(c['tight']).ljust(5)}` \n"
    else:
        msg = "🎯 **SNIPER REPORT**: No stocks met criteria in the active sectors today."

    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                 json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    run_sniper()
