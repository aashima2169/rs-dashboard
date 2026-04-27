import subprocess
import sys
import time

# Auto-install requests if missing
try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests
import pandas as pd

import os
import streamlit as st

# This handles both Streamlit Secrets and GitHub Secrets
if "ALPHA_VANTAGE_KEY" in st.secrets:
    API_KEY = st.secrets["ALPHA_VANTAGE_KEY"]
else:
    API_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "YOUR_LOCAL_KEY_HERE")
BENCHMARK = "NSE:NIFTY_500"

# Mapping for Alpha Vantage (Format is EXCHANGE:SYMBOL)
# Note: Alpha Vantage free tier coverage for India is best on major indices
sectors = {
    "Power & Energy": "NSE:NIFTY_ENERGY",
    "Infrastructure": "NSE:NIFTY_INFRA",
    "Real Estate": "NSE:NIFTY_REALTY",
    "PSE (Govt/Defense)": "NSE:NIFTY_PSE",
    "Auto Index": "NSE:NIFTY_AUTO",
    "IT Index": "NSE:NIFTY_IT",
    "Pharma": "NSE:NIFTY_PHARMA",
    "FMCG": "NSE:NIFTY_FMCG",
    "Metal": "NSE:NIFTY_METAL",
    "Fin Services": "NSE:NIFTY_FIN_SERVICE",
    "Media": "NSE:NIFTY_MEDIA",
    "Bank Nifty": "NSE:NIFTY_BANK",
    "Commodities": "NSE:NIFTY_COMMODITIES",
    "Consumption": "NSE:NIFTY_CONSUMPTION"
}
st.title("🚀 Alpha Vantage Sector Agent")
st.write("Using stable API connection for Institutional RS Confirmation.")

def get_alpha_data(symbol):
    url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&outputsize=full&apikey={API_KEY}'
    r = requests.get(url)
    data = r.json()
    
    if "Time Series (Daily)" in data:
        # Convert to DataFrame
        df = pd.DataFrame.from_dict(data["Time Series (Daily)"], orient='index')
        df.index = pd.to_datetime(df.index)
        return df['4. close'].astype(float).sort_index()
    else:
        return pd.Series()

# MAIN EXECUTION
try:
    # 1. Fetch Benchmark
    with st.spinner('Fetching Benchmark Data...'):
        bm_series = get_alpha_data(BENCHMARK)
        # If Nifty 500 fails, fallback to Nifty 50
        if bm_series.empty:
            bm_series = get_alpha_data("NSE:NIFTY_50")
            st.warning("Nifty 500 not found, using Nifty 50.")
    
    if bm_series.empty:
        st.error("API Limit reached or Key invalid. Alpha Vantage allows 25 calls/day.")
        st.stop()

    results = []
    
    # 2. Fetch Sectors (With a small delay to avoid API spamming)
    for name, symbol in sectors.items():
        with st.spinner(f'Analyzing {name}...'):
            s_series = get_alpha_data(symbol)
            if not s_series.empty:
                # Align data
                combined = pd.concat([s_series, bm_series], axis=1).dropna()
                combined.columns = ['sector', 'benchmark']
                
                # Calculate RS Ratio
                rs_line = combined['sector'] / combined['benchmark']
                
                # 3M and 6M Momentum
                m3 = ((rs_line.iloc[-1] / rs_line.iloc[-63]) - 1) * 100
                m6 = ((rs_line.iloc[-1] / rs_line.iloc[-126]) - 1) * 100
                
                status = "✅ CONFIRMED" if (m3 > 0 and m6 > 0) else "❌ NO SIGNAL"
                
                results.append({
                    "Sector": name,
                    "3M RS %": round(m3, 2),
                    "6M RS %": round(m6, 2),
                    "Signal": status
                })
                # Alpha Vantage free tier needs a tiny gap between calls
                time.sleep(0.5)

    final_df = pd.DataFrame(results).sort_values("3M RS %", ascending=False)
    st.table(final_df.style.applymap(
        lambda x: 'background-color: #1e4620; color: white' if x == "✅ CONFIRMED" else '',
        subset=['Signal']
    ))

except Exception as e:
    st.error(f"System Error: {e}")
