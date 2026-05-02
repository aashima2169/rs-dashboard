import os, requests, json, time
import pandas as pd
import yfinance as yf
import warnings
from collections import defaultdict

warnings.simplefilter(action='ignore', category=FutureWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG: MANUAL REVIEW MODE (F1-F4)
# ─────────────────────────────────────────────────────────────────────────────
CFG = {
    "min_pole_pct":           15,
    "max_pole_pct":           50,
    "pole_trough_window":     30,
    "pole_lookback_days":    130,
    "pole_exclude_recent":    20,
    "vcp_base_days":          60,
    "min_base_bars":          15,
    "min_contraction_ratio":  0.70, 
}

FILTERS = ["F1_EMA_Trend", "F2_Pole_Size", "F3_Base_Formed", "F4_Contraction"]

def get_stocks(sector_key: str) -> list:
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        if not official_name: return []

        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        resp = session.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return [f"{s['symbol']}.NS" for s in resp.json()["data"] if s["symbol"] != official_name]
        return []
    except Exception: return []

def detect_vcp(ticker: str, sector: str, cfg: dict, filter_fails: dict) -> dict | None:
    try:
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 250: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        close = df["Close"].squeeze()
        cmp = float(close.iloc[-1])

        # ── F1: EMA TREND (EMA21 > 50 > 200 AND Price > 50) ──────────────────
        ema21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
        
        if not (ema21 > ema50 > ema200 and cmp > ema50):
            filter_fails["F1_EMA_Trend"] += 1
            return None

        # ── F2: POLE SIZE ────────────────────────────────────────────────────
        search_window = close.iloc[-(cfg["pole_lookback_days"] + 20) : -20]
        p_high = float(search_window.max())
        p_low = float(close.loc[:search_window.idxmax()].tail(30).min())
        p_pct = ((p_high - p_low) / p_low) * 100
        
        if not (cfg["min_pole_pct"] <= p_pct <= cfg["max_pole_pct"]):
            filter_fails["F2_Pole_Size"] += 1
            return None

        # ── F3: BASE BARS ────────────────────────────────────────────────────
        base_window = close.loc[search_window.idxmax():]
        if len(base_window) < cfg["min_base_bars"]:
            filter_fails["F3_Base_Formed"] += 1
            return None

        # ── F4: CONTRACTION ──────────────────────────────────────────────────
        c_ratio = (float(base_window.max()) - float(base_window.min())) / (p_high - p_low)
        if c_ratio > cfg["min_contraction_ratio"]:
            filter_fails["F4_Contraction"] += 1
            return None

        # ── RETURN FOR MANUAL CHECK (F5, F6, F7 BYPASSED) ────────────────────
        return {
            "Ticker": ticker, 
            "Sector": sector,
            "CMP": round(cmp, 2),
            "CTR": round(c_ratio, 2), 
            "Pole_%": round(p_pct, 1),
            "Pivot": round(p_high * 1.01, 2)
        }
    except Exception: return None

def run_sniper():
    print("\n🎯 --- STARTING SCAN (F4 MANUAL MODE) ---")
    if not os.path.exists("active_sectors.json"):
        print("❌ active_sectors.json missing")
        return
        
    with open("active_sectors.json", "r") as f: 
        active_sectors = json.load(f)

    results, filter_fails, total_stocks = [], defaultdict(int), 0
    seen = set()

    for sector in active_sectors:
        tickers = get_stocks(sector)
        print(f"📂 Sector: {sector} ({len(tickers)} stocks)")
        for ticker in tickers:
            total_stocks += 1
            hit = detect_vcp(ticker, sector, CFG, filter_fails)
            if hit and ticker not in seen:
                seen.add(ticker)
                results.append(hit)
                print(f"  ✅ {ticker.ljust(10)} | CTR: {hit['CTR']} | Pole: {hit['Pole_%']}%")
            time.sleep(0.05)

    # ─────────────────────────────────────────────────────────────────────────
    # FILE GENERATION: MATCHES YAML 'path: sniper_candidates.csv'
    # ─────────────────────────────────────────────────────────────────────────
    filename = "sniper_candidates.csv"
    if results:
        results.sort(key=lambda x: x["CTR"])
        pd.DataFrame(results).to_csv(filename, index=False)
        print(f"\n✨ Success: {len(results)} stocks saved to {filename}")
        
        # Telegram Notification
        msg = "🔍 *F4 MANUAL REVIEW LIST*\n`TICKER      CTR    POLE%   PIVOT`\n"
        for r in results[:15]:
            msg += f"`{r['Ticker'].ljust(10)} {str(r['CTR']).ljust(6)} {str(r['Pole_%']).ljust(7)} ₹{r['Pivot']}`\n"
        if TELEGRAM_TOKEN:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                          json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    else:
        # Create empty file so GitHub Actions doesn't fail the upload
        pd.DataFrame([{"Status": "No stocks passed today"}]).to_csv(filename, index=False)
        print(f"ℹ️ No matches. Created empty {filename} for workflow safety.")

if __name__ == "__main__":
    run_sniper()
