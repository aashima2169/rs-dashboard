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

# ─────────────────────────────────────────
# DATA
# ─────────────────────────────────────────
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


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def compute_atr(df):
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"] - df["Close"].shift()).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(14).mean()


# ─────────────────────────────────────────
# CORE LOGIC
# ─────────────────────────────────────────
def score_stock(ticker, sector):
    df = download(ticker)
    if df is None or len(df) < 200:
        return None

    close = df["Close"]
    volume = df["Volume"]

    score = 0

    # ── EMA STRUCTURE (MANDATORY)
    ema21 = close.ewm(span=21).mean()
    ema50 = close.ewm(span=50).mean()
    ema100 = close.ewm(span=100).mean()

    if not (ema21.iloc[-1] > ema50.iloc[-1] > ema100.iloc[-1]):
        return None

    # ── BASE
    base = df.iloc[-60:]
    base_close = base["Close"]

    base_range = (base_close.max() - base_close.min()) / base_close.max()
    if base_range > 0.35:
        return None

    # ── RIGHT SIDE
    recent = base.iloc[-12:]
    recent_close = recent["Close"]

    # 🚨 HARD FILTER: tight last candles
    last_6 = close.iloc[-6:]
    tight_range = (last_6.max() - last_6.min()) / last_6.max()
    if tight_range > 0.06:
        return None

    # 🚨 NEW: Reject expansion candles
    last = df.iloc[-1]
    avg_range = (df["High"] - df["Low"]).iloc[-20:-1].mean()
    last_range = last["High"] - last["Low"]

    if last_range > 1.8 * avg_range:
        return None

    body = abs(last["Close"] - last["Open"])
    if body > 1.5 * avg_range:
        return None

    # ── RANGE COMPRESSION SCORE
    recent_range = (recent_close.max() - recent_close.min()) / recent_close.max()

    if recent_range < 0.04:
        score += 50
    elif recent_range < 0.08:
        score += 30
    elif recent_range < 0.12:
        score += 10
    else:
        score -= 20

    # ── SIDEWAYS TIGHTNESS
    std_dev = recent_close.pct_change().std()
    if std_dev < 0.01:
        score += 25

    # ── CANDLE COMPRESSION
    bodies = (recent["Close"] - recent["Open"]).abs()
    ranges = (recent["High"] - recent["Low"])
    body_ratio = (bodies / ranges).mean()

    if body_ratio < 0.4:
        score += 20
    elif body_ratio < 0.6:
        score += 10
    else:
        score -= 15

    # ── RANGE CONTRACTION (VCP structure)
    seg1 = base_close.iloc[:20]
    seg2 = base_close.iloc[20:40]
    seg3 = base_close.iloc[40:]

    r1 = (seg1.max() - seg1.min()) / seg1.max()
    r2 = (seg2.max() - seg2.min()) / seg2.max()
    r3 = (seg3.max() - seg3.min()) / seg3.max()

    if r3 < r2 < r1:
        score += 30
    elif r3 < r2:
        score += 10

    # ── ATR contraction
    atr = compute_atr(df)
    atr_ratio = atr.iloc[-12:].mean() / atr.iloc[-60:].mean()

    if atr_ratio < 0.7:
        score += 20
    elif atr_ratio < 0.9:
        score += 10

    # ── Volume dry-up
    vols = volume.iloc[-60:]
    if vols.iloc[30:].mean() < vols.iloc[:30].mean():
        score += 10

    # ── Remove slow trend grinders
    slope = np.polyfit(range(len(recent_close)), recent_close, 1)[0]
    if slope > 0:
        score -= 15

    # ── STRICT: no breakout already
    if close.iloc[-1] > recent_close.max() * 1.02:
        return None

    return {
        "Ticker": ticker,
        "Sector": sector,
        "Score": round(score, 2),
        "Price": round(close.iloc[-1], 2),
    }


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def run():
    print("\n🎯 VCP SNIPER (FINAL MODE)\n")

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

    print(f"\n📊 Total candidates found: {len(results)}")

    df = pd.DataFrame(results)

    # ALWAYS CREATE FILE
    if df.empty:
        print("\n❌ No candidates")
        df = pd.DataFrame(columns=["Ticker", "Sector", "Score", "Price"])
        df.to_csv("sniper_candidates.csv", index=False)
        return

    df = df.sort_values("Score", ascending=False)
    df = df.drop_duplicates(subset=["Ticker"])
    df = df.head(CFG["top_n"])

    df.to_csv("sniper_candidates.csv", index=False)

    print("\n🏆 TOP VCP-LIKE CANDIDATES\n")
    print(df.to_string(index=False))


if __name__ == "__main__":
    run()
