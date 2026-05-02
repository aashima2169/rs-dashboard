import os, requests, json
import pandas as pd
import yfinance as yf

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_safe_close(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df['Close'].dropna()

def calc_percentile(series):
    if series.empty: return 0
    current = series.iloc[-1]
    return (series < current).mean() * 100

def run_agent():
    print("📊 --- SCOUT AGENT SESSION START ---")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        sector_tickers = config.get("sectors", {})
        print(f"📂 Config loaded. Scanning {len(sector_tickers)} sectors...")
        
        # Download Benchmark (Nifty 50)
        bm_data = get_safe_close(yf.download("^NSEI", period="1y", progress=False))
        
        results = []
        for name, ticker in sector_tickers.items():
            print(f"🔍 [SCANNING] {name} ({ticker})")
            try:
                s_data = get_safe_close(yf.download(ticker, period="1y", progress=False))
                if s_data.empty:
                    print(f"   ⚠️ LOG: No data found for {ticker}")
                    continue

                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                rs = combined['s'] / combined['b']
                
                # Performance Metrics
                p3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                p6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)
                r3 = round(calc_percentile(rs.pct_change(63).tail(252)))
                r6 = round(calc_percentile(rs.pct_change(126).tail(252)))
                
                results.append({"name": name, "p3": p3, "p6": p6, "r3": r3, "r6": r6, "prc": round((r3+r6)/2)})
            except Exception as e:
                print(f"   ⚠️ LOG: Error processing {name}: {e}")

        # Filter for momentum sectors (Positive Velocity)
        df = pd.DataFrame(results).sort_values("prc", ascending=False)
        active_sectors = df[(df['p3'] > 0) & (df['p6'] > 0)]['name'].tolist()
        
        # --- CRITICAL HANDOFF ---
        # This saves the file that your Sniper is looking for
        with open('active_sectors.json', 'w') as f:
            json.dump(active_sectors, f)
        print(f"📦 [HANDOFF] Active Sectors saved: {active_sectors}")

        # Send Scout Report to Telegram
        msg = "📊 **SCOUT REPORT**\n\n`SECTOR         PRC   3M_%` \n"
        for _, r in df.iterrows():
            msg += f"`{r['name'].ljust(14)} {str(r['prc']).ljust(5)} {str(r['p3']).ljust(5)}` \n"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        
    except Exception as e:
        print(f"❌ CRITICAL SCOUT ERROR: {e}")

if __name__ == "__main__":
    run_agent()
