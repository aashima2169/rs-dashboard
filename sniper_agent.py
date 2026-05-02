import os
import json
import time
import logging
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.simplefilter(action="ignore", category=FutureWarning)

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("vcp_sniper")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
CFG = {
    # trend
    "use_ema21": True,
    "min_trend_up_days": 20,

    # pole / base
    "pole_lookback_days": 180,
    "pole_exclude_recent": 10,
    "pole_trough_window": 40,
    "vcp_base_days": 60,
    "min_base_bars": 30,

    # depth / contraction
    "min_pole_pct": 10,          # loosened a bit
    "max_pole_pct": 60,
    "min_base_depth_pct": 3,
    "max_base_depth_pct": 30,
    "min_contraction_ratio": 0.60,  # loosened from 0.45

    # volume
    "vol_contraction_ratio": 0.85,   # compare base avg volume vs earlier base volume
    "breakout_vol_mult": 1.20,       # breakout day vol vs base avg

    # breakout proximity
    "near_high_threshold": 0.90,     # closer to pivot than before

    # output
    "max_results": 15,
    "sleep_seconds": 0.05,
}

FILTERS = [
    "NO_DATA",
    "F1_EMA_Trend",
    "F2_Pole_Size",
    "F3_Base_Formed",
    "F4_Contraction",
    "F5a_Base_Depth_Min",
    "F5b_Base_Depth_Max",
    "F6_Volume_Dryup",
    "F7_Near_Breakout",
    "F8_Breakout_Volume",
    "EXCEPTION",
]

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def safe_mean(s: pd.Series) -> float:
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.mean()) if len(s) else float("nan")

def safe_download(ticker: str, period: str = "2y") -> pd.DataFrame | None:
    try:
        df = yf.download(
            ticker,
            period=period,
            progress=False,
            auto_adjust=True,
            threads=False,
            group_by="column",
        )
        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        needed = {"Open", "High", "Low", "Close", "Volume"}
        if not needed.issubset(set(df.columns)):
            return None

        df = df.dropna(subset=["High", "Low", "Close", "Volume"]).copy()
        if df.empty:
            return None

        return df
    except Exception:
        logger.exception("download failed for %s", ticker)
        return None

def get_stocks(sector_key: str) -> list[str]:
    """
    Reads config.json -> nse_index_mapping[sector_key] and returns constituents.
    Example mapping value could be an NSE index name.
    """
    try:
        with open("config.json", "r") as f:
            config = json.load(f)

        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        if not official_name:
            logger.warning("No NSE mapping found for sector key: %s", sector_key)
            return []

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.nseindia.com/",
            "Accept": "application/json, text/plain, */*",
        }

        session = requests.Session()
        # warm-up request
        session.get("https://www.nseindia.com", headers=headers, timeout=10)

        url = (
            "https://www.nseindia.com/api/equity-stockIndices"
            f"?index={official_name.replace(' ', '%20')}"
        )
        resp = session.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        payload = resp.json()
        data = payload.get("data", [])
        tickers = []
        for row in data:
            sym = row.get("symbol")
            if sym and sym != official_name:
                tickers.append(f"{sym}.NS")

        # de-duplicate but preserve order
        return list(dict.fromkeys(tickers))

    except Exception:
        logger.exception("get_stocks failed for sector=%s", sector_key)
        return []

def _segment_stats(base_df: pd.DataFrame) -> tuple[list[float], list[float]]:
    """
    Split the base into 3 equal-ish parts and compute:
    - price range % for each segment
    - average volume for each segment
    """
    segments = np.array_split(base_df, 3)
    ranges = []
    vols = []

    for seg in segments:
        if len(seg) < 5:
            return [], []
        hi = float(seg["High"].max())
        lo = float(seg["Low"].min())
        rng_pct = ((hi - lo) / hi) * 100 if hi > 0 else np.nan
        ranges.append(rng_pct)
        vols.append(float(seg["Volume"].mean()))

    return ranges, vols

