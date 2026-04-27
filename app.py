import subprocess
import sys

# FORCE INSTALLATION IF MISSING
try:
    import yfinance as yf
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

import streamlit as st
import pandas as pd

st.set_page_config(layout="wide", page_title="Sector Confirmation")

# DEEP DRILL DOWN SECTORS
sectors = {
    "Power Proxies": "PFC.NS",
    "Defense": "BEL.NS",
    "Auto Ancillaries": "SONACOMS.NS",
    "Infrastructure": "^CNXINFRA",
    "Real Estate": "^CNXREALTY",
    "PSE": "^CNXPSE",
    "FMCG": "^CNXFMCG",
    "IT": "^CNXIT"
}

st.title("🛡️ Institutional RS Agent")

@st.cache_data(ttl=3600)
def get_data():
    tickers = list(sectors.values()) + ["^CNX500"]
    return yf.download(tickers, period="1y")['Adj Close']

try:
    df = get_data()
    bm = "^CNX500"
    
    results = []
    for name, ticker in sectors.items():
        if ticker in df.columns:
            rs_line = df[ticker] / df[bm]
            # 3M and 6M Logic
            m3 = ((rs_line.iloc[-1] / rs_line.iloc[-63]) - 1) * 100
            m6 = ((rs_line.iloc[-1] / rs_line.iloc[-126]) - 1) * 100
            
            signal = "✅ CONFIRMED" if m3 > 0 and m6 > 0 else "❌ NO SIGNAL"
            results.append({"Theme": name, "3M RS %": round(m3, 2), "6M RS %": round(m6, 2), "Signal": signal})

    final_df = pd.DataFrame(results).sort_values("3M RS %", ascending=False)
    st.table(final_df)
    
except Exception as e:
    st.error(f"Waiting for market data... Error: {e}")
