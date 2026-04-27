import os
import time
import subprocess
import sys
import streamlit as st
import pandas as pd

# Auto-install requests
try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

st.set_page_config(layout="wide", page_title="Full Sector Agent")

# 1. API KEY LOGIC
if "ALPHA_VANTAGE_KEY" in st.secrets:
    API_KEY = st.secrets["ALPHA_VANTAGE_KEY"]
else:
    API_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "YOUR_KEY_HERE")

# 2. COMPREHENSIVE SECTOR LIST (Verified Tickers)
sectors = {
    "Energy & Power": "NSE:NIFTY_ENERGY",
    "Infrastructure": "NSE:NIFTY_INFRA",
    "Real Estate": "NSE:NIFTY_REALTY",
    "PSE (Govt Stocks)": "NSE:NIFTY_PSE",
    "Auto Index": "NSE:NIFTY_AUTO",
    "IT Index": "NSE:NIFTY_IT",
    "Pharma": "NSE:NIFTY_PHARMA",
    "FMCG": "NSE:NIFTY_FMCG",
    "Metal": "NSE:NIFTY_METAL",
    "Bank Nifty": "NSE:NIFTY_BANK"
}
BENCHMARK = "NSE:NIFTY_500"

st.title("🚀 Institutional RS Agent")

def get_alpha_data(symbol):
    url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&outputsize=compact&apikey={API_KEY}'
    response = requests.get(url)
    data = response.json()
    
    if "Time Series (Daily)" in data:
        df = pd.DataFrame.from_dict(data["Time Series (Daily)"], orient='index')
        df.index = pd.to_datetime(df.index)
        return df['4. close'].astype(float).sort_index()
    elif "Note" in data:
        st.warning(f"API Rate Limit Hit (5 calls/min). Waiting 60 seconds...")
        time.sleep(60) # Wait and try once more
        return get_alpha_data(symbol)
    else:
        return pd.Series()

# 3. ANALYSIS
try:
    with st.spinner("Analyzing Market Flow..."):
        # Fetch Benchmark
        bm_series = get_alpha_data(BENCHMARK)
        if bm_series.empty:
            bm_series = get_alpha_data("NSE:NIFTY_50") # Fallback
        
        results = []
        for name, sym in sectors.items():
            s_series = get_alpha_data(sym)
            if not s_series.empty and not bm_series.empty:
                # Align dates
                combined = pd.concat([s_series, bm_series], axis=1).dropna()
                combined.columns = ['sector', 'benchmark']
                
                # RS Math
                rs_line = combined['sector'] / combined['benchmark']
                
                # We use -1 (latest) and -20 (approx 1 month ago) for 3M/6M if compact data
                # Since compact only gives 100 days, let's use what's available
                m_short = ((rs_line.iloc[-1] / rs_line.iloc[-20]) - 1) * 100
                m_long = ((rs_line.iloc[-1] / rs_line.iloc[0]) - 1) * 100
                
                signal = "✅ CONFIRMED" if m_short > 0 and m_long > 0 else "❌ NO SIGNAL"
                
                results.append({
                    "Theme": name,
                    "Short-Term RS %": round(m_short, 2),
                    "Long-Term RS %": round(m_long, 2),
                    "Signal": signal
                })
                # Mandatory delay for free tier
                time.sleep(12) 

        if results:
            final_df = pd.DataFrame(results).sort_values("Short-Term RS %", ascending=False)
            st.table(final_df.style.applymap(
                lambda x: 'background-color: #1e4620; color: white' if x == "✅ CONFIRMED" else '',
                subset=['Signal']
            ))
        else:
            st.info("API Limit reached for now. Try again in 1 minute.")

except Exception as e:
    st.error(f"Waiting for API sync... ({e})")
