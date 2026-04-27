import os
import requests
import pandas as pd
import subprocess
import sys

try:
    import yfinance as yf
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

sectors = {
    "BankNifty": "^NSEBANK", "NiftyIT": "^CNXIT", "Pharma": "^CNXPHARMA",
    "FMCG": "^CNXFMCG", "Metal": "^CNXMETAL", "Auto": "^CNXAUTO",
    "Realty": "^CNXREALTY", "Energy": "^CNXENERGY", "Infra": "^CNXINFRA",
    "PSE": "^CNXPSE", "FinServ": "^CNXFIN"
}

def get_safe_close(df):
    return df['Adj Close'] if 'Adj Close' in df.columns else df['Close']

def calc_percentile(series):
    current = series.iloc[-1]
    return (series < current).mean() * 100

def run_agent():
    try:
        bm_raw = yf.download("^NSEI", period="3y", progress=False)
        bm_data = get_safe_close(bm_raw)
        results = []

        for name, ticker in sectors.items():
            try:
                s_raw = yf.download(ticker, period="3y", progress=False)
                if s_raw.empty: continue
                s_data = get_safe_close(s_raw)
                
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                rs = combined['s'] / combined['b']
                
                # --- CALCULATE % PERFORMANCE ---
                pct3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                pct6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)

                # --- CALCULATE PERCENTILE RANK (R) ---
                m3_series = rs.pct_change(63)
                m6_series = rs.pct_change(126)
                r3 = round(calc_percentile(m3_series.tail(252)))
                r6 = round(calc_percentile(m6_series.tail(252)))
                
                # Master Score (PRC)
                prc = round((r3 + r6) / 2)

                results.append({
                    "name": name, "p3": pct3, "r3": r3, "p6": pct6, "r6": r6, "prc": prc
                })
            except: continue

        df = pd.DataFrame(results).sort_values("prc", ascending=False)

        # Message 1: Percentile Focus (The Rank)
        msg_prc = "📊 **RANKING REPORT (Percentiles)**\n"
        msg_prc += "`SECTOR         3M_R  6M_R  PRC` \n"
        msg_prc += "`------------------------------` \n"
        for _, row in df.iterrows():
            msg_prc += f"`{row['name'].ljust(12)} {str(row['r3']).ljust(5)} {str(row['r6']).ljust(5)} {str(row['prc']).ljust(3)}` \n"

        # Message 2: Momentum Focus (The Raw %)
        msg_pct = "\n🚀 **VELOCITY REPORT (Raw %)**\n"
        msg_pct += "`SECTOR         3M_%   6M_%` \n"
        msg_pct += "`---------------------------` \n"
        for _, row in df.iterrows():
            msg_pct += f"`{row['name'].ljust(12)} {str(row['p3']).ljust(6)} {str(row['p6']).ljust(6)}` \n"

        final_msg = msg_prc + msg_pct + "\n*Note: R = Rank (0-100), % = Gain vs Nifty*"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": final_msg, "parse_mode": "Markdown"})
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_agent()
