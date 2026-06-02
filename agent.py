"""
agent.py  —  Scout Agent
------------------------
Calculates 3M and 6M Relative Strength of each sector vs Nifty 50.
Ranks and categorises sectors into Strong / Mixed / Weak.
Detects week-over-week momentum shifts via Supabase history.

Outputs:
  sector_scores.json   — full RS data for all sectors
  Telegram messages    — scores, weak sectors, momentum shifts
  Supabase             — sector_scores table updated each run
"""

import os
import math
import json
import requests
import pandas as pd
import yfinance as yf
from datetime import date, timedelta

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID")
SUPABASE_URL   = os.environ.get("SUPABASE_URL")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY")
TELEGRAM_LIMIT = 4000


# ── Supabase client ───────────────────────────────────────────────────────────

def get_supabase():
    print(f"🔌 Supabase URL set: {bool(SUPABASE_URL)}")
    print(f"🔌 Supabase KEY set: {bool(SUPABASE_KEY)}")
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️  Supabase env vars missing — DB operations skipped")
        return None
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase client connected")
        return client
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_close(ticker):
    df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df["Close"].dropna()


def calc_percentile(series):
    if series.empty:
        return 0.0
    return float((series < series.iloc[-1]).mean() * 100)


def format_pct(val):
    if val is None:
        return "  N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


def send_telegram(msg, use_markdown=True):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(f"⚠️  Telegram not configured. TOKEN:{bool(TELEGRAM_TOKEN)} CHAT:{bool(CHAT_ID)}")
        return
    chunks = []
    while len(msg) > TELEGRAM_LIMIT:
        split_at = msg.rfind("\n", 0, TELEGRAM_LIMIT)
        if split_at == -1:
            split_at = TELEGRAM_LIMIT
        chunks.append(msg[:split_at])
        msg = msg[split_at:].lstrip("\n")
    chunks.append(msg)
    print(f"📤 Sending {len(chunks)} Telegram message(s)...")
    for i, chunk in enumerate(chunks, 1):
        try:
            payload = {"chat_id": CHAT_ID, "text": chunk}
            if use_markdown:
                payload["parse_mode"] = "Markdown"
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"   ✅ Message {i}/{len(chunks)} sent")
            else:
                print(f"   ❌ Failed {i}: {resp.status_code} — {resp.text}")
        except Exception as e:
            print(f"   ❌ Exception {i}: {e}")


# ── Supabase operations ───────────────────────────────────────────────────────

def write_scores(sb, results, scan_date):
    print(f"\n💾 Writing {len(results)} scores to Supabase...")

    def clean(v):
        """Replace NaN/Inf/numpy floats with None or plain Python float"""
        if v is None:
            return None
        try:
            f = float(v)  # converts numpy float64 to Python float
            return None if (math.isnan(f) or math.isinf(f)) else round(f, 2)
        except:
            return None

    try:
        rows = [
            {
                "scan_date": scan_date,
                "sector"   : r["name"],
                "prc"      : int(r["prc"]) if r["prc"] is not None else 0,
                "p3"       : clean(r["p3"]),
                "p6"       : clean(r["p6"]),
                "r3"       : clean(r["r3"]),
                "r6"       : clean(r["r6"]),
                "category" : r["category"],
            }
            for r in results
            if r.get("name") and r.get("category")
        ]
        sb.table("sector_scores").insert(rows).execute()
        print(f"✅ {len(rows)} rows written to Supabase")
    except Exception as e:
        print(f"❌ write_scores failed: {type(e).__name__}: {e}")


def read_history(sb, weeks=4):
    print(f"\n📖 Reading last {weeks} weeks from Supabase...")
    try:
        since = str(date.today() - timedelta(weeks=weeks))
        resp  = sb.table("sector_scores").select("*").gte("scan_date", since).order("scan_date").execute()
        rows  = len(resp.data) if resp.data else 0
        print(f"✅ {rows} historical rows read")
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
    except Exception as e:
        print(f"❌ read_history failed: {type(e).__name__}: {e}")
        return pd.DataFrame()


# ── Drift detection ───────────────────────────────────────────────────────────

def detect_drift(current_df, history_df):
    if history_df.empty:
        print("ℹ️  No history for drift detection yet")
        return []

    past = history_df[history_df["scan_date"] < str(date.today())]
    if past.empty:
        return []

    last_week = history_df[
        history_df["scan_date"] == past["scan_date"].max()
    ].set_index("sector")

    shifts = []
    for _, row in current_df.iterrows():
        sector = row["name"]
        if sector not in last_week.index:
            continue

        prev     = last_week.loc[sector]
        # Handle case where multiple rows exist for same sector (take first)
        if isinstance(prev, pd.DataFrame):
            prev = prev.iloc[0]
        prc_now  = row["prc"]
        prc_prev = int(float(prev["prc"]))
        cat_now  = row["category"]
        cat_prev = prev["category"] if isinstance(prev["category"], str) else str(prev["category"].iloc[0])
        delta    = prc_now - prc_prev

        if cat_now != cat_prev:
            if cat_now == "STRONG":
                shifts.append(f"🚨 *{sector}*: {cat_prev} to STRONG")
            elif cat_now == "WEAK":
                shifts.append(f"🚨 *{sector}*: {cat_prev} to WEAK")
            else:
                shifts.append(f"🔄 *{sector}*: {cat_prev} to {cat_now}")
        elif delta >= 10:
            shifts.append(f"⚡ *{sector}*: PRC {prc_prev} to {prc_now} (+{delta})")
        elif delta <= -10:
            shifts.append(f"📉 *{sector}*: PRC {prc_prev} to {prc_now} ({delta})")

    print(f"✅ Drift detection: {len(shifts)} shifts found")
    return shifts


