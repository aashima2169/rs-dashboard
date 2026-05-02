import os, requests, json, time
import pandas as pd
import numpy as np
import yfinance as yf
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ─────────────────────────────────────────────
# CONFIG — tweak these to widen/narrow the scan
# ─────────────────────────────────────────────
CFG = {
    "min_pole_pct":          20,   # Pole must be at least this strong (%)
    "pole_lookback_days":   130,   # Window to search for the pole (trading days)
    "vcp_base_days":         60,   # Days after the pole top to check for contraction
    "max_base_depth_pct":    20,   # Base should not pull back more than this (%) from pole top
    "vol_contraction_ratio": 0.80, # Recent 20d avg volume must be < 80% of 90d avg volume
    "near_high_threshold":   0.88, # CMP must be within 12% of pole high to be near breakout
    "min_contraction_ratio": 0.50, # Base range must be ≤ 50% of the pole range (the "squeeze")
}


def get_stocks(sector_key: str) -> list[str]:
    """Fetches tickers dynamically from NSE API."""
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        if not official_name:
            print(f"  ⚠️  No NSE mapping found for sector key: {sector_key}")
            return []

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
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
        print(f"  ❌ NSE API returned {resp.status_code} for {sector_key}")
        return []
    except Exception as e:
        print(f"  ❌ NSE API Error for {sector_key}: {e}")
        return []


def detect_vcp(ticker: str, sector: str, cfg: dict) -> dict | None:
    """
    Returns a result dict if the stock passes VCP criteria, else None.

    VCP Logic (Mark Minervini):
    ──────────────────────────
    1.  Stage 2 Uptrend  : SMA50 > SMA150 > SMA200, CMP above all three
    2.  The Pole         : A strong prior move (≥ min_pole_pct) found by
                           locating the highest point in the last 130 days,
                           then measuring the rally from the trough BEFORE
                           that peak (within the 60 days preceding the peak)
    3.  Base / Contraction: After the pole top, price consolidates in a
                            shrinking range — the base range must be tighter
                            than the pole by min_contraction_ratio
    4.  Depth check      : Base must not pull back more than max_base_depth_pct
                           from the pole high (shallow = strong demand)
    5.  Volume Dry-up    : 20-day avg volume < 80% of 90-day avg (supply drying)
    6.  Near Breakout    : CMP within near_high_threshold of pole high
    """
    try:
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 250:
            return None

        # Flatten multi-index if yfinance returns one
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close  = df["Close"].squeeze()
        volume = df["Volume"].squeeze()
        cmp    = float(close.iloc[-1])

        # ── 1. STAGE 2 UPTREND ──────────────────────────────────────────────
        sma50  = float(close.rolling(50).mean().iloc[-1])
        sma150 = float(close.rolling(150).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1])

        stage2 = (
            cmp    > sma50   and
            cmp    > sma150  and
            cmp    > sma200  and
            sma50  > sma150  and
            sma150 > sma200
        )
        if not stage2:
            return None

        # ── 2. POLE DETECTION ───────────────────────────────────────────────
        # Find the highest close in the last `pole_lookback_days` days
        lookback_close = close.tail(cfg["pole_lookback_days"])
        pole_high      = float(lookback_close.max())
        pole_high_idx  = lookback_close.idxmax()

        # Find the trough in the 60 trading days BEFORE the pole high
        pre_peak_window = close.loc[:pole_high_idx].tail(60)
        if len(pre_peak_window) < 10:
            return None
        pole_low = float(pre_peak_window.min())

        pole_pct = ((pole_high - pole_low) / pole_low) * 100
        if pole_pct < cfg["min_pole_pct"]:
            return None

        # ── 3. BASE / CONTRACTION ───────────────────────────────────────────
        # Take the portion of price history AFTER the pole high
        post_peak_close = close.loc[pole_high_idx:]
        base_window     = post_peak_close.tail(cfg["vcp_base_days"])

        if len(base_window) < 5:
            # Stock only just hit new high — no base formed yet
            return None

        base_high  = float(base_window.max())
        base_low   = float(base_window.min())
        base_range = base_high - base_low
        pole_range = pole_high - pole_low

        # Contraction: base range must be meaningfully tighter than the pole
        contraction_ratio = base_range / pole_range
        if contraction_ratio > cfg["min_contraction_ratio"]:
            return None

        # ── 4. BASE DEPTH (pullback from pole high must be shallow) ─────────
        base_depth_pct = ((pole_high - base_low) / pole_high) * 100
        if base_depth_pct > cfg["max_base_depth_pct"]:
            return None

        # ── 5. VOLUME DRY-UP ────────────────────────────────────────────────
        avg_vol_20 = float(volume.tail(20).mean())
        avg_vol_90 = float(volume.tail(90).mean())
        if avg_vol_90 == 0:
            return None
        vol_ratio = avg_vol_20 / avg_vol_90
        if vol_ratio > cfg["vol_contraction_ratio"]:
            return None

        # ── 6. NEAR BREAKOUT (CMP close to pole high = tight pivot) ────────
        if cmp < pole_high * cfg["near_high_threshold"]:
            return None

        # ── PASSED ALL FILTERS → build result ───────────────────────────────
        distance_from_high_pct = round(((pole_high - cmp) / pole_high) * 100, 2)

        return {
            "Ticker":            ticker,
            "Sector":            sector,
            "CMP":               round(cmp, 2),
            "Pole_%":            round(pole_pct, 2),
            "Base_Depth_%":      round(base_depth_pct, 2),
            "Contraction_Ratio": round(contraction_ratio, 2),  # lower = tighter squeeze
            "Vol_Ratio_20_90":   round(vol_ratio, 2),          # lower = more dry-up
            "Dist_From_High_%":  distance_from_high_pct,       # lower = closer to breakout
            "Pivot_Price":       round(pole_high * 1.01, 2),   # 1% above pole high = buy trigger
        }

    except Exception as e:
        print(f"  ⚠️  Error analysing {ticker}: {e}")
        return None


