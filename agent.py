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
    "PSE": "^CNXPSE", "FinServ": "^CNXFIN", "Service": "^CNXSERVICE"
}

def get_safe_close(df):
    return df['Adj Close'] if 'Adj Close' in df.columns else df['Close']

def calc_percentile(series):
    """Calculates the percentile rank of the last value in a series"""
    current = series.iloc[-1]
    return (series < current).mean() * 100

def run_agent():
    try:
        # Fetching 2.5 years of data to have enough room for 12M lookback + Percentile history
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
                
                # Calculate Rolling Momentum for the last 252 days to find the Percentile Rank
                # 3 Month (63 days), 6 Month (126 days), 12 Month (252 days)
                m3_series = rs.pct_change(63)
                m6_series = rs.pct_change(126)
                m12_series = rs.pct_change(252)
                
                # Final Percentile Scores (0-100)
                # Comparing today's 3M momentum against the last 252 days of 3M momentum
                m3_prc = round(calc_percentile(m3_series.tail(252)))
                m6_prc = round(calc_percentile(m6_series.tail(252)))
                m12_prc = round(calc_percentile(m12_series.tail(252)))
                
                # Average Percentile (The final PRC score)
                total_prc = round((m3_prc + m6_prc + m12_prc) / 3)

                results.append({
                    "name": name, "m3": m3_prc, "m6": m6_prc, "m12": m12_prc, "prc": total_prc
                })
            except: continue

        df = pd.DataFrame(results).sort_values("prc", ascending=False)

        message = "🛡️ **PRO RS SCANNER (ALL PERCENTILES)**\n\n"
        message += "`SECTOR          3M   6M   12M  PRC` \n"
        message += "`----------------------------------` \n"
        
        for _, row in df.iterrows():
            n = row['name'].ljust(13)
            r3 = str(row['m3']).ljust(4)
            r6 = str(row['m6']).ljust(4)
            r12 = str(row['m12']).ljust(4)
            rp = str(row['prc']).ljust(3)
            message += f"`{n} {r3} {r6} {r12} {rp}`\n"

        message += "\n**Note:** All values are Percentile Ranks (0-100).\n90+ = Extremely Strong vs History."
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_agent()
