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
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        response = session.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return [f"{s['symbol']}.NS" for s in response.json()['data'] if s['symbol'] != official_name]
        return []
    except Exception as e:
        print(f"❌ Error fetching {sector_key}: {e}")
        return []

def run_sniper():
    print("\n🎯 --- HTF STEP 1: DYNAMIC POLE DETECTION ---")
    if not os.path.exists('active_sectors.json'):
        print("⚠️ No active_sectors.json found. Run Scout Agent first.")
        return
        
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_results = [] 
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"\n📂 Analyzing Sector: {sector} ({len(tickers)} stocks)")
        
        for t in tickers:
            try:
                # We need 250 days of data for a reliable 200 SMA
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if df.empty or len(df) < 200:
                    continue
                
                close = df['Close']
                cmp = float(close.iloc[-1])

                # --- 1. LONG TERM TREND (SMA 200) ---
                sma200 = close.rolling(window=200).mean().iloc[-1]
                is_stage2 = cmp > sma200

                # --- 2. DYNAMIC POLE CALCULATION ---
                # Check multiple lookback windows to catch different 'Pole' speeds
                windows = [10, 20, 30, 40]
                pole_strengths = []
                for w in windows:
                    prev_price = float(close.iloc[-w])
                    move = ((cmp - prev_price) / prev_price) * 100
                    pole_strengths.append(move)
                
                best_pole = max(pole_strengths)

                # --- 3. VERBOSE LOGGING ---
                # Only log stocks that have at least some momentum (>10%)
                if best_pole > 10:
                    print(f"  🔍 {t.ljust(12)} | Pole: {round(best_pole, 1)}% | Stage 2: {'YES' if is_stage2 else 'NO'}")

                # --- 4. THE FILTER ---
                if best_pole >= 20.0 and is_stage2:
                    print(f"  ⭐ POLE MATCH: {t} with {round(best_pole, 2)}% move")
                    all_results.append({
                        "Ticker": t, 
                        "CMP": round(cmp, 2),
                        "Max_Pole_%": round(best_pole, 2),
                        "Sector": sector
                    })

            except Exception as e:
                continue
            time.sleep(0.05)

    if all_results:
        all_results = sorted(all_results, key=lambda x: x['Max_Pole_%'], reverse=True)
        
        # Build Telegram Message
        msg = "🚩 **HTF STEP 1: POLES DETECTED**\n"
        msg += "`TICKER      POLE%    CMP` \n"
        for c in all_results[:15]:
            msg += f"`{c['Ticker'].ljust(10)} {str(c['Max_Pole_%']).ljust(8)} {str(c['CMP']).ljust(8)}` \n"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        print(f"\n✅ Total Poles Found: {len(all_results)}")
    else:
        print("\nℹ️ Zero poles found. Consider lowering pole requirement to 15% if market is slow.")

if __name__ == "__main__":
    run_sniper()
