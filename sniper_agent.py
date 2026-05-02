import os
import json
import time
import warnings
import logging
from collections import defaultdict

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.simplefilter(action="ignore", category=FutureWarning)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger()

CFG = {
    "top_n": 30,
    "sleep": 0.03,
}

# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────
def download(ticker):
    try:
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=True)
        if df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df.dropna()
    except:
        return None


def get_stocks(sector):
    try:
        with open("config.json") as f:
            cfg = json.load(f)

        name = cfg["nse_index_mapping"].get(sector)
        if not name:
            return []

        session = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0"}

        session.get("https://www.nseindia.com", headers=headers)

        url = f"https://www.nseindia.com/api/equity-stockIndices?index={name.replace(' ', '%20')}"
        res = session.get(url, headers=headers)

        return [
            f"{x['symbol']}.NS"
            for x in res.json()["data"]
            if x["symbol"] != name
        ]

    except:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def compute_rs(stock_df, nifty_df):
    try:
        s_ret = stock_df["Close"].pct_change(100).iloc[-1]
        n_ret = nifty_df["Close"].pct_change(100).iloc[-1]
        return (1 + s_ret) / (1 + n_ret)
    except:
        return 1


def find_swings(series, window=5):
    highs, lows = [], []

    for i in range(window, len(series) - window):
        chunk = series[i - window:i + window]

        if series[i] == chunk.max():
            highs.append(series[i])

        if series[i] == chunk.min():
            lows.append(series[i])

    return highs, lows


# ─────────────────────────────────────────────────────────────────────────────
# SCORING ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def score_stock(ticker, sector, nifty_df):
    df = download(ticker)
    if df is None or len(df) < 200:
        return None

    close = df["Close"]
    volume = df["Volume"]

    score = 0

    # ── RS SCORE (0–20)
    rs = compute_rs(df, nifty_df)
    score += min(20, max(0, (rs - 0.9) * 50))

    # ── TREND SCORE (0–20)
    ema50 = close.ewm(span=50).mean().iloc[-1]
    ema200 = close.ewm(span=200).mean().iloc[-1]

    if ema50 > ema200:
        score += 10
    if close.iloc[-1] > ema50:
        score += 10

    # ── POLE SCORE (0–15)
    recent = close.iloc[-200:]
    pole_pct = (recent.max() - recent.min()) / recent.min() * 100
    score += min(15, pole_pct / 5)

    # ── BASE TIGHTNESS (0–20)
    base = close.iloc[-60:]
    base_range = (base.max() - base.min()) / base.max()

    if base_range < 0.1:
        score += 20
    elif base_range < 0.15:
        score += 15
    elif base_range < 0.2:
        score += 10

    # ── VCP STRUCTURE (0–15)
    highs, lows = find_swings(base.values)

    if len(highs) >= 2 and len(lows) >= 2:
        contractions = []

        for i in range(min(len(highs), len(lows)) - 1):
            drop = (highs[i] - lows[i]) / highs[i]
            contractions.append(drop)

        if len(contractions) >= 2:
            improving = sum(
                1 for i in range(len(contractions)-1)
                if contractions[i+1] < contractions[i]
            )
            score += min(15, improving * 5)

    # ── VOLUME DRY-UP (0–10)
    vols = volume.iloc[-60:]
    early = vols.iloc[:30].mean()
    late = vols.iloc[30:].mean()

    if late < early:
        score += 10

    return {
        "Ticker": ticker,
        "Sector": sector,
        "Score": round(score, 2),
        "RS": round(rs, 2),
        "Price": round(close.iloc[-1], 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def run():
    print("\n🎯 VCP SNIPER (SCORING MODE)\n")

    if not os.path.exists("active_sectors.json"):
        print("❌ active_sectors.json missing")
        return

    with open("active_sectors.json") as f:
        sectors = json.load(f)

    nifty = download("^NSEI")
    if nifty is None:
        print("❌ Failed to load NIFTY data")
        return

    results = []

    for sector in sectors:
        tickers = get_stocks(sector)
        print(f"Scanning {sector} ({len(tickers)})")

        for t in tickers:
            res = score_stock(t, sector, nifty)
            if res:
                results.append(res)

            time.sleep(CFG["sleep"])

    if not results:
        print("\n❌ No data")
        return

    df = pd.DataFrame(results)
    df = df.sort_values(by="Score", ascending=False).head(CFG["top_n"])

    df.to_csv("sniper_candidates.csv", index=False)

    print("\n🏆 TOP CANDIDATES")
    print(df.to_string(index=False))


if __name__ == "__main__":
    run()
