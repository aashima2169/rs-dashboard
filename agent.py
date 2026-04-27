import os
import requests
import pandas as pd
import subprocess
import sys

# Auto-install yfinance
try:
    import yfinance as yf
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Tickers that are highly stable on Yahoo
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
    "Consumption": "^CNXCONSUMPTION",
    "Fin Service": "^CNXFIN"
}

def run_agent():
    # Use Nifty 50 as Benchmark
    try:
        # Download data for all sectors + benchmark in one go
        tickers = list(sectors.values()) + ["^NSEI"]
        data = yf.download(tickers, period="1y")['Adj Close']
        
        if "^NSEI" not in data.columns:
            print("Error: Benchmark data not found.")
            return

        bm = data["^NSEI"]
        confirmed = []
        others = []

        for name, ticker in sectors.items():
            if ticker in data.columns:
                # Calculate RS Ratio
                rs = data[ticker] / bm
                
                # 1 Month momentum (approx 21 trading days)
                m_short = ((rs.iloc[-1] / rs.iloc[-21]) - 1) * 100
                # 3 Month momentum (approx 63 trading days)
                m_long = ((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100
                
                line = f"• {name}: 1M {round(m_short,1)}% | 3M {round(m_long,1)}%"
                
                if m_short > 0 and m_long > 0:
                    confirmed.append(line)
                else:
                    others.append(line)

        # PREPARE TELEGRAM MESSAGE
        message = "🛡️ **WEEKLY SECTOR RS REPORT**\n\n"
        message += "🚀 **INSTITUTIONAL LEADERS**\n" 
        message += ("\n".join(confirmed) if confirmed else "None")
        message += "\n\n😴 **LAGGARDS / SIDEWAYS**\n" 
        message += ("\n".join(others) if others else "None")
        
        # SEND TO TELEGRAM
        final_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        requests.post(final_url, json=payload)
        print("Report sent to Telegram successfully!")
        
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    run_agent()
