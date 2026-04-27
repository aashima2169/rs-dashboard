import subprocess
import sys

# FORCE INSTALLATION
try:
    import yfinance as yf
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

import streamlit as st
import pandas as pd

st.set_page_config(layout="wide", page_title="Pure Sector Index Agent")

# MAPPING ONLY OFFICIAL INDICES
sectors = {
    "Nifty 500 (BM)": "^CNX500",
    "Energy & Power": "^CNXENERGY",
    "Auto": "^CNXAUTO",
    "Infrastructure": "^CNXINFRA",
    "Real Estate": "^CNXREALTY",
    "PSE (Govt Stocks)": "^CNXPSE",
    "FMCG": "^CNXFMCG",
    "Bank Nifty": "^NSEBANK",
    "PSU Bank": "^CNXPSUBANK",
    "IT Index": "^CNXIT",
    "Commodities": "^CNXCMDT",
    "Pharma": "^CNXPHARMA",
    "MNC Theme": "^CNXMNC",
    "Financial Services": "^CNXFIN",
    "Metal": "^CNXMETAL"
}

st.title("📊 Pure Sector Index RS Agent")

@st.cache_data(ttl=3600)
def get_index_data():
    # Fetching individually to prevent batch download errors
    data_dict = {}
    for name, ticker in sectors.items():
        try:
            df = yf.download(ticker, period="1y", progress=False)['Adj Close']
            if not df.empty:
                data_dict[ticker] = df
        except:
            continue
    return pd.DataFrame(data_dict)

try:
    df = get_index_data()
    bm = "^CNX500"
    
    if bm not in df.columns:
        st.error("Benchmark Nifty 500 data unavailable. Check connection.")
    else:
        results = []
        for name, ticker in sectors.items():
            if ticker == bm or ticker not in df.columns:
                continue
            
            # RS Ratio Calculation
            rs_line = df[ticker] / df[bm]
            
            # 3M and 6M momentum
            try:
                m3 = ((rs_line.iloc[-1] / rs_line.iloc[-63]) - 1) * 100
                m6 = ((rs_line.iloc[-1] / rs_line.iloc[-126]) - 1) * 100
                
                signal = "✅ CONFIRMED" if (m3 > 0 and m6 > 0) else "❌ NO SIGNAL"
                
                results.append({
                    "Index": name,
                    "3M RS %": round(m3, 2),
                    "6M RS %": round(m6, 2),
                    "Signal": signal
                })
            except:
                continue

        final_df = pd.DataFrame(results).sort_values("3M RS %", ascending=False)

        def color_signal(val):
            return 'background-color: #1e4620; color: white' if val == "✅ CONFIRMED" else ''

        st.table(final_df.style.applymap(color_signal, subset=['Signal']))

except Exception as e:
    st.error(f"Error fetching Index data: {e}")
