import os
import requests
import pandas as pd
import subprocess
import sys
import json

# Ensure yfinance is installed
try:
    import yfinance as yf
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. LOAD CONFIGURATION
# This ensures you don't have to update this file when sectors change
CONFIG_PATH = "config.json"

if not os.path.exists(CONFIG_PATH):
    print(f"Error: {CONFIG_PATH} not found. Please create it first.")
    sys.exit(1)

with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

sectors = config.get("sectors", {})
custom_baskets = config.get("custom_baskets", {})

def get_safe_close(df):
    """Handles multi-index columns from yfinance 3.0+"""
    return df['Adj Close'] if 'Adj Close' in df.columns else df['Close']

def calc_percentile(series):
    """Calculates where the current value stands relative to the last year."""
    current = series.iloc[-1]
    return (series < current).mean() * 100

def run_agent():
    try:
        # Benchmark: Nifty 50 - Only 1 year of data needed for 3M & 6M RS
        bm_raw = yf.download("^NSEI", period="1y", progress=False)
        bm_data = get_safe_close(bm_raw)
        results = []

        # --- A. Process Standard Sectors ---
        for name, ticker in sectors.items():
            try:
                s_raw = yf.download(ticker, period="1y", progress=False)
                s_data = get_safe_close(s_raw)
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                rs = combined['s'] / combined['b']
                
                # Math: Percent Gain vs Percentile Rank
                # 3M = ~63 trading days, 6M = ~126 trading days
                p3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                p6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)
                r3 = round(calc_percentile(rs.pct_change(63).tail(252)))
                r6 = round(calc_percentile(rs.pct_change(126).tail(252)))
                
                results.append({
                    "name": name, "p3": p3, "p6": p6, 
                    "r3": r3, "r6": r6, "prc": round((r3+r6)/2)
                })
            except Exception as e:
                print(f"Skipping {name} due to error: {e}")
                continue

        # --- B. Process Custom Baskets (e.g., Railways) ---
        for basket_name, tickers in custom_baskets.items():
            try:
                # Average performance of the tickers in the basket
                basket_raw = yf.download(tickers, period="1y", progress=False)['Adj Close']
                basket_idx = basket_raw.mean(axis=1)
                comb_b = pd.concat([basket_idx, bm_data], axis=1).dropna()
                comb_b.columns = ['s', 'b']
                rs_b = comb_b['s'] / comb_b['b']
                
                p3_b = round(((rs_b.iloc[-1] / rs_b.iloc[-63]) - 1) * 100, 1)
                p6_b = round(((rs_b.iloc[-1] / rs_b.iloc[-126]) - 1) * 100, 1)
                r3_b = round(calc_percentile(rs_b.pct_change(63).tail(252)))
                r6_b = round(calc_percentile(rs_b.pct_change(126).tail(252)))
                
                results.append({
                    "name": basket_name, "p3": p3_b, "p6": p6_b, 
                    "r3": r3_b, "r6": r6_b, "prc": round((r3_b+r6_b)/2)
                })
            except Exception as e:
                print(f"Skipping basket {basket_name}: {e}")

        # --- C. Rank Results & Save Hand-off ---
        df = pd.DataFrame(results).sort_values("prc", ascending=False)

        # SAVE FOR AGENT 2: Only sectors where BOTH 3M & 6M RS > 10%
        active_sectors = df[(df['p3'] > 10) & (df['p6'] > 10)]['name'].tolist()
        with open('active_sectors.json', 'w') as f:
            json.dump(active_sectors, f)

        # --- D. Build Telegram Message with ALL sectors ---
        msg = "📊 **RANKING REPORT (R)**\n`SECTOR        3M_R  6M_R  PRC` \n`------------------------------` \n"
        for _, row in df.iterrows():
            msg += f"`{row['name'].ljust(12)} {str(row['r3']).ljust(5)} {str(row['r6']).ljust(5)} {str(row['prc']).ljust(3)}` \n"

        msg += "\n🚀 **VELOCITY REPORT (%)**\n`SECTOR        3M_%   6M_%` \n`---------------------------` \n"
        for _, row in df.iterrows():
            msg += f"`{row['name'].ljust(12)} {str(row['p3']).ljust(6)} {str(row['p6']).ljust(6)}` \n"

        # Deterministic Strategy Summary
        top = df.iloc[0]
        summary = f"\n💡 **STRATEGY SUMMARY**\n✅ **TOP LEAD:** {top['name']} (PRC {top['prc']})\n"
        
        improving = df[df['r3'] > (df['r6'] + 15)].head(1)
        if not improving.empty:
            summary += f"🔄 **REVERSAL:** {improving.iloc[0]['name']} is gaining momentum.\n"
        
        laggard = df.sort_values("prc").iloc[0]
        summary += f"🚫 **AVOID:** {laggard['name']} is underperforming.\n"

        # Show filtered sectors for Agent 2
        if active_sectors:
            summary += f"\n🎯 **SECTORS FOR SCREENING:** {', '.join(active_sectors)}\n"
        else:
            summary += f"\n🎯 **SECTORS FOR SCREENING:** None qualify (need 3M & 6M RS > 10%)\n"

        final_msg = msg + summary + "\n*R=Rank, %=Gain vs Nifty. Filtered sectors synced for Agent 2.*"
        
        # Send to Telegram
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": final_msg, "parse_mode": "Markdown"})
        
        print(f"Analysis complete. Active sectors for Sniper: {active_sectors}")
        
    except Exception as e:
        print(f"Error in run_agent: {e}")

if __name__ == "__main__":
    run_agent()
