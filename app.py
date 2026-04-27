import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="Deep Sector RS", layout="centered")
st.title("🛡️ Institutional RS Confirmation")

# Sector Proxies mapped to Nifty 500
sectors = {
    "Power Proxies": "^CNXENERGY",
    "Defense": "BEL.NS", 
    "Auto Ancillaries": "SONACOMS.NS", 
    "Infrastructure": "^CNXINFRA",
    "Real Estate": "^CNXREALTY",
    "Govt Enterprises": "^CNXPSE",
    "FMCG / Consumption": "^CNXFMCG"
}

@st.cache_data(ttl=3600)
def fetch_data():
    tickers = list(sectors.values()) + ["^CNX500"]
    return yf.download(tickers, period="1y")['Adj Close']

df = fetch_data()
bm = "^CNX500"

results = []
for name, ticker in sectors.items():
    rs_line = df[ticker] / df[bm]
    m3 = ((rs_line.iloc[-1] / rs_line.iloc[-63]) - 1) * 100
    m6 = ((rs_line.iloc[-1] / rs_line.iloc[-126]) - 1) * 100
    
    signal = "✅ CONFIRMED" if m3 > 0 and m6 > 0 else "❌ WAIT"
    results.append({"Sector": name, "3M RS %": round(m3, 2), "6M RS %": round(m6, 2), "Status": signal})

final_df = pd.DataFrame(results).sort_values("3M RS %", ascending=False)

st.dataframe(final_df.style.applymap(
    lambda x: 'background-color: #006400; color: white' if x == "✅ CONFIRMED" else '', 
    subset=['Status']
), use_container_width=True)

st.write("Target stocks in ✅ sectors on TradingView for VCP / High-Tight Flag setups.")
