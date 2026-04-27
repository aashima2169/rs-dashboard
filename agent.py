import os
import time
import requests
import pandas as pd

# 1. SETUP SECRETS
API_KEY = os.environ.get("ALPHA_VANTAGE_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 2. THE EXHAUSTIVE LIST (14 Themes)
sectors = {
    "Power & Energy": "NSE:NIFTY_ENERGY",
    "Infrastructure": "NSE:NIFTY_INFRA",
    "Real Estate": "NSE:NIFTY_REALTY",
    "PSE (Govt/Defense)": "NSE:NIFTY_PSE",
    "Auto Index": "NSE:NIFTY_AUTO",
    "IT Services": "NSE:NIFTY_IT",
    "Pharma": "NSE:NIFTY_PHARMA",
    "FMCG": "NSE:NIFTY_FMCG",
    "Metal": "NSE:NIFTY_METAL",
    "Bank Nifty": "NSE:NIFTY_BANK",
    "PSU Bank": "NSE:NIFTY_PSU_BANK",
    "Commodities": "NSE:NIFTY_COMMODITIES",
    "Consumption": "NSE:NIFTY_CONSUMPTION",
    "Financial Services": "NSE:NIFTY_FIN_SERVICE"
}

def get_data(symbol):
    # Standardizing for 100 days of data (Compact) to save bandwidth
    url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&outputsize=compact&apikey={API_KEY}'
    try:
        r = requests.get(url)
        data = r.json()
        if "Time Series (Daily)" in data:
            df = pd.DataFrame.from_dict(data["Time Series (Daily)"], orient='index')
            return df['4. close'].astype(float).sort_index()
        return pd.Series()
    except:
        return pd.Series()

def run_agent():
    # Fetch Benchmark first (Nifty 500)
    bm = get_data("NSE:NIFTY_500")
    if bm.empty: 
        bm = get_data("NSE:NIFTY_50") # Fallback to Nifty 50
    
    if bm.empty:
        print("Error: Could not fetch benchmark. API key might be exhausted.")
        return

    confirmed = []
    others = []

    for name, sym in sectors.items():
        # Delay to stay under 5-calls-per-minute limit
        time.sleep(13) 
        s_data = get_data(sym)
        
        if not s_data.empty:
            # Align and calculate Relative Strength
            combined = pd.concat([s_data, bm], axis=1).dropna()
            combined.columns = ['s', 'b']
            rs = combined['s'] / combined['b']
            
            # Short term (1 month) vs Long term (~4 months available in compact)
            m_short = ((rs.iloc[-1] / rs.iloc[-21]) - 1) * 100
            m_long = ((rs.iloc[-1] / rs.iloc[0]) - 1) * 100
            
            line = f"• {name}: ST {round(m_short,1)}% | LT {round(m_long,1)}%"
            
            if m_short > 0 and m_long > 0:
                confirmed.append(line)
            else:
                others.append(line)

    # FORMAT TELEGRAM MESSAGE
    message = "🛡️ **WEEKLY SECTOR RS REPORT**\n\n"
    message += "🚀 **INSTITUTIONAL LEADERS**\n"
    message += "\n".join(confirmed) if confirmed else "None"
    message += "\n\n😴 **LAGGARDS/SIDEWAYS**\n"
    message += "\n".join(others) if others else "None"
    
    # SEND TO TELEGRAM
    final_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(final_url, json=payload)

if __name__ == "__main__":
    run_agent()
