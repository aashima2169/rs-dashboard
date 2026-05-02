import os
import json
import time
import requests
import pandas as pd
import yfinance as yf


# ================================
# CONFIG
# ================================
CONFIG = {
    "pole_lookback_days": 120,
    "pole_exclude_recent": 10,
    "pole_trough_window": 30,
    "min_pole_pct": 18,
    "max_pole_pct": 150,

    "vcp_base_days": 30,
    "min_base_bars": 15,
}


# ================================
# NSE STOCK FETCHER (FIXED)
# ================================
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

            stocks = []
            for s in data:
                sym = s.get("symbol", "")

                # 🔥 REMOVE JUNK SYMBOLS
                if not sym:
                    continue
                if "NIFTY" in sym.upper():
                    continue
                if sym.endswith("-"):
                    continue

                stocks.append(f"{sym}.NS")

            return list(set(stocks))

        print(f"❌ NSE API error {resp.status_code} for {sector_key}")
        return []

    except Exception as e:
        print(f"❌ NSE Error ({sector_key}): {e}")
        return []


# ================================
# VCP DETECTION
# ================================
def detect_vcp(ticker, sector, cfg, fails):
    try:
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=True)

        if df.empty or len(df) < 250:
            fails["Data"] += 1
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df["Close"]

        # ✅ FIXED WARNING
        cmp = float(close.iloc[-1].item())

        # ========================
        # TREND (RELAXED)
        # ========================
        ema21 = float(close.ewm(span=21).mean().iloc[-1])
        ema50 = float(close.ewm(span=50).mean().iloc[-1])

        if not ((ema21 > ema50) and (cmp > ema50)):
            fails["Trend"] += 1
            return None

        # ========================
        # POLE
        # ========================
        exclude = cfg["pole_exclude_recent"]
        search = close.iloc[-(cfg["pole_lookback_days"] + exclude):-exclude]

        if len(search) < 20:
            fails["Pole"] += 1
            return None

        pole_high = search.max()
        idx = search.idxmax()

        pre = close.loc[:idx].tail(cfg["pole_trough_window"])
        if len(pre) == 0:
            fails["Pole"] += 1
            return None

        pole_low = pre.min()

        if pole_low == 0:
            fails["Pole"] += 1
            return None

        pole_pct = ((pole_high - pole_low) / pole_low) * 100

        if not (cfg["min_pole_pct"] <= pole_pct <= cfg["max_pole_pct"]):
            fails["Pole"] += 1
            return None

        # ========================
        # BASE / CONTRACTION
        # ========================
        base = close.loc[idx:].tail(cfg["vcp_base_days"])

        if len(base) < cfg["min_base_bars"]:
            fails["Base"] += 1
            return None

        base_high = base.max()
        base_low = base.min()

        pole_range = pole_high - pole_low
        base_range = base_high - base_low

        if pole_range == 0:
            fails["Pole"] += 1
            return None

        contraction_ratio = base_range / pole_range

        if contraction_ratio > 0.35:
            fails["Contraction"] += 1
            return None

        # ========================
        # TIGHTENING (FIXED 🔥)
        # ========================
        recent = base.tail(10)

        if len(recent) < 5:
            fails["Tightening"] += 1
            return None

        highs = recent.rolling(3).max()
        lows = recent.rolling(3).min()

        # contraction in ranges
        range_now = highs.iloc[-1] - lows.iloc[-1]
        range_prev = highs.iloc[-4] - lows.iloc[-4]

        if range_now > range_prev:
            fails["Tightening"] += 1
            return None

        # higher lows
        if recent.iloc[-1] < recent.iloc[-3]:
            fails["Tightening"] += 1
            return None

        # volatility compression
        range_pct = (recent.max() - recent.min()) / recent.mean()

        if range_pct > 0.05:
            fails["Tightening"] += 1
            return None

        # ========================
        # FINAL OUTPUT
        # ========================
        return {
            "Ticker": ticker,
            "Sector": sector,
            "Pole_%": round(pole_pct, 1),
            "Contraction": round(contraction_ratio, 2),
            "TightRange": round(range_pct, 3),
            "Price": round(cmp, 2),
        }

    except Exception:
        fails["Error"] += 1
        return None


# ================================
# MAIN
# ================================
def run_sniper():
    print("\n🎯 VCP SNIPER (FINAL)\n")

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

    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"Scanning {sector} ({len(tickers)})")

        for t in tickers:
            res = detect_vcp(t, sector, CONFIG, fails)
            if res:
                results.append(res)

            time.sleep(0.05)

    # ========================
    # REMOVE DUPLICATES
    # ========================
    seen = set()
    unique_results = []

    for r in results:
        if r["Ticker"] not in seen:
            unique_results.append(r)
            seen.add(r["Ticker"])

    results = unique_results

    # ========================
    # OUTPUT
    # ========================
    print("\n🏆 VCP FINAL CANDIDATES\n")

    if results:
        df = pd.DataFrame(results).sort_values("Contraction")
        print(df.to_string(index=False))
        df.to_csv("sniper_candidates.csv", index=False)
    else:
        print("❌ No candidates found")
        pd.DataFrame(columns=["Ticker","Sector","Pole_%","Contraction","TightRange","Price"])\
            .to_csv("sniper_candidates.csv", index=False)

    # ========================
    # DEBUG
    # ========================
    total = sum(fails.values())

    print("\n📊 FILTER FAILURE BREAKDOWN\n")
    for k, v in fails.items():
        pct = (v / total * 100) if total > 0 else 0
        print(f"{k:<12}: {v} ({pct:.1f}%)")


# ================================
if __name__ == "__main__":
    run_sniper()
