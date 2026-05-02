import os
import json
import time
import warnings
import logging

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.simplefilter(action="ignore", category=FutureWarning)
logging.basicConfig(level=logging.INFO, format="%(message)s")

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


def compute_atr(df, period=14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    return atr


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

    # ── RS (0–15)
    rs = compute_rs(df, nifty_df)
    score += min(15, max(0, (rs - 0.95) * 40))

    # ── TREND (0–15)
    ema50 = close.ewm(span=50).mean().iloc[-1]
    ema200 = close.ewm(span=200).mean().iloc[-1]

    if ema50 > ema200:
        score += 8
    if close.iloc[-1] > ema50:
        score += 7

    # ── STRONG MOVE (0–10)
    move = (close.iloc[-150:].max() - close.iloc[-150:].min()) / close.iloc[-150:].min()
    score += min(10, move * 10)

    # ── BASE
    base = close.iloc[-60:]
    base_range = (base.max() - base.min()) / base.max()

    if base_range > 0.22:
        return None

    # ── TIGHTNESS (0–25)
    if base_range < 0.08:
        score += 25
    elif base_range < 0.12:
        score += 20
    elif base_range < 0.16:
        score += 12

    # ── RECENT TIGHTNESS (CRITICAL)
    recent = base.iloc[-15:]
    recent_range = (recent.max() - recent.min()) / recent.max()

    if recent_range > base_range * 0.7:
        return None

    if recent_range < 0.05:
        score += 20
    elif recent_range < 0.08:
        score += 15
    elif recent_range < 0.12:
        score += 8

    # ── ATR CONTRACTION (NEW CORE FILTER)
    atr = compute_atr(df)

    atr_base = atr.iloc[-60:]
    atr_recent = atr.iloc[-15:]

    if atr_recent.mean() > atr_base.mean() * 0.8:
        return None  # no volatility contraction

    # bonus for strong contraction
    contraction_ratio = atr_recent.mean() / atr_base.mean()
    if contraction_ratio < 0.6:
        score += 15
    elif contraction_ratio < 0.75:
        score += 10
    else:
        score += 5

    # ── EXPANSION FILTER
    last_move = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5]
    if last_move > 0.15:
        score -= 15

    # ── VOLUME DRY-UP
    vols = volume.iloc[-60:]
    if vols.iloc[30:].mean() < vols.iloc[:30].mean():
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
    print("\n🎯 VCP SNIPER (ATR + STRUCTURE MODE)\n")

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
        print("\n❌ No candidates")
        return

    df = pd.DataFrame(results)
    df = df.sort_values(by="Score", ascending=False).head(CFG["top_n"])

    df.to_csv("sniper_candidates.csv", index=False)

    print("\n🏆 TOP VCP-LIKE CANDIDATES\n")
    print(df.to_string(index=False))


if __name__ == "__main__":
    run()
