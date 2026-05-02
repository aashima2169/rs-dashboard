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
    print("\n🎯 --- SNIPER MISSION: EMA 10/20/50 POSITION SCAN ---")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    
    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂 Sector [{sector}]: Processing {len(tickers)} tickers...")
        
        for t in tickers:
            try:
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                if df.empty or len(df) < 60: continue
                
                # --- CALCULATE ALL EMAs ---
                close = df['Close'].dropna()
                cmp = round(float(close.iloc[-1]), 2)
                ema10 = round(close.ewm(span=10).mean().iloc[-1], 2)
                ema20 = round(close.ewm(span=20).mean().iloc[-1], 2)
                ema50 = round(close.ewm(span=50).mean().iloc[-1], 2)
                
                # Proximity to EMA 20 (Mean Reversion Check)
                dist_ema20_pct = round(((cmp - ema20) / ema20) * 100, 2)
                
                # Tightness (VCP Check)
                h10, l10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
                h30, l30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
                denom = (h30 - l30) if (h30 - l30) != 0 else 1.0
                tightness = round(float((h10 - l10) / denom), 2)

                # --- ELITE CRITERIA ---
                # 1. Stacked Trend: Price > EMA 10 > EMA 20 > EMA 50
                # 2. Not Overextended: CMP is within 5% of EMA 20
                # 3. VCP Pattern: Tightness < 1.25
                if cmp > ema10 > ema20 > ema50 and dist_ema20_pct < 5.0 and tightness < 1.30:
                    
                    status = "🔥 BUY ZONE" if dist_ema20_pct < 2.5 else "👀 WATCH"
                    
                    all_data.append({
                        "Ticker": t,
                        "Sector": sector,
                        "CMP": cmp,
                        "EMA10": ema10,
                        "EMA20": ema20,
                        "EMA50": ema50,
                        "Dist_EMA20_%": dist_ema20_pct,
                        "Tightness": tightness,
                        "Signal": status
                    })
            except: continue
            time.sleep(0.1)

    if all_data:
        # Save detailed CSV for analysis
        df_results = pd.DataFrame(all_data)
        df_results.to_csv("sniper_candidates.csv", index=False)
        
        # Sort for Telegram (tightest first)
        all_data = sorted(all_data, key=lambda x: x['Tightness'])
        
        msg = "🎯 **SNIPER ELITE: STACKED EMAs**\n"
        msg += "`TICKER   CMP      TIGHT  DIST%`\n"
        for c in all_data[:15]:
            msg += f"`{c['Ticker'].ljust(8)} {str(c['CMP']).ljust(8)} {str(c['Tightness']).ljust(5)}  {str(c['Dist_EMA20_%']).ljust(5)}%` \n"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        print(f"✅ Mission Complete: Found {len(all_data)} Elite stocks.")
    else:
        print("ℹ️ No stocks met the Stacked EMA + VCP criteria today.")

if __name__ == "__main__":
    run_sniper()
