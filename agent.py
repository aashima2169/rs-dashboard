import os
import requests
import pandas as pd
import subprocess
import sys
import time

# Auto-install yfinance
try:
    import yfinance as yf
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Cleaned Ticker List (Most Stable Tickers on Yahoo)
sectors = {
    "Bank Nifty": "^NSEBANK",
    "IT": "^CNXIT",
    "Pharma": "^CNXPHARMA",
    "FMCG": "^CNXFMCG",
    "Metal": "^CNXMETAL",
    "Auto": "^CNXAUTO",
    "Realty": "^CNXREALTY",
    "Energy": "^CNXENERGY",
    "Infra": "^CNXINFRA",
    "PSE (Govt)": "^CNXPSE",
    "Commodities": "^CNXCMDT",
    "Consumption": "^CNXCONSM", # Updated Ticker
    "Fin Service": "^CNXFIN"
}

def run_agent():
    # Fetch Benchmark (Nifty 50) first
    try:
        bm_data = yf.download("^NSEI", period="1y", progress=False)['Adj Close']
        if bm_data.empty:
            print("Error: Could not fetch Benchmark (^NSEI)")
            return
            
        confirmed = []
        others = []

        # Fetch each sector individually to prevent one fail from breaking others
        for name, ticker in sectors.items():
            try:
                s_data = yf.download(ticker, period="1y", progress=False)['Adj Close']
                if s_data.empty:
                    continue
                
                # Align data with Benchmark
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                
                # RS Ratio Calculation
                rs = combined['s'] / combined['b']
                
                # 1 Month momentum (~21 trading days)
                m_short = ((rs.iloc[-1] / rs.iloc[-21]) - 1) * 100
                # 3 Month momentum (~63 trading days)
                m_long = ((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100
                
                line = f"• {name}: 1M {round(m_short,1)}% | 3M {round(m_long,1)}%"
                
                if m_short > 0 and m_long > 0:
                    confirmed.append(line)
                else:
                    others.append(line)
                    
            except Exception as e:
                print(f"Skipping {name} due to error: {e}")
                continue

        # PREPARE TELEGRAM MESSAGE
        message = "🛡️ **WEEKLY SECTOR RS REPORT**\n\n"
        message += "🚀 **INSTITUTIONAL LEADERS** (Both +ve)\n" 
        message += ("\n".join(confirmed) if confirmed else "None")
        message += "\n\n😴 **LAGGARDS / SIDEWAYS**\n" 
        message += ("\n".join(others) if others else "None")
        
        # SEND TO TELEGRAM
        final_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(final_url, json=payload)
        print("Success: Telegram message sent.")

    except Exception as e:
        print(f"Critical System Error: {e}")

if __name__ == "__main__":
    run_agent()
