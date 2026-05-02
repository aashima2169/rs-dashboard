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
# RELAXED CONFIG
# ─────────────────────────────────────────────────────────────────────────────
CFG = {
    "use_ema21": False,
    "min_trend_up_days": 10,

    "pole_lookback_days": 200,
    "pole_exclude_recent": 5,
    "pole_trough_window": 50,

    "min_pole_pct": 8,
    "max_pole_pct": 70,

    "vcp_base_days": 75,
    "min_base_bars": 20,

    "min_base_depth_pct": 2,
    "max_base_depth_pct": 35,

    "min_contraction_ratio": 0.75,

    "vol_contraction_ratio": 0.95,
    "breakout_vol_mult": 1.05,

    "near_high_threshold": 0.88,

    "max_results": 20,
    "sleep_seconds": 0.03,
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
]

# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCH
# ─────────────────────────────────────────────────────────────────────────────
def safe_download(ticker):
    try:
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=True)
        if df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df.dropna()
    except:
        return None

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

# ─────────────────────────────────────────────────────────────────────────────
# VCP DETECTION
# ─────────────────────────────────────────────────────────────────────────────
def detect_vcp(ticker, sector, cfg):
    df = safe_download(ticker)
    if df is None or len(df) < 200:
        return None, "NO_DATA"

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    cmp = close.iloc[-1]

    # ── F1 TREND (RELAXED)
    ema21 = close.ewm(span=21).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    ema200 = close.ewm(span=200).mean().iloc[-1]

    trend_ok = (ema50 > ema200) or (cmp > ema50)
    if cfg["use_ema21"]:
        trend_ok = trend_ok or (ema21 > ema50)

    if not trend_ok:
        return None, "F1_EMA_Trend"

    # ── F2 POLE
    exclude = cfg["pole_exclude_recent"]
    search = close.iloc[-(cfg["pole_lookback_days"] + exclude):-exclude]

    if len(search) < 30:
        return None, "F2_Pole_Size"

    pole_high = search.max()
    pole_idx = search.idxmax()

    trough = close.loc[:pole_idx].tail(cfg["pole_trough_window"])
    if len(trough) < 10:
        return None, "F2_Pole_Size"

    pole_low = trough.min()
    pole_pct = ((pole_high - pole_low) / pole_low) * 100

    if not (cfg["min_pole_pct"] <= pole_pct <= cfg["max_pole_pct"]):
        return None, "F2_Pole_Size"

    # ── F3 BASE
    base = close.loc[pole_idx:].tail(cfg["vcp_base_days"])
    if len(base) < cfg["min_base_bars"]:
        return None, "F3_Base_Formed"

    base_high = base.max()
    base_low = base.min()

    # ── F4 CONTRACTION
    pole_range = pole_high - pole_low
    base_range = base_high - base_low

    contraction = base_range / pole_range if pole_range > 0 else 999

    if contraction > cfg["min_contraction_ratio"]:
        return None, "F4_Contraction"

    # ── F5 DEPTH
    depth = ((pole_high - base_low) / pole_high) * 100

    if depth < cfg["min_base_depth_pct"]:
        return None, "F5a_Base_Depth_Min"
    if depth > cfg["max_base_depth_pct"]:
        return None, "F5b_Base_Depth_Max"

    # ── F6 VOLUME
    v1 = volume.tail(20).mean()
    v2 = volume.tail(90).mean()

    if v1 / v2 > cfg["vol_contraction_ratio"]:
        return None, "F6_Volume_Dryup"

    # ── F7 NEAR BREAKOUT
    if cmp < pole_high * cfg["near_high_threshold"]:
        return None, "F7_Near_Breakout"

    # ── F8 BREAKOUT VOLUME
    if volume.iloc[-1] < cfg["breakout_vol_mult"] * base.mean():
        return None, "F8_Breakout_Volume"

    return {
        "Ticker": ticker,
        "Sector": sector,
        "CMP": round(cmp, 2),
        "Pole_%": round(pole_pct, 2),
        "Depth_%": round(depth, 2),
        "Contraction": round(contraction, 2),
        "Pivot": round(pole_high * 1.01, 2),
    }, "PASS"

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def run_sniper():
    print("\n🎯 --- VCP SNIPER START ---")

    if not os.path.exists("active_sectors.json"):
        print("No sector file found")
        return

    with open("active_sectors.json") as f:
        sectors = json.load(f)

    results = []
    fails = defaultdict(int)
    total = 0

    for sector in sectors:
        tickers = get_stocks(sector)
        print(f"Scanning {sector} ({len(tickers)})")

        for t in tickers:
            total += 1
            res, reason = detect_vcp(t, sector, CFG)

            if res:
                results.append(res)
                print(f"✅ {t} | {res['Pole_%']}% | ₹{res['Pivot']}")
            else:
                fails[reason] += 1

            time.sleep(CFG["sleep_seconds"])

    print("\n📊 FILTER REPORT")
    for k in FILTERS:
        print(f"{k}: {fails[k]}")

    if results:
        pd.DataFrame(results).to_csv("sniper_candidates.csv", index=False)
        print(f"\n✅ Found {len(results)} candidates")
    else:
        print("\n❌ No stocks passed")

if __name__ == "__main__":
    run_sniper()
