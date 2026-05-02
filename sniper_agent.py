import os
import json
import time
import requests
import pandas as pd
import yfinance as yf

# ==============================
# NSE STOCK FETCH (DYNAMIC)
# ==============================
def get_stocks(sector_key):
    try:
        with open("config.json", "r") as f:
            config = json.load(f)

        official_name = config["nse_index_mapping"].get(sector_key)
        if not official_name:
            return []

        session = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0"}

        session.get("https://www.nseindia.com", headers=headers)

        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        resp = session.get(url, headers=headers)

        return [f"{x['symbol']}.NS" for x in resp.json()["data"] if x["symbol"] != official_name]

    except:
        return []


# ==============================
# VCP SCORE FUNCTION
# ==============================
def vcp_score(df):
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # --- EMA STRUCTURE ---
    ema21 = close.ewm(span=21).mean()
    ema50 = close.ewm(span=50).mean()
    ema200 = close.ewm(span=200).mean()

    if not (ema21.iloc[-1] > ema50.iloc[-1] > ema200.iloc[-1]):
        return None

    score = 0

    # --- ATR CONTRACTION ---
    tr = high - low
    atr = tr.rolling(14).mean()
    if atr.iloc[-1] < atr.iloc[-5]:
        score += 25

    # --- RANGE CONTRACTION ---
    ranges = (high - low).rolling(5).mean()
    if ranges.iloc[-1] < ranges.iloc[-5]:
        score += 25

    # --- CANDLE COMPRESSION ---
    bodies = abs(close - df["Open"])
    if bodies.iloc[-1] < bodies.iloc[-5]:
        score += 15

    # ==============================
    # 🔥 RIGHT SIDE (STRICT FIX)
    # ==============================
    recent = df.iloc[-15:]
    last_7 = recent["Close"].iloc[-7:]

    # Tight range
    tight_range = (last_7.max() - last_7.min()) / last_7.max()
    if tight_range > 0.045:
        return None
    else:
        score += 20

    # No breakout already
    if close.iloc[-1] > last_7.max() * 1.015:
        return None

    # No vertical spike into base
    prev_move = close.iloc[-15:-7]
    move_pct = (prev_move.iloc[-1] - prev_move.iloc[0]) / prev_move.iloc[0]
    if move_pct > 0.12:
        return None

    # Compression structure (bonus)
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
# MAIN SNIPER
# ==============================
def run_sniper():
    print("\n🎯 VCP SNIPER (FINAL)\n")

    if not os.path.exists("active_sectors.json"):
        print("❌ active_sectors.json not found")
        return

    with open("active_sectors.json", "r") as f:
        active_sectors = json.load(f)

    results = []

    for sector in active_sectors:
        print(f"Scanning {sector}...")
        tickers = get_stocks(sector)

        for t in tickers:
            try:
                df = yf.download(t, period="1y", interval="1wk", progress=False)

                if df.empty or len(df) < 30:
                    continue

                score = vcp_score(df)

                if score is not None:
                    results.append({
                        "Ticker": t,
                        "Sector": sector,
                        "Score": round(score, 2),
                        "Price": round(df["Close"].iloc[-1], 2)
                    })

            except:
                continue

            time.sleep(0.05)

    df = pd.DataFrame(results)

    # Always create CSV
    if df.empty:
        df = pd.DataFrame(columns=["Ticker", "Sector", "Score", "Price"])

    df = df.sort_values(by="Score", ascending=False)

    print("\n🏆 TOP VCP-LIKE CANDIDATES\n")
    print(df.to_string(index=False))

    df.to_csv("sniper_candidates.csv", index=False)


# ==============================
# ENTRY
# ==============================
if __name__ == "__main__":
    run_sniper()
