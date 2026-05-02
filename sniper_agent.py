import os, requests, json, time
import pandas as pd
import yfinance as yf
import warnings
from collections import defaultdict

warnings.simplefilter(action='ignore', category=FutureWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# Changes in this version:
#   F1  EMA gate       CMP > EMA50 > EMA200 → CMP > EMA200 only
#                      (EMA50 was killing 45% of stocks)
#   F4  contraction    0.55 → 0.70 (was eliminating 36.8% — too tight)
#   F2  max_pole_pct   NEW — cap pole at 50% to reject extended trending stocks
#                      (NALCO's 88% pole = trending stock, not a VCP flag pole)
#   F2  trough window  60 → 30 days before pole top (finds recent base,
#                      not a trough from 3 months ago inflating the pole %)
# ─────────────────────────────────────────────────────────────────────────────
CFG = {
    "min_pole_pct":           15,   # Pole must be at least this strong
    "max_pole_pct":           50,   # ★ NEW: cap — rejects extended trending stocks
    "pole_trough_window":     30,   # ★ was 60: days before pole top to find trough
    "pole_lookback_days":    130,   # Window to search for the pole top
    "pole_exclude_recent":    20,   # Ignore last N days when searching for pole top
    "vcp_base_days":          60,   # Max days after pole top used to measure base
    "min_base_bars":          15,   # Base must span at least this many bars
    "min_base_depth_pct":      3,   # Base must pull back at least 3% from pole top
    "max_base_depth_pct":     25,   # Base must not pull back more than this
    "vol_contraction_ratio":  0.90, # 20d avg vol < 90% of 90d avg vol
    "near_high_threshold":    0.85, # CMP within 15% of pole high
    "min_contraction_ratio":  0.70, # ↑ was 0.55 — base range <= 70% of pole range
}

FILTERS = [
    "F1_EMA_Trend",        # CMP > EMA21 > EMA50 > EMA200
    "F2_Pole_Size",        # min_pole_pct <= Pole% <= max_pole_pct
    "F3_Base_Formed",      # Base has >= min_base_bars
    "F4_Contraction",      # Base range <= min_contraction_ratio * pole range
    "F5a_Base_Depth_Min",  # Base pulled back >= min_base_depth_pct
    "F5b_Base_Depth_Max",  # Base pulled back <= max_base_depth_pct
    "F6_Volume_Dryup",     # 20d avg vol < vol_contraction_ratio * 90d avg vol
    "F7_Near_Breakout",    # CMP >= near_high_threshold * pole_high
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
            return [
                f"{s['symbol']}.NS"
                for s in resp.json()["data"]
                if s["symbol"] != official_name
            ]
        print(f"  ❌ NSE API {resp.status_code} for {sector_key}")
        return []
    except Exception as e:
        print(f"  ❌ NSE Error ({sector_key}): {e}")
        return []


def detect_vcp(ticker: str, sector: str, cfg: dict, filter_fails: dict) -> dict | None:
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
        # Full stack required: CMP > EMA21 > EMA50 > EMA200
        # Confirms a healthy Stage 2 uptrend across all timeframes.
        ema21  = float(close.ewm(span=21,  adjust=False).mean().iloc[-1])
        ema50  = float(close.ewm(span=50,  adjust=False).mean().iloc[-1])
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

        if not (cmp > ema21 > ema50 > ema200):
            filter_fails["F1_EMA_Trend"] += 1
            return None

        # ── F2: POLE SIZE (with upper cap) ───────────────────────────────────
        # Find highest close in lookback window, excluding the most recent
        # pole_exclude_recent bars (so pole top is never "today")
        exclude       = cfg["pole_exclude_recent"]
        search_window = close.iloc[-(cfg["pole_lookback_days"] + exclude) : len(close) - exclude]

        if len(search_window) < 20:
            filter_fails["F2_Pole_Size"] += 1
            return None

        pole_high     = float(search_window.max())
        pole_high_idx = search_window.idxmax()

        # Trough in pole_trough_window days BEFORE the pole top
        # Using 30 days (was 60) — finds the base of the RECENT sharp move,
        # not a trough from months ago (which inflated NALCO's pole to 88%)
        pre_peak = close.loc[:pole_high_idx].tail(cfg["pole_trough_window"])
        if len(pre_peak) < 5:
            filter_fails["F2_Pole_Size"] += 1
            return None
        pole_low = float(pre_peak.min())

        pole_pct = ((pole_high - pole_low) / pole_low) * 100

        # Both too-small AND too-large poles are rejected
        if not (cfg["min_pole_pct"] <= pole_pct <= cfg["max_pole_pct"]):
            filter_fails["F2_Pole_Size"] += 1
            return None

        # ── F3: BASE HAS ENOUGH BARS ─────────────────────────────────────────
        post_peak   = close.loc[pole_high_idx:]
        base_window = post_peak.tail(cfg["vcp_base_days"])

        if len(base_window) < cfg["min_base_bars"]:
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

        # ── F5a: MINIMUM BASE DEPTH ──────────────────────────────────────────
        base_depth_pct = ((pole_high - base_low) / pole_high) * 100
        if base_depth_pct < cfg["min_base_depth_pct"]:
            filter_fails["F5a_Base_Depth_Min"] += 1
            return None

        # ── F5b: MAXIMUM BASE DEPTH ──────────────────────────────────────────
        if base_depth_pct > cfg["max_base_depth_pct"]:
            filter_fails["F5b_Base_Depth_Max"] += 1
            return None

        # ── F6: VOLUME DRY-UP ────────────────────────────────────────────────
        avg_vol_20 = float(volume.tail(20).mean())
        avg_vol_90 = float(volume.tail(90).mean())
        vol_ratio  = (avg_vol_20 / avg_vol_90) if avg_vol_90 > 0 else 999
        if vol_ratio > cfg["vol_contraction_ratio"]:
            filter_fails["F6_Volume_Dryup"] += 1
            return None

        # ── F7: NEAR BREAKOUT ────────────────────────────────────────────────
        if cmp < pole_high * cfg["near_high_threshold"]:
            filter_fails["F7_Near_Breakout"] += 1
            return None

        # ── ALL PASSED ───────────────────────────────────────────────────────
        return {
            "Ticker":            ticker,
            "Sector":            sector,
            "CMP":               round(cmp, 2),
            "Pole_%":            round(pole_pct, 2),
            "Base_Depth_%":      round(base_depth_pct, 2),
            "Base_Bars":         len(base_window),
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
    print("\n" + "═" * 64)
    print("  📊  FILTER ELIMINATION REPORT")
    print("═" * 64)
    print(f"  {'Filter':<27}  {'Eliminated':>10}  {'% of Scanned':>12}")
    print("─" * 64)
    cumulative = 0
    for f in FILTERS:
        n   = filter_fails.get(f, 0)
        pct = (n / total * 100) if total > 0 else 0
        cumulative += n
        bar = "█" * int(pct / 4)
        print(f"  {f:<27}  {n:>10}  {pct:>11.1f}%  {bar}")
    print("═" * 64)
    passed = total - cumulative
    print(f"  Total scanned : {total}")
    print(f"  Total passed  : {max(passed, 0)}")
    print("═" * 64 + "\n")

    if filter_fails:
        worst = max(filter_fails, key=filter_fails.get)
        hints = {
            "F1_EMA_Trend":       "Remove EMA200 gate — use only ema50 > ema200 as a soft check",
            "F2_Pole_Size":       "Adjust min_pole_pct (lower) or max_pole_pct (higher) or pole_trough_window",
            "F3_Base_Formed":     "Lower min_base_bars (e.g. 10)",
            "F4_Contraction":     "Raise min_contraction_ratio (e.g. 0.80)",
            "F5a_Base_Depth_Min": "Lower min_base_depth_pct (e.g. 2)",
            "F5b_Base_Depth_Max": "Raise max_base_depth_pct (e.g. 30)",
            "F6_Volume_Dryup":    "Raise vol_contraction_ratio (e.g. 0.95)",
            "F7_Near_Breakout":   "Lower near_high_threshold (e.g. 0.80)",
        }
        print(f"  🔍 Bottleneck : {worst} ({filter_fails[worst]} stocks)")
        print(f"  💡 Next step  : {hints.get(worst, 'Relax this filter in CFG')}\n")


def run_sniper():
    print("\n🎯 --- VCP SNIPER SCAN ---\n")
    print("  CFG snapshot:")
    for k, v in CFG.items():
        print(f"    {k:<30} = {v}")
    print()

    if not os.path.exists("active_sectors.json"):
        print("❌ active_sectors.json not found.")
        return

    with open("active_sectors.json", "r") as f:
        active_sectors = json.load(f)

    results      = []
    filter_fails = defaultdict(int)
    total_stocks = 0
    seen_tickers = set()

    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂  {sector} → {len(tickers)} tickers")

        for ticker in tickers:
            total_stocks += 1
            hit = detect_vcp(ticker, sector, CFG, filter_fails)
            if hit:
                if ticker not in seen_tickers:
                    seen_tickers.add(ticker)
                    results.append(hit)
                    print(
                        f"  ✅ {ticker.ljust(14)} | "
                        f"Pole: {hit['Pole_%']}%  "
                        f"Depth: {hit['Base_Depth_%']}%  "
                        f"Bars: {hit['Base_Bars']}  "
                        f"Contraction: {hit['Contraction_Ratio']}  "
                        f"Vol: {hit['Vol_Ratio_20_90']}  "
                        f"→ Pivot ₹{hit['Pivot_Price']}"
                    )
                else:
                    print(f"  ♻️  {ticker} (duplicate sector, skipped)")
            time.sleep(0.05)

    print_filter_report(filter_fails, total_stocks)

    if results:
        results.sort(key=lambda x: (x["Contraction_Ratio"], x["Dist_From_High_%"]))
        pd.DataFrame(results).to_csv("sniper_candidates.csv", index=False)

        msg  = "🎯 *VCP SNIPER — Stage 2 Bases*\n"
        msg += "`TICKER       POLE%  DEPTH%  BARS  RATIO  PIVOT`\n"
        for r in results[:15]:
            msg += (
                f"`{r['Ticker'].ljust(12)} "
                f"{str(r['Pole_%']).ljust(6)} "
                f"{str(r['Base_Depth_%']).ljust(7)} "
                f"{str(r['Base_Bars']).ljust(5)} "
                f"{str(r['Contraction_Ratio']).ljust(6)} "
                f"₹{r['Pivot_Price']}`\n"
            )
        if TELEGRAM_TOKEN and CHAT_ID:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            )
        print(f"✨ {len(results)} unique VCP candidates → sniper_candidates.csv")
    else:
        print("ℹ️  No stocks passed all filters. See report above.\n")


if __name__ == "__main__":
    run_sniper()
