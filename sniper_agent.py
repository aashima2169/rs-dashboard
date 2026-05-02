import yfinance as yf
import pandas as pd
import numpy as np

# =========================
# CONFIG
# =========================
TICKERS = []  # <-- your ticker list here

# =========================
# HELPERS
# =========================
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


def compute_structure_score(base_close, recent_close):
    score = 0

    # Split into contraction legs
    seg1 = base_close.iloc[:20]
    seg2 = base_close.iloc[20:40]
    seg3 = base_close.iloc[40:]

    r1 = (seg1.max() - seg1.min()) / seg1.max()
    r2 = (seg2.max() - seg2.min()) / seg2.max()
    r3 = (seg3.max() - seg3.min()) / seg3.max()

    # Multi-leg contraction
    if r3 < r2 < r1:
        score += 40
    elif r3 < r2:
        score += 20

    # Tight right side
    recent_range = (recent_close.max() - recent_close.min()) / recent_close.max()

    if recent_range < 0.04:
        score += 40
    elif recent_range < 0.08:
        score += 25
    elif recent_range < 0.12:
        score += 10
    else:
        score -= 30

    # Sideways behavior (very important)
    std_dev = recent_close.pct_change().std()

    if std_dev < 0.01:
        score += 30
    elif std_dev < 0.015:
        score += 15
    else:
        score -= 20

    return score


def is_valid_trend(df):
    ema21 = df["Close"].ewm(span=21).mean().iloc[-1]
    ema50 = df["Close"].ewm(span=50).mean().iloc[-1]
    ema100 = df["Close"].ewm(span=100).mean().iloc[-1]

    return ema21 > ema50 > ema100


# =========================
# MAIN SCANNER
# =========================
results = []

for ticker in TICKERS:
    try:
        df = yf.download(ticker, period="1y", interval="1wk", progress=False)

        if len(df) < 70:
            continue

        close = df["Close"]
        volume = df["Volume"]

        # EMA TREND FILTER (mandatory)
        if not is_valid_trend(df):
            continue

        base = df.iloc[-60:]
        recent = base.iloc[-12:]

        base_close = base["Close"]
        recent_close = recent["Close"]

        # =========================
        # STRUCTURE SCORE
        # =========================
        structure_score = compute_structure_score(base_close, recent_close)

        # =========================
        # QUALITY SCORE
        # =========================
        quality_score = 0

        # Candle compression
        bodies = (recent["Close"] - recent["Open"]).abs()
        ranges = (recent["High"] - recent["Low"])
        body_ratio = (bodies / ranges).mean()

        if body_ratio < 0.4:
            quality_score += 20
        elif body_ratio < 0.6:
            quality_score += 10
        else:
            quality_score -= 10

        # ATR contraction
        atr = compute_atr(df)
        atr_ratio = atr.iloc[-12:].mean() / atr.iloc[-60:].mean()

        if atr_ratio < 0.7:
            quality_score += 20
        elif atr_ratio < 0.9:
            quality_score += 10

        # Volume contraction
        vols = volume.iloc[-60:]
        if vols.iloc[30:].mean() < vols.iloc[:30].mean():
            quality_score += 10

        # =========================
        # TREND PENALTY (kill runners)
        # =========================
        trend = (close.iloc[-1] - close.iloc[-12]) / close.iloc[-12]

        if trend > 0.06:
            quality_score -= 60

        # =========================
        # BREAKOUT FILTER (already moved stocks)
        # =========================
        if close.iloc[-1] > recent_close.max() * 1.025:
            quality_score -= 30

        # =========================
        # FINAL SCORE (structure dominates)
        # =========================
        score = structure_score * 2 + quality_score

        if score > 30:
            results.append({
                "Ticker": ticker,
                "Score": round(score, 2),
                "Price": round(close.iloc[-1], 2)
            })

    except:
        continue


# =========================
# OUTPUT
# =========================
results = sorted(results, key=lambda x: x["Score"], reverse=True)

print("\n🏆 TOP VCP-LIKE CANDIDATES\n")
print(f"{'Ticker':<15} {'Score':<10} {'Price':<10}")

for r in results:
    print(f"{r['Ticker']:<15} {r['Score']:<10} {r['Price']:<10}")
