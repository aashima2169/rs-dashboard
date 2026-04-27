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
    "PSE (Govt)": "^CNXPSE", "Commodities": "^CNXCMDT", "Fin Service": "^CNXFIN"
}

def get_safe_close(df):
    if 'Adj Close' in df.columns: return df['Adj Close']
    return df['Close']

def run_agent():
    try:
        # Fetching more data (2y) to ensure 6M calculations are accurate
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
                
                # Momentum Calculations (21, 63, 126 trading days)
                m1 = round(((rs.iloc[-1] / rs.iloc[-21]) - 1) * 100, 1)
                m3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                m6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)
                
                # QUADRANT LOGIC (Based on 1M and 6M for long-term structure)
                if m1 > 0 and m6 > 0:
                    quadrant = "🚀 LEAD"
                elif m1 < 0 and m6 > 0:
                    quadrant = "⚠️ WEAK"
                elif m1 > 0 and m6 < 0:
                    quadrant = "📈 IMPROV"
                else:
                    quadrant = "😴 LAGG"

                results.append({
                    "name": name, "m1": m1, "m3": m3, "m6": m6, "quad": quadrant
                })
            except: continue

        df = pd.DataFrame(results).sort_values("m1", ascending=False)

        message = "🛡️ **INSTITUTIONAL RS STRATEGY**\n\n"
        # Adjusted header for mobile spacing
        message += "`SECTOR          1M   3M   6M   STATE` \n"
        message += "`------------------------------------` \n"
        
        for _, row in df.iterrows():
            name_p = row['name'].ljust(15)
            m1_p = str(row['m1']).ljust(4)
            m3_p = str(row['m3']).ljust(4)
            m6_p = str(row['m6']).ljust(4)
            message += f"`{name_p} {m1_p} {m3_p} {m6_p}` **{row['quad']}**\n"

        message += "\n**Logic:** 1M/3M/6M show % outperformance vs Nifty 50."
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_agent()
