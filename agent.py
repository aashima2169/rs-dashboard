"""
agent.py  —  Scout Agent
------------------------
Calculates 3M and 6M Relative Strength of each sector vs Nifty 50.
Ranks and categorises sectors into Strong / Mixed / Weak.

Outputs:
  sector_scores.json   — full RS data for all sectors (read by sniper + dashboard)

Does NOT write active_sectors.json — that decision is yours.
Run sniper_agent.py manually after reviewing this report.
"""

import os
import json
import requests
import pandas as pd
import yfinance as yf
from datetime import date

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_close(ticker: str) -> pd.Series:
    df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df["Close"].dropna()


def calc_percentile(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float((series < series.iloc[-1]).mean() * 100)


def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️  Telegram env vars not set — skipping")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"⚠️  Telegram error: {e}")


def format_pct(val) -> str:
    """Format a percentage value with sign, or N/A if None."""
    if val is None:
        return "  N/A "
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


# ─── Main ──────────────────────────────────────────────────────────────────────

def run_agent():
    print("📊 --- SCOUT AGENT START ---")

    with open("config.json", "r") as f:
        config = json.load(f)

    sector_tickers = config.get("sectors", {})
    print(f"📂 Scanning {len(sector_tickers)} sectors vs Nifty 50...\n")

    # Download benchmark
    bm_data = get_close("^NSEI")
    if bm_data.empty:
        print("❌ Could not download Nifty 50 — aborting.")
        return

    results = []

    for name, ticker in sector_tickers.items():
        print(f"  🔍 {name} ({ticker})")
        try:
            s_data = get_close(ticker)
            if s_data.empty:
                print(f"     ⚠️  No data for {ticker}")
                continue

            combined = pd.concat([s_data, bm_data], axis=1).dropna()
            combined.columns = ["s", "b"]
            rs = combined["s"] / combined["b"]

            # ── RS absolute change ────────────────────────────────────────────
            p3 = round(((rs.iloc[-1] / rs.iloc[-63])  - 1) * 100, 1) if len(rs) >= 63  else None
            p6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1) if len(rs) >= 126 else None

            # ── Percentile rank vs past year ──────────────────────────────────
            r3 = round(calc_percentile(rs.pct_change(63).tail(252)))  if p3 is not None else 0
            r6 = round(calc_percentile(rs.pct_change(126).tail(252))) if p6 is not None else 0

            # PRC = composite rank (equal weight 3M + 6M)
            prc = round((r3 + r6) / 2)

            results.append({
                "name"  : name,
                "ticker": ticker,
                "p3"    : p3,
                "p6"    : p6,
                "r3"    : r3,
                "r6"    : r6,
                "prc"   : prc,
            })

        except Exception as e:
            print(f"     ⚠️  Error processing {name}: {e}")

    if not results:
        print("❌ No results — check tickers in config.json")
        return

    df = pd.DataFrame(results).sort_values("prc", ascending=False)

    # ── Categorise ────────────────────────────────────────────────────────────
    def categorise(row) -> str:
        if row["p3"] is not None and row["p6"] is not None:
            if row["p3"] > 0 and row["p6"] > 0:
                return "STRONG"
            elif row["p3"] > 0 or row["p6"] > 0:
                return "MIXED"
        return "WEAK"

    df["category"] = df.apply(categorise, axis=1)

    # ── Save sector_scores.json (used by sniper + Phase 2 dashboard) ──────────
    sector_scores = df.copy()
    sector_scores["scan_date"] = str(date.today())
    sector_scores.to_json("sector_scores.json", orient="records", indent=2)
    print("\n📊 sector_scores.json saved")

    # ── Print to console ──────────────────────────────────────────────────────
    print("\n" + "─" * 54)
    print(f"{'SECTOR':<18} {'PRC':>4}  {'3M RS':>7}  {'6M RS':>7}  {'CAT'}")
    print("─" * 54)
    for _, r in df.iterrows():
        print(
            f"{r['name']:<18} {r['prc']:>4}  "
            f"{format_pct(r['p3']):>7}  {format_pct(r['p6']):>7}  "
            f"{r['category']}"
        )
    print("─" * 54)

    # ── Build Telegram message ────────────────────────────────────────────────
    today = date.today().strftime("%d %b %Y")
    msg   = f"📊 *SECTOR RS REPORT — {today}*\n\n"

    # Column header (monospace)
    msg += "`SECTOR           PRC   3M RS   6M RS`\n"
    msg += "`────────────────────────────────────`\n"

    for category, emoji, label in [
        ("STRONG", "🟢", "STRONG"),
        ("MIXED",  "🟡", "MIXED"),
        ("WEAK",   "🔴", "WEAK"),
    ]:
        rows = df[df["category"] == category]
        if rows.empty:
            continue

        msg += f"\n{emoji} *{label}*\n"
        for _, r in rows.iterrows():
            p3_str = format_pct(r["p3"])
            p6_str = format_pct(r["p6"])
            name   = r["name"][:14].ljust(14)   # truncate long names
            prc    = str(r["prc"]).rjust(3)
            msg += f"`{name}  {prc}  {p3_str}  {p6_str}`\n"

    msg += (
        "\n_Review above · then manually set active\\_sectors.json_\n"
        "_and trigger the Sniper workflow separately._"
    )

    print("\n" + msg)
    send_telegram(msg)
    print("\n✅ Scout complete — review report before running sniper.")


if __name__ == "__main__":
    run_agent()
