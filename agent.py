"""
agent.py  —  Scout Agent
------------------------
Calculates 3M and 6M Relative Strength of each sector vs Nifty 50.
Ranks and categorises sectors into Strong / Mixed / Weak.

Supabase integration:
  - Writes this week's scores to sector_scores table
  - Reads last 4 weeks for drift detection (momentum shifts)
  - Reads 4-week-old calls for eval (did Strong sectors beat Nifty?)
  - Writes eval results to eval_results table
"""

import os
import json
import requests
import pandas as pd
import yfinance as yf
from datetime import date, timedelta
from supabase import create_client, Client

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID")
SUPABASE_URL   = os.environ.get("SUPABASE_URL")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY")
TELEGRAM_LIMIT = 4000


# ── Supabase client ───────────────────────────────────────────────────────────

def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️  Supabase env vars not set — skipping DB operations")
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"⚠️  Supabase connection failed: {e}")
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
        return "  N/A "
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(f"⚠️  Telegram not set. TOKEN:{bool(TELEGRAM_TOKEN)} CHAT:{bool(CHAT_ID)}")
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
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": chunk, "parse_mode": "Markdown"},
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
    try:
        rows = [
            {
                "scan_date": scan_date,
                "sector"   : r["name"],
                "prc"      : r["prc"],
                "p3"       : r["p3"],
                "p6"       : r["p6"],
                "r3"       : r["r3"],
                "r6"       : r["r6"],
                "category" : r["category"],
            }
            for r in results
        ]
        sb.table("sector_scores").insert(rows).execute()
        print(f"✅ {len(rows)} scores written to Supabase")
    except Exception as e:
        print(f"⚠️  Write scores failed: {e}")


def read_history(sb, weeks=4):
    try:
        since = str(date.today() - timedelta(weeks=weeks))
        resp  = sb.table("sector_scores").select("*").gte("scan_date", since).order("scan_date").execute()
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
    except Exception as e:
        print(f"⚠️  Read history failed: {e}")
        return pd.DataFrame()


def read_calls_4_weeks_ago(sb):
    try:
        target = str(date.today() - timedelta(weeks=4))
        resp   = sb.table("sector_scores").select("*").lte("scan_date", target).order("scan_date", desc=True).limit(50).execute()
        if resp.data:
            df     = pd.DataFrame(resp.data)
            latest = df["scan_date"].max()
            return df[df["scan_date"] == latest]
        return pd.DataFrame()
    except Exception as e:
        print(f"⚠️  Read old calls failed: {e}")
        return pd.DataFrame()


def write_eval(sb, eval_rows):
    try:
        sb.table("eval_results").insert(eval_rows).execute()
        print(f"✅ {len(eval_rows)} eval results written to Supabase")
    except Exception as e:
        print(f"⚠️  Write eval failed: {e}")


# ── Drift detection ───────────────────────────────────────────────────────────

def detect_drift(current_df, history_df):
    if history_df.empty:
        return []
    past = history_df[history_df["scan_date"] < str(date.today())]
    if past.empty:
        return []
    last_week = history_df[history_df["scan_date"] == past["scan_date"].max()].set_index("sector")

    shifts = []
    for _, row in current_df.iterrows():
        sector = row["name"]
        if sector not in last_week.index:
            continue
        prev     = last_week.loc[sector]
        prc_now  = row["prc"]
        prc_prev = int(prev["prc"])
        cat_now  = row["category"]
        cat_prev = prev["category"]
        delta    = prc_now - prc_prev

        if cat_now != cat_prev:
            if cat_now == "STRONG":
                shifts.append(f"🚨 *{sector}*: {cat_prev} → STRONG")
            elif cat_now == "WEAK":
                shifts.append(f"🚨 *{sector}*: {cat_prev} → WEAK")
            else:
                shifts.append(f"🔄 *{sector}*: {cat_prev} → {cat_now}")
        elif delta >= 10:
            shifts.append(f"⚡ *{sector}*: PRC {prc_prev}→{prc_now} (+{delta})")
        elif delta <= -10:
            shifts.append(f"📉 *{sector}*: PRC {prc_prev}→{prc_now} ({delta})")

    return shifts


# ── Eval ──────────────────────────────────────────────────────────────────────

