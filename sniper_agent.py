import os
import json
import time
import warnings
import logging
from collections import defaultdict

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.simplefilter(action="ignore", category=FutureWarning)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger()

CFG = {
    "rs_threshold": 0.98,

    "min_pole_pct": 12,
    "max_pole_pct": 70,
    "pole_lookback_days": 200,
    "pole_exclude_recent": 5,
    "pole_trough_window": 50,

    "vcp_base_days": 70,
    "min_base_bars": 20,

    "vol_contraction_ratio": 0.9,
    "near_high_threshold": 0.9,

    "sleep": 0.03,
}

FILTERS = [
    "NO_DATA",
    "RS_FAIL",
    "F1_TREND",
    "F2_POLE",
    "F3_BASE",
    "F4_SWING",
    "F5_DEPTH",
    "F6_VOLUME",
    "F7_BREAKOUT",
]

def download(ticker):
    try:
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=True)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except:
        return None

def get_stocks(sector):
    try:
        with open("config.json") as f:
            cfg = json.load(f)

        name = cfg["nse_index_mapping"].get(sector)
        if not name:
            return []

        session = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0"}

        session.get("https://www.nseindia.com", headers=headers)

        url = f"https://www.nseindia.com/api/equity-stockIndices?index={name.replace(' ', '%20')}"
        res = session.get(url, headers=headers)

        return [f"{x['symbol']}.NS" for x in res.json()["data"] if x["symbol"] != name]

    except:
        return []

def compute_rs(stock_df, nifty_df):
    try:
        s_ret = stock_df["Close"].pct_change(100).iloc[-1]
        n_ret = nifty_df["Close"].pct_change(100).iloc[-1]
        return (1 + s_ret) / (1 + n_ret)
    except:
        return 0

def find_swings(series, window=5):
    highs, lows = [], []
    for i in range(window, len(series) - window):
        chunk = series[i - window:i + window]
        if series[i] == chunk.max():
            highs.append((i, series[i]))
        if series[i] == chunk.min():
            lows.append((i, series[i]))
    return highs, lows

def check_vcp_contraction(base):
    highs, lows = find_swings(base.values)

    if len(highs) < 3 or len(lows) < 3:
        return False

    highs = sorted(highs, key=lambda x: x[0])
    lows = sorted(lows, key=lambda x: x[0])

    contractions = []

    for i in range(min(len(highs), len(lows)) - 1):
        high = highs[i][1]
        low = lows[i][1]

        if high == 0:
            continue

        drop = (high - low) / high
        contractions.append(drop)

    if len(contractions) < 2:
        return False

    # require visible contraction trend
    score = 0
    for i in range(len(contractions) - 1):
        if contractions[i+1] < contractions[i]:
            score += 1

    return score >= 1

def detect_vcp(ticker, sector, nifty_df):
    df = download(ticker)
    if df is None or len(df) < 200:
        return None, "NO_DATA"

    close = df["Close"]
    volume = df["Volume"]

    rs = compute_rs(df, nifty_df)
    if rs < CFG["rs_threshold"]:
        return None, "RS_FAIL"

    ema50 = close.ewm(span=50).mean().iloc[-1]
    ema200 = close.ewm(span=200).mean().iloc[-1]

    if not (ema50 > ema200 or close.iloc[-1] > ema50):
        return None, "F1_TREND"

    search = close.iloc[-(CFG["pole_lookback_days"] + 5):-5]
    if len(search) < 30:
        return None, "F2_POLE"

    pole_high = search.max()
    pole_idx = search.idxmax()

    trough = close.loc[:pole_idx].tail(CFG["pole_trough_window"])
    if len(trough) < 10:
        return None, "F2_POLE"

    pole_low = trough.min()
    pole_pct = ((pole_high - pole_low) / pole_low) * 100

    if not (CFG["min_pole_pct"] <= pole_pct <= CFG["max_pole_pct"]):
        return None, "F2_POLE"

    base = close.loc[pole_idx:].tail(CFG["vcp_base_days"])
    if len(base) < CFG["min_base_bars"]:
        return None, "F3_BASE"

    if not check_vcp_contraction(base):
        return None, "F4_SWING"

    # strict volatility cap (kills Oil-type charts)
    base_range = (base.max() - base.min()) / base.max()
    if base_range > 0.18:
        return None, "F4_SWING"

    base_low = base.min()
    depth = ((pole_high - base_low) / pole_high) * 100

    if depth > 35:
        return None, "F5_DEPTH"

    vols = volume.loc[base.index]
    early = vols.iloc[:len(vols)//2].mean()
    late = vols.iloc[len(vols)//2:].mean()

    if late > CFG["vol_contraction_ratio"] * early:
        return None, "F6_VOLUME"

    cmp = close.iloc[-1]

    if cmp < pole_high * CFG["near_high_threshold"]:
        return None, "F7_BREAKOUT"

    return {
        "Ticker": ticker,
        "Sector": sector,
        "RS": round(rs, 2),
        "Pole_%": round(pole_pct, 2),
        "Depth_%": round(depth, 2),
        "Pivot": round(pole_high * 1.01, 2),
    }, "PASS"

def run():
    print("\n🎯 VCP SNIPER (STRICT VISUAL MODE)\n")

    if not os.path.exists("active_sectors.json"):
        return

    with open("active_sectors.json") as f:
        sectors = json.load(f)

    nifty = download("^NSEI")
    if nifty is None:
        return

    results = []
    fails = defaultdict(int)

    for sector in sectors:
        tickers = get_stocks(sector)
        print(f"Scanning {sector} ({len(tickers)})")

        for t in tickers:
            res, reason = detect_vcp(t, sector, nifty)

            if res:
                results.append(res)
                print(f"✅ {t} | RS {res['RS']} | ₹{res['Pivot']}")
            else:
                fails[reason] += 1

            time.sleep(CFG["sleep"])

    print("\n📊 FILTER REPORT")
    for k in FILTERS:
        print(f"{k}: {fails[k]}")

    if results:
        pd.DataFrame(results).to_csv("sniper_candidates.csv", index=False)
        print(f"\n✅ Found {len(results)} CLEAN VCP setups")
    else:
        print("\n❌ No clean setups found")

if __name__ == "__main__":
    run()
