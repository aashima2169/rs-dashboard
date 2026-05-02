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
# Changes from last run (based on filter elimination report):
#   min_pole_pct          20 → 15   (F2 was killing 12.3%)
#   vol_contraction_ratio 0.80 → 0.90 (F6 was killing 9.4%)
#   pole_exclude_recent   NEW: exclude last 10 days from pole search
#                         so post-peak base always has room to form (fixes F3)
#   EMA trend             CMP > EMA21 > EMA50 > EMA200
#                       → CMP > EMA50 > EMA200 only (fixes F1 bottleneck)
# ─────────────────────────────────────────────────────────────────────────────
CFG = {
    "min_pole_pct":           15,   # ↓ was 20
    "pole_lookback_days":    130,   # window to search for pole top
    "pole_exclude_recent":    10,   # ★ NEW: ignore last N days when finding pole top
                                    #   ensures post-peak base window always exists
    "vcp_base_days":          60,   # days after pole top to measure base
    "max_base_depth_pct":     25,   # ↑ was 20 (slight buffer for deeper bases)
    "vol_contraction_ratio":  0.90, # ↑ was 0.80 (less strict volume dry-up)
    "near_high_threshold":    0.85, # ↑ was 0.88 (wider breakout proximity)
    "min_contraction_ratio":  0.55, # ↑ was 0.50 (slight buffer for base tightness)
}

FILTERS = [
    "F1_EMA_Trend",       # CMP > EMA50 > EMA200
    "F2_Pole_Size",       # Pole >= min_pole_pct
    "F3_Base_Formed",     # Post-peak base has enough bars
    "F4_Contraction",     # Base range <= contraction_ratio * pole range
    "F5_Base_Depth",      # Pullback from pole top <= max_base_depth_pct
    "F6_Volume_Dryup",    # 20d avg vol < vol_contraction_ratio * 90d avg vol
    "F7_Near_Breakout",   # CMP within near_high_threshold of pole top
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
        # Relaxed: only require CMP > EMA50 > EMA200
        # (EMA21 > EMA50 was too strict — valid bases often dip EMA21 briefly)
        ema50  = float(close.ewm(span=50,  adjust=False).mean().iloc[-1])
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
        ema21  = float(close.ewm(span=21,  adjust=False).mean().iloc[-1])  # kept for output only

        if not (cmp > ema50 > ema200):
            filter_fails["F1_EMA_Trend"] += 1
            return None

        # ── F2: POLE SIZE ────────────────────────────────────────────────────
        # Search window = last pole_lookback_days, but EXCLUDE the most recent
        # pole_exclude_recent bars so the pole top is never "today"
        # This guarantees a post-peak window exists for base measurement (fixes F3)
        exclude = cfg["pole_exclude_recent"]
        search_window = close.iloc[-(cfg["pole_lookback_days"] + exclude) : len(close) - exclude]

        if len(search_window) < 20:
            filter_fails["F2_Pole_Size"] += 1
            return None

        pole_high     = float(search_window.max())
        pole_high_idx = search_window.idxmax()

        # Trough in the 60 days before the pole top
        pre_peak = close.loc[:pole_high_idx].tail(60)
        if len(pre_peak) < 10:
            filter_fails["F2_Pole_Size"] += 1
            return None
        pole_low = float(pre_peak.min())

        pole_pct = ((pole_high - pole_low) / pole_low) * 100
        if pole_pct < cfg["min_pole_pct"]:
            filter_fails["F2_Pole_Size"] += 1
            return None

        # ── F3: BASE HAS FORMED ──────────────────────────────────────────────
        # Everything after the pole top = the base / consolidation zone
        post_peak   = close.loc[pole_high_idx:]
        base_window = post_peak.tail(cfg["vcp_base_days"])

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
    print("\n" + "═" * 60)
    print("  📊  FILTER ELIMINATION REPORT")
    print("═" * 60)
    print(f"  {'Filter':<25}  {'Eliminated':>10}  {'% of Scanned':>12}")
    print("─" * 60)
    cumulative = 0
    for f in FILTERS:
        n   = filter_fails.get(f, 0)
        pct = (n / total * 100) if total > 0 else 0
        cumulative += n
        bar = "█" * int(pct / 4)
        print(f"  {f:<25}  {n:>10}  {pct:>11.1f}%  {bar}")
    print("═" * 60)
    passed = total - cumulative
    print(f"  Total scanned : {total}")
    print(f"  Total passed  : {max(passed, 0)}")
    print("═" * 60 + "\n")

    if filter_fails:
        worst = max(filter_fails, key=filter_fails.get)
        hints = {
            "F1_EMA_Trend":    "Try removing EMA200 check — use only CMP > EMA50",
            "F2_Pole_Size":    "Lower min_pole_pct further (e.g. 12) or increase pole_lookback_days",
            "F3_Base_Formed":  "Increase pole_exclude_recent (e.g. 15) or reduce vcp_base_days minimum",
            "F4_Contraction":  "Raise min_contraction_ratio (e.g. 0.65–0.70)",
            "F5_Base_Depth":   "Raise max_base_depth_pct (e.g. 30–35)",
            "F6_Volume_Dryup": "Raise vol_contraction_ratio (e.g. 0.95) or remove this filter",
            "F7_Near_Breakout":"Lower near_high_threshold (e.g. 0.80)",
        }
        print(f"  🔍 Bottleneck : {worst} ({filter_fails[worst]} stocks)")
        print(f"  💡 Next step  : {hints.get(worst, 'Relax this filter in CFG')}\n")


def run_sniper():
    print("\n🎯 --- VCP SNIPER SCAN (EMA TREND + POLE + CONTRACTION + VOLUME) ---\n")
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

    print_filter_report(filter_fails, total_stocks)

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
        print("ℹ️  No stocks passed all filters. See report above.\n")


if __name__ == "__main__":
    run_sniper()
