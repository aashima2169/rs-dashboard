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
# ─────────────────────────────────────────────────────────────────────────────
CFG = {
    "min_pole_pct":           15,   # Pole must be at least this strong
    "max_pole_pct":           50,   # Cap — rejects extended trending stocks
    "pole_trough_window":     30,   # Days before pole top to find trough
    "pole_lookback_days":    130,   # Window to search for the pole top
    "pole_exclude_recent":    20,   # Ignore last N days when searching for pole top
    "vcp_base_days":          60,   # Max days after pole top used to measure base
    "min_base_bars":          15,   # Base must span at least this many bars
    "min_contraction_ratio":  0.70, # Base range <= 70% of pole range (PASS FOR MANUAL CHECK)
}

# Updated report list to match active filters
FILTERS = [
    "F1_EMA_Trend",        # EMA21 > EMA50 > EMA200 AND CMP > EMA50
    "F2_Pole_Size",        # min_pole_pct <= Pole% <= max_pole_pct
    "F3_Base_Formed",      # Base has >= min_base_bars
    "F4_Contraction",      # Base range <= min_contraction_ratio * pole range
]

def get_stocks(sector_key: str) -> list:
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        if not official_name:
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
        return []
    except Exception:
        return []

def detect_vcp(ticker: str, sector: str, cfg: dict, filter_fails: dict) -> dict | None:
    try:
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 250:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close  = df["Close"].squeeze()
        cmp    = float(close.iloc[-1])

        # ── F1: EMA TREND ────────────────────────────────────────────────────
        ema21  = float(close.ewm(span=21,  adjust=False).mean().iloc[-1])
        ema50  = float(close.ewm(span=50,  adjust=False).mean().iloc[-1])
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

        if not (ema21 > ema50 > ema200 and cmp > ema50):
            filter_fails["F1_EMA_Trend"] += 1
            return None

        # ── F2: POLE SIZE ────────────────────────────────────────────────────
        exclude       = cfg["pole_exclude_recent"]
        search_window = close.iloc[-(cfg["pole_lookback_days"] + exclude) : len(close) - exclude]
        if len(search_window) < 20:
            filter_fails["F2_Pole_Size"] += 1
            return None

        pole_high     = float(search_window.max())
        pole_high_idx = search_window.idxmax()
        pre_peak = close.loc[:pole_high_idx].tail(cfg["pole_trough_window"])
        if len(pre_peak) < 5:
            filter_fails["F2_Pole_Size"] += 1
            return None
        
        pole_low = float(pre_peak.min())
        pole_pct = ((pole_high - pole_low) / pole_low) * 100
        if not (cfg["min_pole_pct"] <= pole_pct <= cfg["max_pole_pct"]):
            filter_fails["F2_Pole_Size"] += 1
            return None

        # ── F3: BASE BARS ────────────────────────────────────────────────────
        post_peak   = close.loc[pole_high_idx:]
        base_window = post_peak.tail(cfg["vcp_base_days"])
        if len(base_window) < cfg["min_base_bars"]:
            filter_fails["F3_Base_Formed"] += 1
            return None

        # ── F4: CONTRACTION ──────────────────────────────────────────────────
        base_high  = float(base_window.max())
        base_low   = float(base_window.min())
        pole_range = pole_high - pole_low
        base_range = base_high - base_low
        contraction_ratio = (base_range / pole_range) if pole_range > 0 else 999
        
        if contraction_ratio > cfg["min_contraction_ratio"]:
            filter_fails["F4_Contraction"] += 1
            return None

        # ── EXIT POINT FOR MANUAL REVIEW ─────────────────────────────────────
        # Returning here bypasses F5, F6, and F7 completely
        return {
            "Ticker": ticker, 
            "Sector": sector, 
            "CMP": round(cmp, 2),
            "CTR": round(contraction_ratio, 2),
            "Pole_%": round(pole_pct, 2),
            "Pivot": round(pole_high * 1.01, 2)
        }

        # ── DISABLED FILTERS ─────────────────────────────────────────────────
        """
        # F5: Base Depth Check
        # F6: Volume Dry-up Check
        # F7: Near Breakout Check
        """
    except Exception:
        return None

def print_filter_report(filter_fails: dict, total: int):
    print("\n📊 FILTER ELIMINATION REPORT (MANUAL MODE)")
    print("-" * 40)
    for f in FILTERS:
        n = filter_fails.get(f, 0)
        pct = (n / total * 100) if total > 0 else 0
        print(f"{f:<20}: {n:>4} ({pct:>5.1f}%)")
    print("-" * 40)

def run_sniper():
    print("\n🎯 --- VCP SNIPER: MANUAL REVIEW MODE (F4 ONLY) ---")
    if not os.path.exists("active_sectors.json"):
        print("❌ No active_sectors.json found. Run Scout Agent first.")
        return
    with open("active_sectors.json", "r") as f:
        active_sectors = json.load(f)

    results, filter_fails, total_stocks = [], defaultdict(int), 0
    seen_tickers = set()

    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂 Scanning {sector} ({len(tickers)} tickers)")
        for ticker in tickers:
            total_stocks += 1
            hit = detect_vcp(ticker, sector, CFG, filter_fails)
            if hit and ticker not in seen_tickers:
                seen_tickers.add(ticker)
                results.append(hit)
                print(f"  ✅ {ticker.ljust(12)} | CTR: {hit['CTR']} | Pivot: ₹{hit['Pivot']}")
            time.sleep(0.05)

    print_filter_report(filter_fails, total_stocks)

    if results:
        # Sort by tightness (lowest contraction ratio first)
        results.sort(key=lambda x: x["CTR"])
        pd.DataFrame(results).to_csv("manual_vcp_review.csv", index=False)
        
        msg = "🔍 *MANUAL VCP REVIEW (Passes F4)*\n`TICKER      CTR    POLE%   PIVOT`\n"
        for r in results[:30]: # Showing top 30 candidates
            msg += f"`{r['Ticker'].ljust(10)} {str(r['CTR']).ljust(6)} {str(r['Pole_%']).ljust(7)} ₹{r['Pivot']}`\n"
        
        if TELEGRAM_TOKEN:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                          json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    else:
        print("ℹ️ No stocks passed the F4 Contraction threshold.")

if __name__ == "__main__":
    run_sniper()
