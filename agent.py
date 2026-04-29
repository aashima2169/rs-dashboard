import os
import requests
import pandas as pd
import json
import yfinance as yf
import sys

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_safe_close(df):
    """Handles multi-index columns from yfinance 3.0+"""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df['Close'].dropna()

def calc_percentile(series):
    """Calculates where the current value stands relative to the last year."""
    current = series.iloc[-1]
    return (series < current).mean() * 100

def run_agent():
    try:
        print("📊 SCOUT AGENT STARTED...")
        
        if not os.path.exists('config.json'):
            print("Error: config.json not found.")
            return

        with open('config.json', 'r') as f:
            config = json.load(f)
        
        sector_map = config.get("sectors", {})
        
        # Benchmark: Nifty 50
        bm_raw = yf.download("^NSEI", period="1y", progress=False)
        bm_data = get_safe_close(bm_raw)
        
        results = []

        # --- A. Process Sectors ---
        for name, identifiers in sector_map.items():
            try:
                # identifiers[0] is the Yahoo Ticker (e.g., ^CNXMETAL)
                ticker = identifiers[0]
                print(f"🔍 Analyzing Sector: {name} ({ticker})")
                
                s_raw = yf.download(ticker, period="1y", progress=False)
                s_data = get_safe_close(s_raw)
                
                # Align data
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                rs = combined['s'] / combined['b']
                
                # Calculate 3M (63 days) and 6M (126 days) Relative Strength
                p3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                p6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)
                
                # Percentile Rank (PRC)
                r3 = round(calc_percentile(rs.pct_change(63).tail(252)))
                r6 = round(calc_percentile(rs.pct_change(126).tail(252)))
                
                results.append({
                    "name": name, "p3": p3, "p6": p6, 
                    "r3": r3, "r6": r6, "prc": round((r3+r6)/2)
                })
            except Exception as e:
                print(f"⚠️ Skipping {name}: {e}")

        # --- B. Rank and Filter ---
        df = pd.DataFrame(results).sort_values("prc", ascending=False)

        # Sniper logic: Only sectors with positive 3M and 6M RS
        active_sectors = df[(df['p3'] > 0) & (df['p6'] > 0)]['name'].tolist()
        
        # Merge with "Always Scan" from config
        final_scan_list = list(set(active_sectors + config.get("always_scan", [])))

        with open('active_sectors.json', 'w') as f:
            json.dump(final_scan_list, f)

        # --- C. Telegram Report ---
        msg = "📊 **SCOUT REPORT - SECTOR RS RANKINGS**\n\n"
        msg += "`SECTOR         3M_RS  6M_RS  PRC` \n"
        msg += "`--------------------------------` \n"
        for _, row in df.iterrows():
            msg += f"`{row['name'].ljust(14)} {str(row['p3']).ljust(6)} {str(row['p6']).ljust(6)} {str(row['prc']).ljust(3)}` \n"

        top = df.iloc[0]['name']
        msg += f"\n💡 **TOP LEAD:** {top}\n"
        msg += f"🎯 **FOR SNIPER:** {', '.join(final_scan_list)}"

        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        
        print(f"✅ SCOUT COMPLETED. {len(final_scan_list)} sectors passed to Sniper.")

    except Exception as e:
        print(f"❌ Critical Error: {e}")

if __name__ == "__main__":
    run_agent()
