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


def candle_body(df):
    return (df["Close"] - df["Open"]).abs()


def candle_range(df):
    return df["High"] - df["Low"]


# ─────────────────────────────────────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────────────────────────────────────
def score_stock(ticker, sector):
    df = download(ticker)
    if df is None or len(df) < 200:
        return None

    close = df["Close"]
    volume = df["Volume"]

    score = 0
    tightness = 0

    # ── EMA STRUCTURE (STRICT FILTER)
    ema21 = close.ewm(span=21).mean()
    ema50 = close.ewm(span=50).mean()
    ema100 = close.ewm(span=100).mean()

    if not (ema21.iloc[-1] > ema50.iloc[-1] > ema100.iloc[-1]):
        return None

    if close.iloc[-1] < ema21.iloc[-1]:
        return None

    # slope check (important)
    if ema21.iloc[-1] <= ema21.iloc[-5]:
        score -= 5

    # ── PRIOR MOVE
    move = (close.iloc[-150:].max() - close.iloc[-150:].min()) / close.iloc[-150:].min()
    score += min(8, move * 8)

    # ── BASE
    base = df.iloc[-60:]
    base_close = base["Close"]

    base_range = (base_close.max() - base_close.min()) / base_close.max()
    if base_range > 0.30:
        return None

    # ── BASE TIGHTNESS
    if base_range < 0.08:
        tightness += 20
    elif base_range < 0.12:
        tightness += 15
    elif base_range < 0.18:
        tightness += 8

    # ── RIGHT SIDE
    recent = base.iloc[-15:]
    recent_close = recent["Close"]

    recent_range = (recent_close.max() - recent_close.min()) / recent_close.max()

    if recent_range < 0.05:
        tightness += 20
    elif recent_range < 0.08:
        tightness += 15
    elif recent_range < 0.12:
        tightness += 5
    else:
        tightness -= 10

    if recent_range > 0.15:
        score -= 15

    # ── RANGE CONTRACTION
    seg1 = base_close.iloc[:20]
    seg2 = base_close.iloc[20:40]
    seg3 = base_close.iloc[40:]

    r1 = (seg1.max() - seg1.min()) / seg1.max()
    r2 = (seg2.max() - seg2.min()) / seg2.max()
    r3 = (seg3.max() - seg3.min()) / seg3.max()

    if r3 < r2 < r1:
        tightness += 20
    else:
        score -= 10

    # ── ATR CONTRACTION
    atr = compute_atr(df)
    atr_ratio = atr.iloc[-15:].mean() / atr.iloc[-60:].mean()

    if atr_ratio < 0.6:
        tightness += 15
    elif atr_ratio < 0.8:
        tightness += 10
    elif atr_ratio < 1.0:
        tightness += 5
    else:
        score -= 8

    # ── CANDLE COMPRESSION
    body = candle_body(base)
    rng = candle_range(base)

    if body.iloc[-15:].mean() < body.iloc[:45].mean() * 0.7:
        tightness += 10
    if rng.iloc[-15:].mean() < rng.iloc[:45].mean() * 0.7:
        tightness += 10

    # ── TREND EXTENSION PENALTY
    trend_move = (close.iloc[-30:].max() - close.iloc[-30:].min()) / close.iloc[-30:].min()
    if trend_move > 0.20:
        score -= 15

    # ── VOLUME
    vols = volume.iloc[-60:]
    if vols.iloc[30:].mean() < vols.iloc[:30].mean():
        tightness += 8

    final_score = (score * 0.4) + (tightness * 2.0)

    return {
        "Ticker": ticker,
        "Sector": sector,
        "Score": round(final_score, 2),
        "Price": round(close.iloc[-1], 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def run():
    print("\n🎯 VCP SNIPER (EMA STRUCTURE + TRUE VCP LOGIC)\n")

    if not os.path.exists("active_sectors.json"):
        print("❌ active_sectors.json missing")
        return

    with open("active_sectors.json") as f:
        sectors = json.load(f)

    results = []

    for sector in sectors:
        tickers = get_stocks(sector)
        print(f"Scanning {sector} ({len(tickers)})")

        for t in tickers:
            res = score_stock(t, sector)
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
