import os, requests, json, time
import pandas as pd
import yfinance as yf
import warnings

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
            return [f"{s['symbol']}.NS" for s in response.json()['data'] if s['symbol'] != official_name]
        return []
    except: return []

def run_sniper():
    print("\n🎯 --- SNIPER MISSION: DEEP DEBUG ---")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_candidates = []
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"\n📂 Sector [{sector}]: Found {len(tickers)} stocks.")
        
        for t in tickers:
            try:
                # 1. Download Data
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                
                # Fix for MultiIndex columns in new yfinance versions
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                if df.empty or len(df) < 50:
                    print(f"   ❌ {t.ljust(12)}: No data found")
                    continue
                
                # 2. Extract Values
                close = df['Close'].dropna()
                curr_price = float(close.iloc[-1])
                ema20 = close.ewm(span=20).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]
                
                # 3. DEBUG LOGGING: Show us the values
                # print(f"DEBUG {t}: Price {round(curr_price,1)} | EMA20 {round(ema20,1)} | EMA50 {round(ema50,1)}")

                # 4. TREND CHECK
                if curr_price > ema20 and ema20 > ema50:
                    print(f"   ✅ TREND MATCH: {t.ljust(12)}")
                    all_candidates.append({
                        "ticker": t, "sector": sector, "price": round(curr_price, 2)
                    })
                else:
                    # Optional: uncomment to see rejections in GitHub logs
                    # print(f"   ❌ {t.ljust(12)}: Failed Trend (P:{round(curr_price,1)} E20:{round(ema20,1)})")
                    pass
            except Exception as e:
                print(f"   ⚠️ Error scanning {t}: {e}")
                continue
            time.sleep(0.1)

    print(f"\n✅ TOTAL TREND MATCHES: {len(all_candidates)}")
    if all_candidates:
        msg = f"🎯 **SNIPER TREND REPORT**\nFound {len(all_candidates)} uptrending stocks."
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg})
    else:
        print("ℹ️ No matches found in current scan.")

if __name__ == "__main__":
    run_sniper()