def run_eval(sb, sector_tickers, bm_data):
    old_calls = read_calls_4_weeks_ago(sb)
    if old_calls.empty:
        print("ℹ️  No calls from 4 weeks ago — skipping eval")
        return [], None

    call_date    = old_calls["scan_date"].iloc[0]
    strong_calls = old_calls[old_calls["category"] == "STRONG"]
    if strong_calls.empty:
        print("ℹ️  No Strong calls from 4 weeks ago — skipping eval")
        return [], None

    print(f"\n📋 Evaluating {len(strong_calls)} Strong calls from {call_date}...")
    eval_rows = []
    hits      = 0

    for _, call in strong_calls.iterrows():
        sector = call["sector"]
        ticker = sector_tickers.get(sector)
        if not ticker:
            continue
        try:
            s_data        = get_close(ticker)
            sector_return = ((s_data.iloc[-1] / s_data.iloc[-20]) - 1) * 100
            nifty_return  = ((bm_data.iloc[-1] / bm_data.iloc[-20]) - 1) * 100
            beat_nifty    = bool(sector_return > nifty_return)
            if beat_nifty:
                hits += 1
            eval_rows.append({
                "call_date"        : call_date,
                "eval_date"        : str(date.today()),
                "sector"           : sector,
                "category_called"  : "STRONG",
                "actual_return_pct": round(float(sector_return), 2),
                "beat_nifty"       : beat_nifty,
            })
            print(f"   {'✅' if beat_nifty else '❌'} {sector}: {sector_return:+.1f}% vs Nifty {nifty_return:+.1f}%")
        except Exception as e:
            print(f"   ⚠️  Eval error {sector}: {e}")

    hit_rate = round(hits / len(eval_rows) * 100) if eval_rows else None
    return eval_rows, hit_rate


# ── Main ──────────────────────────────────────────────────────────────────────

def run_agent():
    print("📊 --- SCOUT AGENT START ---")

    with open("config.json", "r") as f:
        config = json.load(f)

    sector_tickers = config.get("sectors", {})
    today          = str(date.today())
    sb             = get_supabase()

    print(f"📂 Scanning {len(sector_tickers)} sectors...\n")

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
            results.append({"name": name, "ticker": ticker, "p3": p3, "p6": p6, "r3": r3, "r6": r6, "prc": round((r3+r6)/2)})
        except Exception as e:
            print(f"     ⚠️  Error: {e}")

    if not results:
        print("❌ No results")
        return

    df = pd.DataFrame(results).sort_values("prc", ascending=False)

    def categorise(row):
        if row["p3"] is not None and row["p6"] is not None:
            if row["p3"] > 0 and row["p6"] > 0: return "STRONG"
            elif row["p3"] > 0 or row["p6"] > 0: return "MIXED"
        return "WEAK"

    df["category"] = df.apply(categorise, axis=1)
    df["scan_date"] = today
    df.to_json("sector_scores.json", orient="records", indent=2)
    print("\n📊 sector_scores.json saved")

    results = df.to_dict(orient="records")

    # ── Eval (before writing new scores) ─────────────────────────────────────
    eval_rows, hit_rate = [], None
    if sb:
        eval_rows, hit_rate = run_eval(sb, sector_tickers, bm_data)
        if eval_rows:
            write_eval(sb, eval_rows)

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

    # Message 1 — Strong + Mixed
    msg1 = f"📊 *SECTOR RS REPORT — {today_fmt}*\n\n"
    msg1 += "`SECTOR           PRC   3M RS   6M RS`\n"
    msg1 += "`──────────────────────────────────`\n"
    for cat, emoji, label in [("STRONG", "🟢", "STRONG"), ("MIXED", "🟡", "MIXED")]:
        rows = df[df["category"] == cat]
        if rows.empty: continue
        msg1 += f"\n{emoji} *{label}*\n"
        for _, r in rows.iterrows():
            msg1 += f"`{r['name'][:14].ljust(14)}  {str(r['prc']).rjust(3)}  {format_pct(r['p3'])}  {format_pct(r['p6'])}`\n"

    # Message 2 — Weak
    msg2 = f"📊 *SECTOR RS REPORT — {today_fmt} (cont.)*\n\n"
    weak = df[df["category"] == "WEAK"]
    if not weak.empty:
        msg2 += "🔴 *WEAK*\n"
        for _, r in weak.iterrows():
            msg2 += f"`{r['name'][:14].ljust(14)}  {str(r['prc']).rjust(3)}  {format_pct(r['p3'])}  {format_pct(r['p6'])}`\n"
    msg2 += "\n_Review · set active\\_sectors.json · trigger Sniper_"

    # Message 3 — Momentum shifts
    msg3 = ""
    if shifts:
        msg3 = f"🚨 *MOMENTUM SHIFTS — {today_fmt}*\n\n" + "\n".join(shifts)

    # Message 4 — Eval scorecard
    msg4 = ""
    if eval_rows:
        msg4 = f"📋 *SCOUT EVAL — calls from {eval_rows[0]['call_date']}*\n\n"
        for e in eval_rows:
            icon = "✅" if e["beat_nifty"] else "❌"
            msg4 += f"{icon} `{e['sector'][:14].ljust(14)} {e['actual_return_pct']:+.1f}%`\n"
        if hit_rate is not None:
            msg4 += f"\n*Hit Rate: {hit_rate}%* 🎯"

    send_telegram(msg1)
    send_telegram(msg2)
    if msg3: send_telegram(msg3)
    if msg4: send_telegram(msg4)

    print("\n✅ Scout complete.")


if __name__ == "__main__":
    run_agent()
