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

st.set_page_config(layout="wide", page_title="Reliable Sector Agent")

# MAPPING OFFICIAL INDICES
# I've added Defense/Power/Ancillary equivalents supported by YF
sectors = {
    "Energy & Power": "^CNXENERGY",
    "Auto (Includes Ancillaries)": "^CNXAUTO",
    "Infrastructure": "^CNXINFRA",
    "Real Estate": "^CNXREALTY",
    "PSE (Govt/Defense Themes)": "^CNXPSE",
    "FMCG": "^CNXFMCG",
    "Bank Nifty": "^NSEBANK",
    "PSU Bank": "^CNXPSUBANK",
    "IT Index": "^CNXIT",
    "Commodities": "^CNXCMDT",
    "Pharma": "^CNXPHARMA",
    "MNC Theme": "^CNXMNC",
    "Metal": "^CNXMETAL",
    "Services": "^CNXSERVICE",
    "Media": "^CNXMEDIA"
}

st.title("🛡️ Institutional RS Agent (Index Pure)")

@st.cache_data(ttl=3600)
def get_reliable_data():
    # Try Nifty 500 first, Fallback to Nifty 50 if it fails
    benchmarks = ["^CNX500", "^NSEI"]
    data_dict = {}
    
    # Get Benchmarks
    for b in benchmarks:
        try:
            temp = yf.download(b, period="1y", progress=False)['Adj Close']
            if not temp.empty:
                data_dict[b] = temp
        except:
            continue
            
    # Get Sectors
    for name, ticker in sectors.items():
        try:
            temp = yf.download(ticker, period="1y", progress=False)['Adj Close']
            if not temp.empty:
                data_dict[ticker] = temp
        except:
            continue
            
    return pd.DataFrame(data_dict)

try:
    df = get_reliable_data()
    
    # Determine which benchmark to use
    if "^CNX500" in df.columns and not df["^CNX500"].isnull().all():
        bm = "^CNX500"
        st.success("Using Nifty 500 Benchmark")
    elif "^NSEI" in df.columns:
        bm = "^NSEI"
        st.warning("Nifty 500 unavailable. Using Nifty 50 (Stable) as Benchmark.")
    else:
        st.error("No benchmark data available. Yahoo Finance might be down.")
        st.stop()
    
    results = []
    for name, ticker in sectors.items():
        if ticker in df.columns and ticker != bm:
            # RS Calculation
            rs_line = df[ticker] / df[bm]
            
            # Use safe offsets for 3M (63 days) and 6M (126 days)
            try:
                m3 = ((rs_line.iloc[-1] / rs_line.iloc[-63]) - 1) * 100
                m6 = ((rs_line.iloc[-1] / rs_line.iloc[-126]) - 1) * 100
                
                status = "✅ CONFIRMED" if (m3 > 0 and m6 > 0) else "❌ NO SIGNAL"
                
                results.append({
                    "Sector Index": name,
                    "3M RS %": round(m3, 2),
                    "6M RS %": round(m6, 2),
                    "Signal": status
                })
            except:
                continue

    final_df = pd.DataFrame(results).sort_values("3M RS %", ascending=False)

    st.table(final_df.style.applymap(
        lambda x: 'background-color: #1e4620; color: white' if x == "✅ CONFIRMED" else '',
        subset=['Signal']
    ))

except Exception as e:
    st.error(f"Critical System Error: {e}")
