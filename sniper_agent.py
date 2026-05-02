import os, requests, json, time
import pandas as pd
import yfinance as yf
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

# Environment Variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_stocks(sector_key):
    """Fetches tickers dynamically from NSE API."""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.nseindia.com/"
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        response = session.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return [f"{s['symbol']}.NS" for s in response.json()['data'] if s['symbol'] != official_name]
        return []
    except Exception as e:
        print(f"  ❌ NSE API Error for {sector_key}: {e}")
        return []

def run_sniper():
    print("\n🎯 --- SNIPER MISSION: STEP 1 (DYNAMIC POLE) ---")
    
    if not os.path.exists('active_sectors.json'):
        print("❌ Error: active_sectors.json not found.")
        return
        
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"\n📂 Sector: {sector} | Total Tickers: {len(tickers)}")
        
        for t in tickers:
            try:
                # Fetching 1 year of data for SMA 200
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if df.empty or len(df) < 200:
                    continue
                
                # Cleanup multi-index if present
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                close = df['Close']
                cmp = float(close.iloc[-1])

                # --- DYNAMIC POLE LOGIC ---
                # 1. Look for the lowest point in the last 40 trading days
                lookback_40 = close.tail(40)
                lowest_price = lookback_40.min()
                
                # 2. Find the peak reached AFTER that low point
                low_idx = lookback_40.idxmin()
                peak_since_low = close.loc[low_idx:].max()
                
                # 3. Calculate the % height of the 'Pole'
                pole_pct = ((peak_since_low - lowest_price) / lowest_price) * 100
                
                # --- TREND CHECK ---
                sma200 = close.rolling(window=200).mean().iloc[-1]
                ema10 = close.ewm(span=10).mean().iloc[-1]
                ema21 = close.ewm(span=21).mean().iloc[-1]

                # --- VERBOSE LOGGING ---
                # We log any stock with a pole > 10% so you can see it's working
                if pole_pct > 10:
                    status = "✅" if (pole_pct >= 20 and cmp > sma200) else "❌"
                    print(f"  {status} {t.ljust(12)} | Pole: {round(pole_pct, 1)}% | Above SMA200: {cmp > sma200}")

                # --- FILTER: 20% Pole + Stage 2 Uptrend ---
                if pole_pct >= 20.0 and cmp > sma200 and ema10 > ema21:
                    all_data.append({
                        "Ticker": t,
                        "Sector": sector,
                        "CMP": round(cmp, 2),
                        "Pole_%": round(pole_pct, 2)
                    })
            except Exception as e:
                print(f"  ⚠️ Error analyzing {t}: {e}")
                continue
            
            time.sleep(0.05) # Prevent rate limiting

    if all_data:
        # Sort by strongest pole
        all_data = sorted(all_data, key=lambda x: x['Pole_%'], reverse=True)
        
        filename = "step1_poles.csv"
        pd.DataFrame(all_data).to_csv(filename, index=False)
        
        msg = "🚩 **SNIPER STEP 1: DYNAMIC POLES**\n"
        msg += "`TICKER      POLE%    CMP` \n"
        for c in all_data[:15]:
            msg += f"`{c['Ticker'].ljust(10)} {str(c['Pole_%']).ljust(8)} {str(c['CMP']).ljust(8)}` \n"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        print(f"\n✨ Mission Success: Found {len(all_data)} potential poles.")
    else:
        print("\nℹ️ No stocks met the 20% Pole + SMA 200 criteria.")

if __name__ == "__main__":
    run_sniper()
