import os, requests, json
import pandas as pd
import yfinance as yf

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_safe_close(df):
    """Flattens Yahoo Finance data and removes empty values."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df['Close'].dropna()

def calc_percentile(series):
    """Calculates Relative Strength Rank (0-100)."""
    if series.empty: return 0
    current = series.iloc[-1]
    return (series < current).mean() * 100

def run_agent():
    print("📊 --- SCOUT AGENT SESSION START ---")
    try:
        if not os.path.exists('config.json'):
            print("❌ FATAL: config.json not found in directory.")
            return

        with open('config.json', 'r') as f:
            config = json.load(f)
        
        sector_tickers = config.get("sectors", {})
        print(f"📂 Loaded {len(sector_tickers)} sectors from config.")

        # Download Benchmark
        print("🌐 Fetching Nifty 50 Benchmark...")
        bm_raw = yf.download("^NSEI", period="1y", progress=False)
        bm_data = get_safe_close(bm_raw)
        
        if bm_data.empty:
            print("❌ ERROR: Could not fetch Benchmark (^NSEI). Check internet/Yahoo status.")
            return

        results = []
        for name, ticker in sector_tickers.items():
            print(f"\n🔍 [SCANNING] Sector: {name} | Ticker: {ticker}")
            
            try:
                s_raw = yf.download(ticker, period="1y", progress=False)
                s_data = get_safe_close(s_raw)
                
                # ERROR LOG: Check for data availability
                if s_data.empty:
                    print(f"   ⚠️ LOG: No data found for {ticker}. Check if ticker is correct on Yahoo Finance.")
                    continue
                if len(s_data) < 126:
                    print(f"   ⚠️ LOG: Insufficient history for {name} ({len(s_data)} days). Need 126+.")
                    continue

                # Align and calculate RS
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                rs = combined['s'] / combined['b']
                
                # Performance Math
                p3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                p6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)
                r3 = round(calc_percentile(rs.pct_change(63).tail(252)))
                r6 = round(calc_percentile(rs.pct_change(126).tail(252)))
                
                score = round((r3+r6)/2)
                results.append({"name": name, "p3": p3, "p6": p6, "prc": score})
                print(f"   ✅ SUCCESS: RS Score: {score} | 3M Velocity: {p3}%")

            except Exception as e:
                print(f"   ❌ ERROR: Failed to process {name}: {str(e)}")

        # Ranking and Handoff
        df = pd.DataFrame(results).sort_values("prc", ascending=False)
        
        # SNIPER PREVIEW: Log which sectors actually made the cut
        active_sectors = df[(df['p3'] > 0) & (df['p6'] > 0)]['name'].tolist()
        always_scan = config.get("always_scan", [])
        final_list = list(set(active_sectors + always_scan))

        print(f"\n📦 --- HANDOFF TO SNIPER ---")
        print(f"   Active (Positive RS): {active_sectors}")
        print(f"   Always Scan Themes: {always_scan}")
        print(f"   TOTAL SECTORS FOR SNIPER: {final_list}")

        with open('active_sectors.json', 'w') as f:
            json.dump(final_list, f)

        # Telegram Summary
        msg = "📊 **SCOUT SECTOR RANKING**\n\n`SECTOR         PRC   3M_%` \n"
        for _, r in df.iterrows():
            msg += f"`{r['name'].ljust(14)} {str(r['prc']).ljust(5)} {str(r['p3']).ljust(5)}` \n"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        
        print("\n✅ SCOUT COMPLETED. Report sent to Telegram.")

    except Exception as e:
        print(f"❌ CRITICAL AGENT ERROR: {e}")

if __name__ == "__main__":
    run_agent()
