"""
macro_agent.py
--------------
Orchestrates the macro analysis layer.
Runs AFTER agent.py has completed.

Flow:
  1. Reads sector_scores.json (written by agent.py)
  2. Fetches quantitative signals via market_context.py
  3. Calls Gemini for macro analysis via llm_decision.py
  4. Writes macro_summaries + macro_findings to Supabase
  5. Sends Telegram messages
"""

import os
import json
import requests
from datetime import date

from market_context import get_market_context
from llm_decision   import get_llm_decision

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID")
SUPABASE_URL   = os.environ.get("SUPABASE_URL")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY")
TELEGRAM_LIMIT = 4000
BASE_PRC_THRESHOLD = 40


# ── Supabase ──────────────────────────────────────────────────────────────────

def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️  Supabase env vars not set — skipping DB writes")
        return None
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase connected")
        return client
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        return None


def write_macro_summary(sb, decision: dict, context: dict, scan_date: str):
    """Writes regime, scores and summary to macro_summaries table."""
    try:
        row = {
            "scan_date"   : scan_date,
            "regime"      : decision.get("regime"),
            "final_score" : decision.get("final_score"),
            "quant_score" : decision.get("quant_score"),
            "qual_score"  : decision.get("qual_score"),
            "summary"     : decision.get("summary", ""),
            "vix"         : context["vix_signal"].get("vix_now"),
            "nifty_3m"    : context["mom_signal"].get("nifty_3m_return"),
            "above_20w"   : context["sma_signal"].get("above_20w"),
            "above_50w"   : context["sma_signal"].get("above_50w"),
        }
        sb.table("macro_summaries").insert(row).execute()
        print("✅ macro_summaries written")
    except Exception as e:
        print(f"❌ write_macro_summary failed: {type(e).__name__}: {e}")


def write_macro_findings(sb, macro_scores: dict, scan_date: str):
    """Writes individual macro topic findings to macro_findings table."""
    try:
        rows = []
        for topic, val in macro_scores.items():
            if val is None:
                continue
            score     = val.get("score", 50)
            sentiment = "BULLISH" if score >= 65 else "BEARISH" if score <= 35 else "NEUTRAL"
            rows.append({
                "scan_date" : scan_date,
                "topic"     : topic,
                "score"     : score,
                "finding"   : val.get("finding", ""),
                "sentiment" : sentiment,
            })
        if rows:
            sb.table("macro_findings").insert(rows).execute()
            print(f"✅ macro_findings written ({len(rows)} topics)")
    except Exception as e:
        print(f"❌ write_macro_findings failed: {type(e).__name__}: {e}")


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(msg, use_markdown=True):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️  Telegram not configured.")
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


# ── Apply decision ────────────────────────────────────────────────────────────

