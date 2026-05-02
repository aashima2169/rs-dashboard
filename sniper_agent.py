import os
import json
import time
import requests
import pandas as pd
import yfinance as yf


# =========================
# FETCH STOCKS (NSE API) — FIXED (NO INDEX SYMBOLS)
# =========================
def get_stocks(sector_key: str) -> list:
    try:
        with open("config.json", "r") as f:
            config = json.load(f)

        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        if not official_name:
            print(f"  ⚠️ No NSE mapping for: {sector_key}")
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

            # ✅ FIX: remove index symbols like NIFTY / PSE
            stocks = []
            for s in data:
                symbol = s.get("symbol", "").upper()

                if not symbol:
                    continue

                if (
                    "NIFTY" in symbol
                    or symbol == official_name.upper()
                    or symbol.endswith("INDEX")
                ):
                    continue

                stocks.append(f"{symbol}.NS")

            return stocks

        else:
            print(f"  ❌ NSE API {resp.status_code} for {sector_key}")
            return []

    except Exception as e:
        print(f"  ❌ NSE Error ({sector_key}): {e}")
        return []


# =========================
# MAIN SNIPER
# =========================
def run_sniper():

    print("\n🎯 VCP SNIPER (FINAL)")

    if not os.path.exists("active_sectors.json"):
        print("❌ active_sectors.json not found")
        return

    with open("active_sectors.json", "r") as f:
        active_sectors = json.load(f)

    results = []
    fails = {
        "Trend": 0,
        "Pole": 0,
        "Contraction": 0,
        "Tightening": 0,
        "Base": 0,
        "Data": 0,
        "Error": 0,
    }

    total_checked = 0

    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"Scanning {sector} ({len(tickers)})")

        for t in tickers:
            total_checked += 1

            try:
                df = yf.download(
                    t,
                    period="1y",
                    progress=False,
                    auto_adjust=True,
                )

                if df.empty or len(df) < 200:
                    fails["Data"] += 1
                    continue

                close = df["Close"].dropna()
                cmp = float(close.iloc[-1])

                # =========================
                # TREND FILTER
                # =========================
                ema21 = close.ewm(span=21).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]
                ema200 = close.rolling(200).mean().iloc[-1]

                if not ((ema21 > ema50 > ema200) and (cmp > ema50)):
                    fails["Trend"] += 1
                    continue

                # =========================
                # POLE (DYNAMIC)
                # =========================
                moves = []
                for p in [10, 20, 30, 40]:
                    if len(close) > p:
                        move = ((cmp - close.iloc[-p]) / close.iloc[-p]) * 100
                        moves.append(move)

                if not moves:
                    fails["Data"] += 1
                    continue

                best_pole = max(moves)

                if best_pole < 20:
                    fails["Pole"] += 1
                    continue

                # =========================
                # BASE (LAST 30 DAYS)
                # =========================
                base = close.tail(30)

                if len(base) < 15:
                    fails["Base"] += 1
                    continue

                base_high = base.max()
                base_low = base.min()

                contraction_ratio = (base_high - base_low) / base_high

                if contraction_ratio > 0.5:
                    fails["Contraction"] += 1
                    continue

                # =========================
                # TIGHTENING
                # =========================
                recent = base.tail(10)

                if len(recent) < 6:
                    fails["Tightening"] += 1
                    continue

                highs = recent.rolling(3).max()
                lows = recent.rolling(3).min()

                range_now = highs.iloc[-1] - lows.iloc[-1]
                range_prev = highs.iloc[-4] - lows.iloc[-4]

                if range_now > range_prev:
                    fails["Tightening"] += 1
                    continue

                if recent.iloc[-1] < recent.iloc[-3]:
                    fails["Tightening"] += 1
                    continue

                range_pct = (recent.max() - recent.min()) / recent.mean()
                if range_pct > 0.06:
                    fails["Tightening"] += 1
                    continue

                # =========================
                # SAVE RESULT
                # =========================
                results.append({
                    "Ticker": t,
                    "Sector": sector,
                    "Pole_%": round(best_pole, 1),
                    "Contraction": round(contraction_ratio, 2),
                    "TightRange": round(range_pct, 3),
                    "Price": round(cmp, 2),
                })

            except Exception as e:
                fails["Error"] += 1
                print(f"Error {t}: {e}")

            time.sleep(0.03)

    # =========================
    # OUTPUT
    # =========================
    print("\n🏆 VCP FINAL CANDIDATES\n")

    if results:
        df = pd.DataFrame(results).sort_values("Pole_%", ascending=False)
        print(df.to_string(index=False))
        df.to_csv("sniper_candidates.csv", index=False)
    else:
        print("❌ No VCP candidates found")
        pd.DataFrame(columns=["Ticker", "Sector", "Pole_%", "Contraction", "TightRange", "Price"])\
            .to_csv("sniper_candidates.csv", index=False)

    # =========================
    # DEBUG BREAKDOWN
    # =========================
    print("\n📊 FILTER FAILURE BREAKDOWN\n")

    for k, v in fails.items():
        pct = (v / total_checked * 100) if total_checked else 0
        print(f"{k:<12}: {v} ({pct:.1f}%)")


# =========================
# RUN
# =========================
if __name__ == "__main__":
    run_sniper()