# ── Main ──────────────────────────────────────────────────────────────────────

def run_agent():
    print("📊 --- SCOUT AGENT START ---")

    with open("config.json", "r") as f:
        config = json.load(f)

    sector_tickers = config.get("sectors", {})
    today          = str(date.today())
    sb             = get_supabase()

    print(f"\n📂 Scanning {len(sector_tickers)} sectors...\n")

    bm_data = get_close("^NSEI")
    if bm_data.empty:
        print("❌ Nifty 50 download failed — aborting.")
        return

    # ── RS calculation ────────────────────────────────────────────────────────
    results = []
    for name, ticker in sector_tickers.items():
        print(f"  🔍 {name} ({ticker})")
        try:
            s_data = get_close(ticker)
            if s_data.empty:
                print(f"     ⚠️  No data")
                continue
            combined = pd.concat([s_data, bm_data], axis=1).dropna()
            combined.columns = ["s", "b"]
            rs  = combined["s"] / combined["b"]
            p3  = round(((rs.iloc[-1] / rs.iloc[-63])  - 1) * 100, 1) if len(rs) >= 63  else None
            p6  = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1) if len(rs) >= 126 else None
            r3  = round(calc_percentile(rs.pct_change(63).tail(252)))  if p3 is not None else 0
            r6  = round(calc_percentile(rs.pct_change(126).tail(252))) if p6 is not None else 0
            results.append({
                "name": name, "ticker": ticker,
                "p3": p3, "p6": p6,
                "r3": r3, "r6": r6,
                "prc": round((r3 + r6) / 2),
            })
        except Exception as e:
            print(f"     ❌ Error: {type(e).__name__}: {e}")

    if not results:
        print("❌ No results — check tickers in config.json")
        return

    df = pd.DataFrame(results).sort_values("prc", ascending=False)

    def categorise(row):
        if row["p3"] is not None and row["p6"] is not None:
            if row["p3"] > 0 and row["p6"] > 0:   return "STRONG"
            elif row["p3"] > 0 or row["p6"] > 0:  return "MIXED"
        return "WEAK"

    df["category"] = df.apply(categorise, axis=1)
    df["scan_date"] = today
    df.to_json("sector_scores.json", orient="records", indent=2)
    print("\n📊 sector_scores.json saved")

    results = df.to_dict(orient="records")

    # ── Drift detection ───────────────────────────────────────────────────────
    shifts = []
    if sb:
        history_df = read_history(sb, weeks=4)
        shifts     = detect_drift(df, history_df)

    # ── Write this week's scores ──────────────────────────────────────────────
    if sb:
        write_scores(sb, results, today)

    # ── Console table ─────────────────────────────────────────────────────────
    print("\n" + "─" * 54)
    print(f"{'SECTOR':<18} {'PRC':>4}  {'3M RS':>7}  {'6M RS':>7}  CAT")
    print("─" * 54)
    for _, r in df.iterrows():
        print(f"{r['name']:<18} {r['prc']:>4}  {format_pct(r['p3']):>7}  {format_pct(r['p6']):>7}  {r['category']}")
    print("─" * 54)

    # ── Telegram messages ─────────────────────────────────────────────────────
    today_fmt = date.today().strftime("%d %b %Y")

    def fmt_row(r):
        name = r["name"][:9].ljust(9)
        prc  = str(r["prc"]).rjust(3)
        p3   = format_pct(r["p3"]).strip().rjust(6)
        p6   = format_pct(r["p6"]).strip().rjust(6)
        return f"`{name} {prc} {p3} {p6}`"

    # Message 1 — Strong + Mixed
    msg1  = f"📊 *SECTOR RS — {today_fmt}*\n"
    msg1 += "`         PRC     3M     6M`\n"
    for cat, emoji, label in [("STRONG", "🟢", "STRONG"), ("MIXED", "🟡", "MIXED")]:
        rows = df[df["category"] == cat]
        if rows.empty:
            continue
        msg1 += f"\n{emoji} *{label}*\n"
        for _, r in rows.iterrows():
            msg1 += fmt_row(r) + "\n"

    # Message 2 — Weak (plain text, no Markdown)
    weak  = df[df["category"] == "WEAK"]
    msg2  = f"📊 SECTOR RS — {today_fmt} (cont.)\n"
    msg2 += "          PRC     3M     6M\n"
    if not weak.empty:
        msg2 += "\n🔴 WEAK\n"
        for _, r in weak.iterrows():
            name = r["name"][:9].ljust(9)
            prc  = str(r["prc"]).rjust(3)
            p3   = format_pct(r["p3"]).strip().rjust(6)
            p6   = format_pct(r["p6"]).strip().rjust(6)
            msg2 += f"{name} {prc} {p3} {p6}\n"
    msg2 += "\nReview and trigger Sniper manually."

    # Message 3 — Momentum shifts
    msg3 = ""
    if shifts:
        msg3 = f"🚨 *MOMENTUM SHIFTS — {today_fmt}*\n\n" + "\n".join(shifts)

    send_telegram(msg1)
    send_telegram(msg2, use_markdown=False)
    if msg3:
        send_telegram(msg3)

    print("\n✅ Scout complete.")


if __name__ == "__main__":
    run_agent()