def run_sniper():
    print("\n🎯 --- VCP SNIPER SCAN (STAGE 2 + POLE + CONTRACTION + VOLUME) ---\n")

    if not os.path.exists("active_sectors.json"):
        print("❌ active_sectors.json not found.")
        return

    with open("active_sectors.json", "r") as f:
        active_sectors = json.load(f)

    results = []

    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂  {sector} → {len(tickers)} tickers")

        for ticker in tickers:
            hit = detect_vcp(ticker, sector, CFG)
            if hit:
                results.append(hit)
                print(
                    f"  ✅ {ticker.ljust(14)} | "
                    f"Pole: {hit['Pole_%']}% | "
                    f"Depth: {hit['Base_Depth_%']}% | "
                    f"Contraction: {hit['Contraction_Ratio']} | "
                    f"Vol: {hit['Vol_Ratio_20_90']} | "
                    f"→ Pivot: {hit['Pivot_Price']}"
                )
            time.sleep(0.05)

    # ── SAVE + NOTIFY ────────────────────────────────────────────────────────
    if results:
        results.sort(key=lambda x: (x["Contraction_Ratio"], x["Dist_From_High_%"]))
        df_out = pd.DataFrame(results)
        df_out.to_csv("step1_vcp_candidates.csv", index=False)

        msg  = "🎯 *VCP SNIPER — Stage 2 Bases*\n"
        msg += "`TICKER       POLE%  DEPTH%  RATIO  PIVOT`\n"
        for r in results[:15]:
            msg += (
                f"`{r['Ticker'].ljust(12)} "
                f"{str(r['Pole_%']).ljust(6)} "
                f"{str(r['Base_Depth_%']).ljust(7)} "
                f"{str(r['Contraction_Ratio']).ljust(6)} "
                f"{r['Pivot_Price']}`\n"
            )

        if TELEGRAM_TOKEN and CHAT_ID:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            )

        print(f"\n✨ Done — {len(results)} VCP candidates saved to step1_vcp_candidates.csv")
    else:
        print("\nℹ️  No stocks passed all VCP filters. Try relaxing thresholds in CFG.")


if __name__ == "__main__":
    run_sniper()