# ─────────────────────────────────────────────────────────────────────────────
# VCP DETECTOR
# ─────────────────────────────────────────────────────────────────────────────
def detect_vcp(ticker: str, sector: str, cfg: dict) -> tuple[dict | None, str]:
    df = safe_download(ticker, period="2y")
    if df is None or len(df) < 220:
        return None, "NO_DATA"

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    cmp = float(close.iloc[-1])

    # ── F1: trend filter
    ema21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
    ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

    trend_ok = (ema50 > ema200) and (cmp > ema50)
    if cfg["use_ema21"]:
        trend_ok = trend_ok and (ema21 > ema50)

    if not trend_ok:
        return None, "F1_EMA_Trend"

    # ── F2: find pole high in a prior window, excluding the most recent candles
    exclude = cfg["pole_exclude_recent"]
    start = max(0, len(close) - (cfg["pole_lookback_days"] + exclude))
    end = max(0, len(close) - exclude)
    search_window = close.iloc[start:end]

    if len(search_window) < 40:
        return None, "F2_Pole_Size"

    pole_high_pos = int(search_window.values.argmax() + start)
    pole_high = float(close.iloc[pole_high_pos])

    # Use a prior trough window before pole high
    trough_start = max(0, pole_high_pos - cfg["pole_trough_window"])
    pre_peak_window = close.iloc[trough_start:pole_high_pos]

    if len(pre_peak_window) < 10:
        return None, "F2_Pole_Size"

    pole_low = float(pre_peak_window.min())
    pole_pct = ((pole_high - pole_low) / pole_low) * 100 if pole_low > 0 else 0

    if not (cfg["min_pole_pct"] <= pole_pct <= cfg["max_pole_pct"]):
        return None, "F2_Pole_Size"

    # ── F3: base after pole high
    base_df = df.iloc[pole_high_pos:].tail(cfg["vcp_base_days"]).copy()
    if len(base_df) < cfg["min_base_bars"]:
        return None, "F3_Base_Formed"

    base_close = base_df["Close"].astype(float)
    base_high = float(base_df["High"].max())
    base_low = float(base_df["Low"].min())

    # ── F4: contraction check using 3 base segments
    ranges, vols = _segment_stats(base_df)
    if len(ranges) != 3:
        return None, "F4_Contraction"

    # later segments should be tighter than earlier ones
    if not (ranges[0] >= ranges[1] >= ranges[2]):
        return None, "F4_Contraction"

    pole_range_pct = ((pole_high - pole_low) / pole_low) * 100 if pole_low > 0 else 0
    base_range_pct = ((base_high - base_low) / base_high) * 100 if base_high > 0 else 999
    contraction_ratio = base_range_pct / pole_range_pct if pole_range_pct > 0 else 999

    if contraction_ratio > cfg["min_contraction_ratio"]:
        return None, "F4_Contraction"

    # ── F5: base depth
    base_depth_pct = ((pole_high - base_low) / pole_high) * 100 if pole_high > 0 else 0
    if base_depth_pct < cfg["min_base_depth_pct"]:
        return None, "F5a_Base_Depth_Min"
    if base_depth_pct > cfg["max_base_depth_pct"]:
        return None, "F5b_Base_Depth_Max"

    # ── F6: volume dry-up inside the base
    base_vol_early = float(base_df["Volume"].iloc[: max(5, len(base_df) // 3)].mean())
    base_vol_late = float(base_df["Volume"].iloc[-max(5, len(base_df) // 3):].mean())

    vol_ratio = base_vol_late / base_vol_early if base_vol_early > 0 else 999
    if vol_ratio > cfg["vol_contraction_ratio"]:
        return None, "F6_Volume_Dryup"

    # ── F7: near breakout
    if cmp < pole_high * cfg["near_high_threshold"]:
        return None, "F7_Near_Breakout"

    # ── F8: breakout volume confirmation
    base_avg_vol = float(base_df["Volume"].mean())
    breakout_vol = float(volume.iloc[-1])
    breakout_vol_mult = breakout_vol / base_avg_vol if base_avg_vol > 0 else 0

    if breakout_vol_mult < cfg["breakout_vol_mult"]:
        return None, "F8_Breakout_Volume"

    return {
        "Ticker": ticker,
        "Sector": sector,
        "CMP": round(cmp, 2),
        "Pole_%": round(pole_pct, 2),
        "Base_Depth_%": round(base_depth_pct, 2),
        "Base_Bars": int(len(base_df)),
        "Contraction_Ratio": round(contraction_ratio, 2),
        "Base_Range_%": round(base_range_pct, 2),
        "Vol_Ratio_LateVsEarly": round(vol_ratio, 2),
        "Breakout_Vol_Mult": round(breakout_vol_mult, 2),
        "Pivot_Price": round(pole_high * 1.01, 2),
    }, "PASS"

# ─────────────────────────────────────────────────────────────────────────────
# REPORTING
# ─────────────────────────────────────────────────────────────────────────────
def print_filter_report(filter_fails: dict, total: int):
    print("\n📊 FILTER ELIMINATION REPORT")
    print("-" * 50)
    for f in FILTERS:
        n = filter_fails.get(f, 0)
        pct = (n / total * 100) if total > 0 else 0
        print(f"{f:<22}: {n:>4} ({pct:>5.1f}%)")
    print("-" * 50)

def send_telegram_message(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception:
        logger.exception("telegram send failed")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def run_sniper():
    print("\n🎯 --- VCP SNIPER MISSION START ---")

    if not os.path.exists("active_sectors.json"):
        logger.error("active_sectors.json not found")
        return

    with open("active_sectors.json", "r") as f:
        active_sectors = json.load(f)

    results = []
    filter_fails = defaultdict(int)
    total_stocks = 0
    seen_tickers = set()

    for sector in active_sectors:
        tickers = get_stocks(sector)
        logger.info("Scanning sector=%s | tickers=%d", sector, len(tickers))

        for ticker in tickers:
            total_stocks += 1
            hit, reason = detect_vcp(ticker, sector, CFG)

            if hit and ticker not in seen_tickers:
                seen_tickers.add(ticker)
                results.append(hit)
                logger.info(
                    "HIT %s | pole=%s%% | depth=%s%% | pivot=₹%s",
                    ticker,
                    hit["Pole_%"],
                    hit["Base_Depth_%"],
                    hit["Pivot_Price"],
                )
            else:
                filter_fails[reason] += 1

            time.sleep(CFG["sleep_seconds"])

    print_filter_report(filter_fails, total_stocks)

    if results:
        results.sort(key=lambda x: (x["Contraction_Ratio"], x["Breakout_Vol_Mult"]))
        out = pd.DataFrame(results)
        out.to_csv("sniper_candidates.csv", index=False)
        logger.info("Saved %d candidates to sniper_candidates.csv", len(results))

        msg = "🎯 *VCP SNIPER — Stage 2 Bases*\n`TICKER       POLE%   DEPTH%  PIVOT   VOLx`\n"
        for r in results[:CFG["max_results"]]:
            msg += (
                f"`{r['Ticker'].ljust(10)} "
                f"{str(r['Pole_%']).ljust(7)} "
                f"{str(r['Base_Depth_%']).ljust(7)} "
                f"₹{str(r['Pivot_Price']).ljust(7)} "
                f"{str(r['Breakout_Vol_Mult'])}`\n"
            )
        send_telegram_message(msg)
    else:
        print("ℹ️ No stocks passed all filters.")

if __name__ == "__main__":
    run_sniper()
