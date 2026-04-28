import os
import requests
import pandas as pd
import subprocess
import sys
import json  # To pass data to Agent 2

try:
    import yfinance as yf
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

sectors = {
    "Power": "^CNXENERGY", "PSE": "^CNXPSE", "CPSE": "^CNXCPSE",
    "BankNifty": "^NSEBANK", "NiftyIT": "^CNXIT", "Pharma": "^CNXPHARMA",
    "FMCG": "^CNXFMCG", "Metal": "^CNXMETAL", "Auto": "^CNXAUTO",
    "Realty": "^CNXREALTY", "Infra": "^CNXINFRA"
}
rail_tickers = ["IRFC.NS", "RVNL.NS", "IRCON.NS", "RITES.NS"]

def get_safe_close(df):
    return df['Adj Close'] if 'Adj Close' in df.columns else df['Close']

def calc_percentile(series):
    current = series.iloc[-1]
    return (series < current).mean() * 100

def run_agent():
    try:
        bm_raw = yf.download("^NSEI", period="3y", progress=False)
        bm_data = get_safe_close(bm_raw)
        results = []

        # Process Official Sectors
        for name, ticker in sectors.items():
            try:
                s_raw = yf.download(ticker, period="3y", progress=False)
                s_data = get_safe_close(s_raw)
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                rs = combined['s'] / combined['b']
                
                p3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                p6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)
                r3 = round(calc_percentile(rs.pct_change(63).tail(252)))
                r6 = round(calc_percentile(rs.pct_change(126).tail(252)))
                results.append({"name": name, "p3": p3, "p6": p6, "r3": r3, "r6": r6, "prc": round((r3+r6)/2)})
            except: continue

        # Process Railways
        try:
            rail_raw = yf.download(rail_tickers, period="3y", progress=False)['Adj Close']
            rail_idx = rail_raw.mean(axis=1)
            comb_r = pd.concat([rail_idx, bm_data], axis=1).dropna()
            comb_r.columns = ['s', 'b']
            rs_r = comb_r['s'] / comb_r['b']
            p3_r = round(((rs_r.iloc[-1] / rs_r.iloc[-63]) - 1) * 100, 1)
            p6_r = round(((rs_r.iloc[-1] / rs_r.iloc[-126]) - 1) * 100, 1)
            r3_r = round(calc_percentile(rs_r.pct_change(63).tail(
