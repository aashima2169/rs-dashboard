import os
import json
import time
import requests
import pandas as pd
import yfinance as yf

# ==============================
# CONFIG
# ==============================
DEBUG = True

# ==============================
# NSE STOCK FETCH
# ==============================
def get_stocks(sector_key: str) -> list:
    try:
        with open("config.json", "r") as f:
            config = json.load(f)

        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        if not official_name:
            print(f"⚠️ No NSE mapping for: {sector_key}")
            return []

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.nseindia.com/",
        }

        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)

        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        resp = session.get(url, headers=headers, timeout=10)

        if resp.status_code == 200:
            data = resp.json().get("data", [])
            return [f"{s['symbol']}.NS" for s in data if "symbol" in s]

        print(f"❌ NSE API error {resp.status_code} for {sector_key}")
        return []

    except Exception as e:
        print(f"❌ NSE Error ({sector_key}): {e}")
        return []

# ==============================
# SAFE CLOSE
# ==============================
def get_close(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df["Close"].dropna()

# ==============================
# FILTER TRACKING
# ==============================
filter_fails = {
    "Trend": 0,
    "Pole": 0,
    "Contraction": 0,
    "Tightening": 0,
    "Base": 0,
    "Data": 0,
    "Error": 0,
}

# ==============================
# CORE LOGIC
# ==============================
def evaluate_stock(ticker, sector):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)

        if df.empty or len(df) < 200:
            filter_fails["Data"] += 1
            return None

        close = get_close(df)

        # FIX: remove warning
        cmp = float(close.iloc[-1])

        # =========================
        # TREND FILTER
        # =========================
        ema21 = close.ewm(span=21).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        ema200 = close.ewm(span=200).mean().iloc[-1]

        if not (ema21 > ema50 > ema200 and cmp > ema50):
            filter_fails["Trend"] += 1
            return None

        # =========================
        # POLE DETECTION
        # =========================
        moves = [
            ((cmp - close.iloc[-10]) / close.iloc[-10]) * 100,
            ((cmp - close.iloc[-20]) / close.iloc[-20]) * 100,
            ((cmp - close.iloc[-30]) / close.iloc[-30]) * 100,
            ((cmp - close.iloc[-40]) / close.iloc[-40]) * 100,
        ]

        best_pole = max(moves)

        if best_pole < 20:
            filter_fails["Pole"] += 1
            return None

        # =========================
        # CONTRACTION
        # =========================
        recent = close.tail(20)
        contraction_ratio = recent.std() / recent.mean()

        if contraction_ratio > 0.5:
            filter_fails["Contraction"] += 1
            return None

        # =========================
        # TIGHTENING
        # =========================
        range_pct = (recent.max() - recent.min()) / recent.mean()

        if range_pct > 0.06:
            filter_fails["Tightening"] += 1
            return None

        # =========================
        # BASE (FIXED LOGIC)
        # =========================
        base_high = close.tail(30).max()

        # price must be near highs (NOT lows)
        if cmp < base_high * 0.90:
            filter_fails["Base"] += 1
            return None

        return {
            "Ticker": ticker,
            "Sector": sector,
            "Pole_%": round(best_pole, 1),
            "Contraction": round(contraction_ratio, 2),
            "TightRange": round(range_pct, 3),
            "Price": round(cmp, 2),
        }

    except Exception as e:
        filter_fails["Error"] += 1
        return None

# ==============================
# MAIN
# ==============================
def run_sniper():
    print("\n🎯 VCP SNIPER (FINAL)")

    if not os.path.exists("active_sectors.json"):
        print("❌ active_sectors.json not found")
        return

    with open("active_sectors.json", "r") as f:
        active_sectors = json.load(f)

    results = []

    for sector in active_sectors:
        stocks = get_stocks(sector)
        print(f"Scanning {sector} ({len(stocks)})")

        for stock in stocks:
            res = evaluate_stock(stock, sector)
            if res:
                results.append(res)
            time.sleep(0.05)

    df = pd.DataFrame(results)

    print("\n🏆 VCP FINAL CANDIDATES")

    if df.empty:
        print("❌ No candidates found")
    else:
        df = df.sort_values("Pole_%", ascending=False)
        print(df.to_string(index=False))

    # =========================
    # DEBUG OUTPUT
    # =========================
    total = sum(filter_fails.values())

    print("\n📊 FILTER FAILURE BREAKDOWN")
    for k, v in filter_fails.items():
        pct = (v / total * 100) if total > 0 else 0
        print(f"{k:<12}: {v} ({pct:.1f}%)")

    # =========================
    # SAVE FILE
    # =========================
    df.to_csv("sniper_candidates.csv", index=False)

# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    run_sniper()
