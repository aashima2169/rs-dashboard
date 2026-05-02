import os, requests, json, time
import pandas as pd
import numpy as np
import yfinance as yf
import warnings
from collections import defaultdict

warnings.simplefilter(action='ignore', category=FutureWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID")

# ─────────────────────────────────────────────
# CONFIG — tweak these to widen/narrow the scan
# ─────────────────────────────────────────────
CFG = {
    "min_pole_pct":          20,   # Pole must be at least this strong (%)
    "pole_lookback_days":   130,   # Window to search for the pole top
    "vcp_base_days":         60,   # Days after pole top to measure the base
    "max_base_depth_pct":    20,   # Base must not pull back more than this from pole top
    "vol_contraction_ratio": 0.80, # Recent 20d avg vol must be < 80% of 90d avg vol
    "near_high_threshold":   0.88, # CMP must be within 12% of pole high
    "min_contraction_ratio": 0.50, # Base range must be ≤ 50% of the pole range
}

# ─────────────────────────────────────────────
# FILTER LABELS (for debug summary table)
# ─────────────────────────────────────────────
FILTERS = [
    "F1_EMA_Trend",       # CMP > EMA21 > EMA50 > EMA200
    "F2_Pole_Size",       # Pole >= min_pole_pct
    "F3_Base_Formed",     # Enough bars exist after the pole top
    "F4_Contraction",     # Base range <= 50% of pole range
    "F5_Base_Depth",      # Base low not more than 20% below pole high
    "F6_Volume_Dryup",    # 20d avg vol < 80% of 90d avg vol
    "F7_Near_Breakout",   # CMP within 12% of pole high
]


def get_stocks(sector_key: str) -> list:
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        if not official_name:
            print(f"  ⚠️  No NSE mapping for: {sector_key}")
            return []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.nseindia.com/",
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        resp = session.get(url, headers=headers, timeout=10)

        if resp.status_code == 200:
            return [f"{s['symbol']}.NS" for s in resp.json()["data"] if s["symbol"] != official_name]
        print(f"  ❌ NSE API {resp.status_code} for {sector_key}")
        return []
    except Exception as e:
        print(f"  ❌ NSE Error ({sector_key}): {e}")
        return []


def detect_vcp(ticker: str, sector: str, cfg: dict, filter_fails: dict) -> dict | None:
    """
    Runs each VCP filter in sequence and logs which one fails.
    Returns result dict if all pass, else None.
    """
    try:
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 250:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close  = df["Close"].squeeze()
        volume = df["Volume"].squeeze()
        cmp    = float(close.iloc[-1])

        # ── F1: EMA TREND ────────────────────────────────────────────────────
        # Uptrend confirmed when CMP > EMA21 > EMA50 > EMA200
        ema21  = float(close.ewm(span=21,  adjust=False).mean().iloc[-1])
        ema50  = float(close.ewm(span=50,  adjust=False).mean().iloc[-1])
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

        if not (cmp > ema21 > ema50 > ema200):
            filter_fails["F1_EMA_Trend"] += 1
            return None

        # ── F2: POLE SIZE ────────────────────────────────────────────────────
        # Highest close in last pole_lookback_days = pole top
        # Trough in 60 days before that peak = pole base
        lookback_close = close.tail(cfg["pole_lookback_days"])
        pole_high      = float(lookback_close.max())
        pole_high_idx  = lookback_close.idxmax()

        pre_peak_window = close.loc[:pole_high_idx].tail(60)
        if len(pre_peak_window) < 10:
            filter_fails["F2_Pole_Size"] += 1
            return None
        pole_low = float(pre_peak_window.min())

        pole_pct = ((pole_high - pole_low) / pole_low) * 100
        if pole_pct < cfg["min_pole_pct"]:
            filter_fails["F2_Pole_Size"] += 1
            return None

        # ── F3: BASE HAS FORMED ──────────────────────────────────────────────
        post_peak_close = close.loc[pole_high_idx:]
        base_window     = post_peak_close.tail(cfg["vcp_base_days"])
        if len(base_window) < 5:
            filter_fails["F3_Base_Formed"] += 1
            return None

        # ── F4: VOLATILITY CONTRACTION ───────────────────────────────────────
        base_high  = float(base_window.max())
        base_low   = float(base_window.min())
        pole_range = pole_high - pole_low
        base_range = base_high - base_low

        contraction_ratio = (base_range / pole_range) if pole_range > 0 else 999
        if contraction_ratio > cfg["min_contraction_ratio"]:
            filter_fails["F4_Contraction"] += 1
            return None

        # ── F5: BASE DEPTH ───────────────────────────────────────────────────
        # Shallow pullback from pole top = strong holders not selling
        base_depth_pct = ((pole_high - base_low) / pole_high) * 100
        if base_depth_pct > cfg["max_base_depth_pct"]:
            filter_fails["F5_Base_Depth"] += 1
            return None

        # ── F6: VOLUME DRY-UP ────────────────────────────────────────────────
        avg_vol_20 = float(volume.tail(20).mean())
        avg_vol_90 = float(volume.tail(90).mean())
        vol_ratio  = (avg_vol_20 / avg_vol_90) if avg_vol_90 > 0 else 999
        if vol_ratio > cfg["vol_contraction_ratio"]:
            filter_fails["F6_Volume_Dryup"] += 1
            return None

        # ── F7: NEAR BREAKOUT ────────────────────────────────────────────────
        # CMP must be close to the pivot — too far below = not actionable yet
        if cmp < pole_high * cfg["near_high_threshold"]:
            filter_fails["F7_Near_Breakout"] += 1
            return None

        # ── ALL FILTERS PASSED ───────────────────────────────────────────────
        return {
            "Ticker":            ticker,
            "Sector":            sector,
            "CMP":               round(cmp, 2),
            "Pole_%":            round(pole_pct, 2),
            "Base_Depth_%":      round(base_depth_pct, 2),
            "Contraction_Ratio": round(contraction_ratio, 2),
            "Vol_Ratio_20_90":   round(vol_ratio, 2),
            "Dist_From_High_%":  round(((pole_high - cmp) / pole_high) * 100, 2),
            "Pivot_Price":       round(pole_high * 1.01, 2),
            "EMA21":             round(ema21, 2),
            "EMA50":             round(ema50, 2),
            "EMA200":            round(ema200, 2),
        }

    except Exception as e:
        print(f"  ⚠️  Error — {ticker}: {e}")
        return None


def print_filter_report(filter_fails: dict, total: int):
    """Prints a breakdown table showing how many stocks each filter eliminated."""
    print("\n" + "═" * 58)
    print("  📊  FILTER ELIMINATION REPORT")
    print("═" * 58)
    print(f"  {'Filter':<25}  {'Eliminated':>10}  {'% of Scanned':>12}")
    print("─" * 58)
    for f in FILTERS:
        n   = filter_fails.get(f, 0)
        pct = (n / total * 100) if total > 0 else 0
        bar = "█" * int(pct / 4)
        print(f"  {f:<25}  {n:>10}  {pct:>11.1f}%  {bar}")
    print("═" * 58)
    passed = total - sum(filter_fails.values())
    print(f"  Total scanned : {total}")
    print(f"  Total passed  : {max(passed, 0)}")
    print("═" * 58 + "\n")

    # Bottleneck hint
    if filter_fails:
        worst = max(filter_fails, key=filter_fails.get)
        hints = {
            "F1_EMA_Trend":    "Raise ema spans or drop the EMA200 requirement (allow CMP > EMA21 > EMA50)",
            "F2_Pole_Size":    "Lower min_pole_pct (e.g. 15) or increase pole_lookback_days (e.g. 180)",
            "F3_Base_Formed":  "Reduce vcp_base_days minimum bar requirement",
            "F4_Contraction":  "Raise min_contraction_ratio (e.g. 0.65) to allow wider bases",
            "F5_Base_Depth":   "Raise max_base_depth_pct (e.g. 25–30) to allow deeper pullbacks",
            "F6_Volume_Dryup": "Raise vol_contraction_ratio (e.g. 0.90) — volume dry-up is less strict",
            "F7_Near_Breakout":"Lower near_high_threshold (e.g. 0.80) to widen the breakout proximity window",
        }
        print(f"  🔍 Bottleneck : {worst} ({filter_fails[worst]} stocks killed here)")
        print(f"  💡 Suggestion : {hints.get(worst, 'Relax this filter in CFG')}\n")


def run_sniper():
    print("\n🎯 --- VCP SNIPER SCAN (EMA TREND + POLE + CONTRACTION + VOLUME) ---\n")

    if not os.path.exists("active_sectors.json"):
        print("❌ active_sectors.json not found.")
        return

    with open("active_sectors.json", "r") as f:
        active_sectors = json.load(f)

    results      = []
    filter_fails = defaultdict(int)
    total_stocks = 0

    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂  {sector} → {len(tickers)} tickers")

        for ticker in tickers:
            total_stocks += 1
            hit = detect_vcp(ticker, sector, CFG, filter_fails)
            if hit:
                results.append(hit)
                print(
                    f"  ✅ {ticker.ljust(14)} | "
                    f"Pole: {hit['Pole_%']}%  "
                    f"Depth: {hit['Base_Depth_%']}%  "
                    f"Contraction: {hit['Contraction_Ratio']}  "
                    f"Vol: {hit['Vol_Ratio_20_90']}  "
                    f"→ Pivot ₹{hit['Pivot_Price']}"
                )
            time.sleep(0.05)

    # ── FILTER DEBUG REPORT ──────────────────────────────────────────────────
    print_filter_report(filter_fails, total_stocks)

    # ── SAVE + NOTIFY ────────────────────────────────────────────────────────
    if results:
        results.sort(key=lambda x: (x["Contraction_Ratio"], x["Dist_From_High_%"]))
        pd.DataFrame(results).to_csv("sniper_candidates.csv", index=False)

        msg  = "🎯 *VCP SNIPER — Stage 2 Bases*\n"
        msg += "`TICKER       POLE%  DEPTH%  RATIO  PIVOT`\n"
        for r in results[:15]:
            msg += (
                f"`{r['Ticker'].ljust(12)} "
                f"{str(r['Pole_%']).ljust(6)} "
                f"{str(r['Base_Depth_%']).ljust(7)} "
                f"{str(r['Contraction_Ratio']).ljust(6)} "
                f"₹{r['Pivot_Price']}`\n"
            )
        if TELEGRAM_TOKEN and CHAT_ID:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            )
        print(f"✨ {len(results)} VCP candidates → sniper_candidates.csv")
    else:
        print("ℹ️  No stocks passed all filters. See the report above to find the bottleneck.\n")


if __name__ == "__main__":
    run_sniper()
