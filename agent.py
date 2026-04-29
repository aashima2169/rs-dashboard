import os
import requests
import pandas as pd
import json
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
    print("📊 SCOUT AGENT STARTED...")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        # Use the 'sectors' dictionary for Yahoo tickers
        sector_tickers = config.get("sectors", {})
        bm_raw = yf.download("^NSEI", period="1y", progress=False)
        bm_data = get_safe_close(bm_raw)
        
        results = []

        for name, ticker in sector_tickers.items():
            try:
                print(f"🔍 Analyzing Sector: {name} ({ticker})")
                
                # Fetch data with Session to avoid 404s
                s_raw = yf.download(ticker, period="1y", progress=False)
                s_data = get_safe_close(s_raw)
                
                if s_data.empty or len(s_data) < 126:
                    print(f"⚠️ Data incomplete for {name}")
                    continue

                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                rs = combined['s'] / combined['b']
                
                # Calculate RS Metrics
                p3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                p6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)
                r3 = round(calc_percentile(rs.pct_change(63).tail(252)))
                r6 = round(calc_percentile(rs.pct_change(126).tail(252)))
                
                results.append({
                    "name": name, "p3": p3, "p6": p6, 
                    "r3": r3, "r6": r6, "prc": round((r3+r6)/2)
                })
            except Exception as e:
                print(f"⚠️ Error on {name}: {e}")

        # Filter: 3M and 6M RS must be positive
        df = pd.DataFrame(results).sort_values("prc", ascending=False)
        active_sectors = df[(df['p3'] > 0) & (df['p6'] > 0)]['name'].tolist()
        
        with open('active_sectors.json', 'w') as f:
            json.dump(active_sectors, f)

        # Telegram Message
        msg = "📊 **SCOUT REPORT**\n\n`SECTOR         3M_RS  6M_RS  PRC` \n"
        for _, row in df.iterrows():
            msg += f"`{row['name'].ljust(14)} {str(row['p3']).ljust(6)} {str(row['p6']).ljust(6)} {str(row['prc']).ljust(3)}` \n"

        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        print(f"✅ SCOUT COMPLETED. Active: {active_sectors}")

    except Exception as e:
        print(f"❌ Critical Error: {e}")

if __name__ == "__main__":
    run_agent()
