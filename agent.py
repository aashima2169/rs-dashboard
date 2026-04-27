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
    "Fin Service": "^CNXFIN"
}

def get_safe_close(df):
    """Checks if 'Adj Close' exists, otherwise returns 'Close'"""
    if 'Adj Close' in df.columns:
        return df['Adj Close']
    return df['Close']

def run_agent():
    try:
        # Fetch Benchmark (Nifty 50)
        bm_raw = yf.download("^NSEI", period="1y", progress=False)
        if bm_raw.empty:
            print("Error: Could not fetch Benchmark")
            return
        
        bm_data = get_safe_close(bm_raw)
            
        confirmed = []
        others = []

        for name, ticker in sectors.items():
            try:
                s_raw = yf.download(ticker, period="1y", progress=False)
                if s_raw.empty: continue
                
                s_data = get_safe_close(s_raw)
                
                # Align data
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                
                # RS Ratio Calculation
                rs = combined['s'] / combined['b']
                
                # Momentum (1M = 21 days, 3M = 63 days)
                m_short = ((rs.iloc[-1] / rs.iloc[-21]) - 1) * 100
                m_long = ((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100
                
                line = f"• {name}: 1M {round(m_short,1)}% | 3M {round(m_long,1)}%"
                
                if m_short > 0 and m_long > 0:
                    confirmed.append(line)
                else:
                    others.append(line)
                    
            except Exception as e:
                print(f"Skipping {name}: {e}")
                continue

        # PREPARE TELEGRAM MESSAGE
        message = "🛡️ **WEEKLY SECTOR RS REPORT**\n\n"
        message += "🚀 **INSTITUTIONAL LEADERS**\n" 
        message += ("\n".join(confirmed) if confirmed else "None")
        message += "\n\n😴 **LAGGARDS / SIDEWAYS**\n" 
        message += ("\n".join(others) if others else "None")
        
        # SEND TO TELEGRAM
        final_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(final_url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
        print("Success! Message sent to Telegram.")

    except Exception as e:
        print(f"Critical System Error: {e}")

if __name__ == "__main__":
    run_agent()