def apply_decision(sector_scores: list, decision: dict) -> dict:
    prc_adj   = decision.get("prc_adjustment", 0)
    threshold = BASE_PRC_THRESHOLD + prc_adj
    tailwinds = {t["sector"]: t["reason"] for t in decision["sector_flags"].get("tailwind", [])}
    headwinds = {h["sector"]: h["reason"] for h in decision["sector_flags"].get("headwind", [])}

    actionable, flagged, suppressed, watch = [], [], [], []

    for r in sector_scores:
        sector   = r["name"]
        prc      = r["prc"]
        category = r["category"]

        if sector in headwinds and category == "STRONG":
            suppressed.append({**r, "reason": headwinds[sector]})
        elif sector in tailwinds and category != "STRONG":
            flagged.append({**r, "reason": tailwinds[sector]})
        elif category == "STRONG" and prc >= threshold:
            actionable.append(r)
        elif category == "STRONG" and prc < threshold:
            watch.append(r)

    return {
        "threshold" : threshold,
        "actionable": actionable,
        "flagged"   : flagged,
        "suppressed": suppressed,
        "watch"     : watch,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run_macro_agent():
    print("\n🤖 --- MACRO AGENT START ---")

    with open("config.json", "r") as f:
        config = json.load(f)

    # Try local file first (weekday runs), fall back to Supabase (Sunday runs)
    sector_scores = []
    try:
        with open("sector_scores.json", "r") as f:
            sector_scores = json.load(f)
        print(f"📂 Loaded {len(sector_scores)} sector scores from file")
    except FileNotFoundError:
        print("📂 sector_scores.json not found — reading from Supabase")
        try:
            from supabase import create_client
            sb_temp = create_client(SUPABASE_URL, SUPABASE_KEY)
            latest  = sb_temp.table("sector_scores")                              .select("scan_date")                              .order("scan_date", desc=True)                              .limit(1).execute()
            if latest.data:
                latest_date = latest.data[0]["scan_date"]
                rows = sb_temp.table("sector_scores")                               .select("*")                               .eq("scan_date", latest_date)                               .execute()
                sector_scores = [
                    {"name": r["sector"], "prc": r["prc"],
                     "p3": r["p3"], "p6": r["p6"], "category": r["category"]}
                    for r in rows.data
                ]
                print(f"📂 Loaded {len(sector_scores)} sector scores from Supabase ({latest_date})")
        except Exception as e:
            print(f"❌ Could not load sector scores: {e}")
            sector_scores = []

    today     = str(date.today())
    today_fmt = date.today().strftime("%d %b %Y")
    sb        = get_supabase()

    # ── Market context + LLM decision ────────────────────────────────────────
    context  = get_market_context(config)
    decision = get_llm_decision(
        quant_score    = context["quant_score"],
        signal_summary = context["signal_summary"],
        sector_scores  = sector_scores,
        config         = config,
    )

    # ── Apply decision ────────────────────────────────────────────────────────
    adjusted     = apply_decision(sector_scores, decision)
    macro_scores = decision.get("macro_scores", {})
    active       = {k: v for k, v in macro_scores.items() if v is not None}
    regime       = decision.get("regime", "NEUTRAL")
    summary      = decision.get("summary", "").strip()
    regime_emoji = {"BULL": "🐂", "NEUTRAL": "⚖️", "BEAR": "🐻"}.get(regime, "❓")

    print(f"\n📊 Regime: {regime} | Score: {decision['final_score']}/100")
    print(f"   Threshold : {adjusted['threshold']}")
    print(f"   Actionable: {len(adjusted['actionable'])} | Flagged: {len(adjusted['flagged'])} | Suppressed: {len(adjusted['suppressed'])}")

    # ── Write to Supabase ─────────────────────────────────────────────────────
    if sb:
        write_macro_summary(sb, decision, context, today)
        write_macro_findings(sb, macro_scores, today)

    # ── Save local backup ─────────────────────────────────────────────────────
    with open("macro_output.json", "w") as f:
        json.dump({"decision": decision, "adjusted": adjusted,
                   "context": {"quant_score": context["quant_score"]},
                   "scan_date": today}, f, indent=2, default=str)
    print("💾 macro_output.json saved")

    # ── Telegram Message 4 — Macro summary ───────────────────────────────────
    from datetime import datetime
    is_sunday = datetime.now().weekday() == 6
    prefix    = "📋 *Monday Prep* — " if is_sunday else ""
    if summary:
        msg4 = f"{prefix}{regime_emoji} *Macro ({regime}):* {summary}"
        send_telegram(msg4)

    # ── Telegram Message 5 — Macro findings ──────────────────────────────────
    if active:
        msg5 = f"📰 Macro Findings — {today_fmt}\n"
        label_map = {
            "fii_dii_flows"    : "FII / DII Flows",
            "rbi_policy"       : "RBI Policy",
            "rupee_dollar"     : "Rupee vs Dollar",
            "crude_oil"        : "Crude Oil",
            "global_risk"      : "Global Risk",
            "tariffs_trade"    : "Tariffs & Trade",
            "geopolitical_war" : "Geopolitical Risk",
            "customs_duty_bans": "Customs & Duties",
            "healthcare_virus" : "Health Risk",
            "domestic_policy"  : "India Policy",
            "us_bond_yields"   : "US Bond Yields",
            "gold_silver"      : "Gold & Silver",
        }
        for key, val in active.items():
            score   = val.get("score", 50)
            finding = val.get("finding", "")
            short   = finding.replace(";", ".").split(".")[0].strip()
            bar     = "🟢" if isinstance(score, int) and score >= 65 else "🔴" if isinstance(score, int) and score <= 35 else "🟡"
            label   = label_map.get(key, key.replace("_", " ").title())[:16]
            msg5   += f"{bar} {label}: {short}\n"
        send_telegram(msg5, use_markdown=False)

    print("\n✅ Macro agent complete.")


if __name__ == "__main__":
    run_macro_agent()
