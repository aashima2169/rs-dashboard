import os, requests, json, time
import pandas as pd
import yfinance as yf
import warnings
from collections import defaultdict

warnings.simplefilter(action='ignore', category=FutureWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID")

CFG = {
    "min_pole_pct": 15,
    "max_pole_pct": 45,
    "pole_trough_window": 30,
    "pole_lookback_days": 130,
    "pole_exclude_recent": 20,
    "vcp_base_days": 60,
    "min_base_bars": 18,
    "min_base_depth_pct": 5,
    "max_base_depth_pct": 22,
    "base_tightening_ratio": 0.65,
    "vol_contraction_ratio": 0.85,
    "near_high_threshold": 0.88,
    "min_contraction_ratio": 0.60,
}

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

        if resp.status_code != 200:
            print(f"❌ NSE API {resp.status_code} for {sector_key}")
            return []

        data = resp.json()

        stocks = []
        for s in data.get("data", []):
            symbol = s.get("symbol", "").strip()

            # 🔥 CORE FIX
            if not symbol:
                continue

            # Skip index rows (they always start with NIFTY)
            if symbol.upper().startswith("NIFTY"):
                continue

            stocks.append(f"{symbol}.NS")

        return stocks

    except Exception as e:
        print(f"❌ NSE Error ({sector_key}): {e}")
        return []


def detect_vcp(ticker, sector, cfg, filter_fails):
    try:
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 250:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close  = df["Close"]
        high   = df["High"]
        low    = df["Low"]
        volume = df["Volume"]

        cmp = float(close.iloc[-1])

        # ── F1 TREND ──
        ema21  = float(close.ewm(span=21).mean().iloc[-1])
        ema50  = float(close.ewm(span=50).mean().iloc[-1])
        ema200 = float(close.ewm(span=200).mean().iloc[-1])

        trend_ok = ema21 > ema50 > ema200
        price_ok = cmp > ema50

        if not (trend_ok and price_ok):
            filter_fails["F1_EMA_Trend"] += 1
            return None

        # ── POLE ──
        exclude = cfg["pole_exclude_recent"]
        search  = close.iloc[-(cfg["pole_lookback_days"] + exclude):-exclude]

        pole_high = search.max()
        idx       = search.idxmax()

        pre = close.loc[:idx].tail(cfg["pole_trough_window"])
        pole_low = pre.min()

        pole_pct = ((pole_high - pole_low) / pole_low) * 100
        if not (cfg["min_pole_pct"] <= pole_pct <= cfg["max_pole_pct"]):
            filter_fails["F2_Pole_Size"] += 1
            return None

        # ── BASE ──
        base = close.loc[idx:].tail(cfg["vcp_base_days"])
        if len(base) < cfg["min_base_bars"]:
            filter_fails["F3_Base_Formed"] += 1
            return None

        base_high = base.max()
        base_low  = base.min()

        pole_range = pole_high - pole_low
        base_range = base_high - base_low

        if base_range / pole_range > cfg["min_contraction_ratio"]:
            filter_fails["F4_Contraction"] += 1
            return None

        # ── BASE TIGHTENING ──
        mid = len(base)//2
        r1 = base.iloc[:mid].max() - base.iloc[:mid].min()
        r2 = base.iloc[mid:].max() - base.iloc[mid:].min()

        if r1 == 0 or (r2/r1) > cfg["base_tightening_ratio"]:
            filter_fails["F4b_Base_Tightening"] += 1
            return None

        # ── ATR CONTRACTION ──
        tr = high - low
        atr = tr.rolling(14).mean()

        if (atr.iloc[-5:].mean() / atr.iloc[-30:-10].mean()) > 0.75:
            filter_fails["F4c_ATR_Contraction"] += 1
            return None

        # ── CANDLE COMPRESSION ──
        if ((high.tail(5)-low.tail(5)).mean() /
            (high.tail(30)-low.tail(30)).mean()) > 0.6:
            filter_fails["F4d_Candle_Compression"] += 1
            return None

        # ── DEPTH ──
        depth = ((pole_high - base_low)/pole_high)*100
        if depth < cfg["min_base_depth_pct"]:
            filter_fails["F5a_Base_Depth_Min"] += 1
            return None
        if depth > cfg["max_base_depth_pct"]:
            filter_fails["F5b_Base_Depth_Max"] += 1
            return None

        # ── VOLUME ──
        if (volume.tail(20).mean()/volume.tail(90).mean()) > cfg["vol_contraction_ratio"]:
            filter_fails["F6_Volume_Dryup"] += 1
            return None

        # ── NEAR BREAKOUT ──
        if cmp < pole_high * cfg["near_high_threshold"]:
            filter_fails["F7_Near_Breakout"] += 1
            return None

        return {
            "Ticker": ticker,
            "Sector": sector,
            "Score": round(100 - (r2/r1)*100, 0),
            "Price": round(cmp, 2)
        }

    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None


def run_sniper():
    print("\n🎯 VCP SNIPER (FINAL)\n")

    if not os.path.exists("active_sectors.json"):
        print("❌ active_sectors.json missing")
        return

    sectors = json.load(open("active_sectors.json"))

    results = []
    seen    = set()
    fails   = defaultdict(int)

    for s in sectors:
        tickers = get_stocks(s)
        print(f"Scanning {s} ({len(tickers)})")

        for t in tickers:
            r = detect_vcp(t, s, CFG, fails)
            if r and t not in seen:
                seen.add(t)
                results.append(r)

            time.sleep(0.05)

    df = pd.DataFrame(results).sort_values("Score", ascending=False)

    print("\n🏆 TOP VCP-LIKE CANDIDATES\n")
    print(df)

    df.to_csv("sniper_candidates.csv", index=False)


if __name__ == "__main__":
    run_sniper()
