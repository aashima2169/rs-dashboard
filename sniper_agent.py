import pandas as pd
import numpy as np
import yfinance as yf
import json
import os

# ==============================
# CONFIG
# ==============================
TIMEFRAME = "1y"
INTERVAL = "1wk"


# ==============================
# DATA FETCH
# ==============================
def get_data(ticker):
    try:
        df = yf.download(ticker, period=TIMEFRAME, interval=INTERVAL, progress=False)
        if df is None or len(df) < 30:
            return None
        return df.dropna()
    except:
        return None


# ==============================
# VCP SCORING FUNCTION
# ==============================
def vcp_score(df):
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # ── EMA STRUCTURE ──
    ema21 = close.ewm(span=21).mean()
    ema50 = close.ewm(span=50).mean()
    ema200 = close.ewm(span=200).mean()

    if not (ema21.iloc[-1] > ema50.iloc[-1] > ema200.iloc[-1]):
        return None

    score = 0

    # ── ATR CONTRACTION ──
    tr = high - low
    atr = tr.rolling(14).mean()
    if atr.iloc[-1] < atr.iloc[-5]:
        score += 25

    # ── RANGE CONTRACTION ──
    ranges = (high - low).rolling(5).mean()
    if ranges.iloc[-1] < ranges.iloc[-5]:
        score += 25

    # ── CANDLE COMPRESSION ──
    bodies = abs(close - df["Open"])
    if bodies.iloc[-1] < bodies.iloc[-5]:
        score += 15

    # ==============================
    # 🔥 RIGHT SIDE (STRICT VCP)
    # ==============================
    recent = df.iloc[-15:]
    recent_close = recent["Close"]

    # 1. Tight consolidation
    last_7 = recent_close.iloc[-7:]
    tight_range = (last_7.max() - last_7.min()) / last_7.max()
    if tight_range > 0.045:
        return None
    else:
        score += 20

    # 2. No breakout already
    if close.iloc[-1] > last_7.max() * 1.015:
        return None

    # 3. No vertical move into base
    prev_move = close.iloc[-15:-7]
    move_pct = (prev_move.iloc[-1] - prev_move.iloc[0]) / prev_move.iloc[0]
    if move_pct > 0.12:
        return None

    # 4. Compression structure (bonus, not strict)
    highs = recent["High"].iloc[-7:]
    compress_count = sum(
        highs.iloc[i] >= highs.iloc[i + 1]
        or abs(highs.iloc[i] - highs.iloc[i + 1]) < 0.01
        for i in range(len(highs) - 1)
    )
    if compress_count >= 4:
        score += 10

    # ==============================
    # 🚫 EXTENSION FILTER
    # ==============================
    dist_from_50 = (close.iloc[-1] - ema50.iloc[-1]) / ema50.iloc[-1]
    if dist_from_50 > 0.20:
        return None

    return score


# ==============================
# SCANNER
# ==============================
def run_scan(sectors):
    results = []

    for sector, tickers in sectors.items():
        print(f"Scanning {sector} ({len(tickers)})")

        for ticker in tickers:
            df = get_data(ticker)
            if df is None:
                continue

            score = vcp_score(df)

            if score is not None:
                results.append({
                    "Ticker": ticker,
                    "Sector": sector,
                    "Score": round(score, 2),
                    "Price": round(df["Close"].iloc[-1], 2)
                })

    return results


# ==============================
# MAIN
# ==============================
if __name__ == "__main__":

    print("🎯 VCP SNIPER (PRODUCTION MODE)\n")

    # ✅ Load Scout Output
    if os.path.exists("scout_output.json"):
        with open("scout_output.json", "r") as f:
            sectors = json.load(f)
    else:
        print("❌ scout_output.json not found")
        sectors = {}

    results = run_scan(sectors)

    df = pd.DataFrame(results)

    # ✅ Always create CSV (prevents GitHub artifact failure)
    if df.empty:
        df = pd.DataFrame(columns=["Ticker", "Sector", "Score", "Price"])

    df = df.sort_values(by="Score", ascending=False)

    print("\n🏆 TOP VCP-LIKE CANDIDATES\n")
    print(df.to_string(index=False))

    df.to_csv("sniper_candidates.csv", index=False)
