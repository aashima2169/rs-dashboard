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
    "Bank Nifty": "^NSEBANK", "IT": "^CNXIT", "Pharma": "^CNXPHARMA",
    "FMCG": "^CNXFMCG", "Metal": "^CNXMETAL", "Auto": "^CNXAUTO",
    "Realty": "^CNXREALTY", "Energy": "^CNXENERGY", "Infra": "^CNXINFRA",
    "PSE (Govt)": "^CNXPSE", "Fin Service": "^CNXFIN"
}

def get_safe_close(df):
    return df['Adj Close'] if 'Adj Close' in df.columns else df['Close']

def run_agent():
    try:
        # Fetch 2y data for 12M (252 trading days) calculation
        bm_raw = yf.download("^NSEI", period="2y", progress=False)
        bm_data = get_safe_close(bm_raw)
            
        results = []

        for name, ticker in sectors.items():
            try:
                s_raw = yf.download(ticker, period="2y", progress=False)
                if s_raw.empty: continue
                s_data = get_safe_close(s_raw)
                
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                rs = combined['s'] / combined['b']
                
                # 1. MOMENTUM SCORES (Raw Numbers)
                m3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                m6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)
                m12 = round(((rs.iloc[-1] / rs.iloc[-252]) - 1) * 100, 1)
                
                # 2. RS PERCENTILE (Matches PRC in your screenshot)
                current_rs = rs.iloc[-1]
                rs_history = rs.tail(252)
                percentile = round((rs_history < current_rs).mean() * 100)

                # 3. STATE LOGIC
                if percentile > 80: state = "🚀 LEAD"
                elif percentile > 50: state = "📈 IMPR"
                else: state = "😴 LAGG"

                results.append({
                    "name": name, "m3": m3, "m6": m6, "m12": m12, 
                    "prc": percentile, "state": state
                })
            except: continue

        # Sort by PRC (Highest Percentile)
        df = pd.DataFrame(results).sort_values("prc", ascending=False)

        message = "🛡️ **PRO RS SCANNER**\n\n"
        message += "`SECTOR          3M   6M   12M  PRC ` \n"
        message += "`------------------------------------` \n"
        
        for _, row in df.iterrows():
            # Formatting strings to maintain table structure without % signs
            name_p = row['name'].ljust(15)
            m3_p = str(row['m3']).ljust(4)
            m6_p = str(row['m6']).ljust(4)
            m12_p = str(row['m12']).ljust(4)
            prc_p = str(row['prc']).ljust(4)
            
            message += f"`{name_p} {m3_p} {m6_p} {m12_p} {prc_p}` **{row['state']}**\n"

        message += "\n**PRC:** RS Percentile (0-100 scale)\n**3/6/12M:** Relative Momentum vs Nifty"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_agent()
