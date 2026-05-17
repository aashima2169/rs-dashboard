"""
agent.py  —  Scout Agent
------------------------
Calculates 3M and 6M Relative Strength of each sector vs Nifty 50.
Ranks and categorises sectors into Strong / Mixed / Weak.

Outputs:
  sector_scores.json   — full RS data for all sectors

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

TELEGRAM_LIMIT = 4000   # safe buffer under Telegram's 4096 char limit


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
    """Send a message, automatically splitting if over Telegram's 4096 char limit."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️  Telegram env vars not set — skipping")
        print(f"   TELEGRAM_BOT_TOKEN set: {bool(TELEGRAM_TOKEN)}")
        print(f"   TELEGRAM_CHAT_ID set:   {bool(CHAT_ID)}")
        return

    # Split into chunks if needed
    chunks = []
    while len(msg) > TELEGRAM_LIMIT:
        # Find last newline before the limit to avoid splitting mid-line
        split_at = msg.rfind("\n", 0, TELEGRAM_LIMIT)
        if split_at == -1:
            split_at = TELEGRAM_LIMIT
        chunks.append(msg[:split_at])
        msg = msg[split_at:].lstrip("\n")
    chunks.append(msg)

    print(f"📤 Sending {len(chunks)} Telegram message(s)...")

    for i, chunk in enumerate(chunks, 1):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": chunk, "parse_mode": "Markdown"},
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"   ✅ Message {i}/{len(chunks)} sent")
            else:
                print(f"   ❌ Message {i}/{len(chunks)} failed: {resp.status_code} — {resp.text}")
        except Exception as e:
            print(f"   ❌ Message {i}/{len(chunks)} exception: {e}")


def format_pct(val) -> str:
    if val is None:
        return "  N/A "
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_agent():
    print("📊 --- SCOUT AGENT START ---")

    with open("config.json", "r") as f:
        config = json.load(f)

    sector_tickers = config.get("sectors", {})
    print(f"📂 Scanning {len(sector_tickers)} sectors vs Nifty 50...\n")

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

            p3 = round(((rs.iloc[-1] / rs.iloc[-63])  - 1) * 100, 1) if len(rs) >= 63  else None
            p6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1) if len(rs) >= 126 else None

            r3 = round(calc_percentile(rs.pct_change(63).tail(252)))  if p3 is not None else 0
            r6 = round(calc_percentile(rs.pct_change(126).tail(252))) if p6 is not None else 0

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

    def categorise(row) -> str:
        if row["p3"] is not None and row["p6"] is not None:
            if row["p3"] > 0 and row["p6"] > 0:
                return "STRONG"
            elif row["p3"] > 0 or row["p6"] > 0:
                return "MIXED"
        return "WEAK"

    df["category"] = df.apply(categorise, axis=1)

    # ── Save sector_scores.json ───────────────────────────────────────────────
    sector_scores = df.copy()
    sector_scores["scan_date"] = str(date.today())
    sector_scores.to_json("sector_scores.json", orient="records", indent=2)
    print("\n📊 sector_scores.json saved")

    # ── Console table ─────────────────────────────────────────────────────────
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

    # ── Telegram: Message 1 — Strong + Mixed ──────────────────────────────────
    today = date.today().strftime("%d %b %Y")

    msg1 = f"📊 *SECTOR RS REPORT — {today}*\n\n"
    msg1 += "`SECTOR           PRC   3M RS   6M RS`\n"
    msg1 += "`──────────────────────────────────`\n"

    for category, emoji, label in [("STRONG", "🟢", "STRONG"), ("MIXED", "🟡", "MIXED")]:
        rows = df[df["category"] == category]
        if rows.empty:
            continue
        msg1 += f"\n{emoji} *{label}*\n"
        for _, r in rows.iterrows():
            name = r["name"][:14].ljust(14)
            prc  = str(r["prc"]).rjust(3)
            msg1 += f"`{name}  {prc}  {format_pct(r['p3'])}  {format_pct(r['p6'])}`\n"

    # ── Telegram: Message 2 — Weak ────────────────────────────────────────────
    msg2 = f"📊 *SECTOR RS REPORT — {today} (cont.)*\n\n"
    msg2 += "`SECTOR           PRC   3M RS   6M RS`\n"
    msg2 += "`──────────────────────────────────`\n"

    weak_rows = df[df["category"] == "WEAK"]
    if not weak_rows.empty:
        msg2 += "\n🔴 *WEAK*\n"
        for _, r in weak_rows.iterrows():
            name = r["name"][:14].ljust(14)
            prc  = str(r["prc"]).rjust(3)
            msg2 += f"`{name}  {prc}  {format_pct(r['p3'])}  {format_pct(r['p6'])}`\n"

    msg2 += "\n_Review above · set active\\_sectors.json · trigger Sniper manually_"

    print("\n" + msg1)
    send_telegram(msg1)

    print("\n" + msg2)
    send_telegram(msg2)

    print("\n✅ Scout complete.")


if __name__ == "__main__":
    run_agent()
