import os
import requests
import pandas as pd
import json
import yfinance as yf

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_safe_close(df):
    """Handles multi-index columns and flattens data"""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df['Close'].dropna()

def calc_percentile(series):
    """Calculates where the current value stands relative to the last year"""
    if series.empty: return 0
    current = series.iloc[-1]
    return (series < current).mean() * 100

def run_agent():
    print("📊 SCOUT AGENT STARTED...")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        sector_tickers = config.get("sectors", {})
        # Benchmark: Nifty 50 for Relative Strength calculation
        bm_raw = yf.download("^NSEI", period="1y", progress=False)
        bm_data = get_safe_close(bm_raw)
        
        results = []

        for name, ticker in sector_tickers.items():
            try:
                print(f"🔍 Analyzing Sector: {name} ({ticker})")
                s_raw = yf.download(ticker, period="1y", progress=False)
                s_data = get_safe_close(s_raw)
                
                if s_data.empty or len(s_data) < 126:
                    print(f"⚠️ Data incomplete for {name}")
                    continue

                # Align Sector data with Nifty Benchmark
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                
                # RS Line = Sector Price / Benchmark Price
                rs = combined['s'] / combined['b']
                
                # --- PERCENTAGE CALCULATION (Velocity) ---
                # How much the RS line has grown in % over 3M (63 days) and 6M (126 days)
                p3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                p6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)
                
                # --- PERCENTILE CALCULATION (Rank) ---
                # How the current RS strength compares to the last 252 trading days
                r3 = round(calc_percentile(rs.pct_change(63).tail(252)))
                r6 = round(calc_percentile(rs.pct_change(126).tail(252)))
                
                results.append({
                    "name": name, 
                    "p3": p3, "p6": p6, 
                    "r3": r3, "r6": r6, 
                    "prc": round((r3+r6)/2)
                })
            except Exception as e:
                print(f"⚠️ Error on {name}: {e}")

        # Filter for Sniper: Must have positive momentum (Percentage > 0)
        df = pd.DataFrame(results).sort_values("prc", ascending=False)
        active_sectors = df[(df['p3'] > 0) & (df['p6'] > 0)]['name'].tolist()
        
        with open('active_sectors.json', 'w') as f:
            json.dump(active_sectors, f)

        # --- TELEGRAM REPORT ---
        # A. Ranking Report (Percentile)
        msg = "📊 **SCOUT REPORT - SECTOR RANKINGS**\n\n"
        msg += "`SECTOR         3M_R  6M_R  PRC` \n"
        msg += "`------------------------------` \n"
        for _, row in df.iterrows():
            msg += f"`{row['name'].ljust(14)} {str(row['r3']).ljust(5)} {str(row['r6']).ljust(5)} {str(row['prc']).ljust(3)}` \n"

        # B. Velocity Report (Percentage)
        msg += "\n🚀 **VELOCITY REPORT (%)**\n"
        msg += "`SECTOR         3M_%    6M_%` \n"
        msg += "`---------------------------` \n"
        for _, row in df.iterrows():
            msg += f"`{row['name'].ljust(14)} {str(row['p3']).ljust(7)} {str(row['p6']).ljust(7)}` \n"

        # Summary
        top = df.iloc[0]
        msg += f"\n💡 **TOP LEAD:** {top['name']} (PRC {top['prc']})"
        msg += f"\n🎯 **SNIPER TARGETS:** {', '.join(active_sectors)}"

        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        
        print(f"✅ SCOUT COMPLETED. {len(active_sectors)} sectors sent to Sniper.")

    except Exception as e:
        print(f"❌ Critical Error: {e}")

if __name__ == "__main__":
    run_agent()
