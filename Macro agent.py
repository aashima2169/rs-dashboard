"""
macro_agent.py
--------------
Orchestrates the macro analysis layer.
Runs AFTER agent.py has completed.

Flow:
  1. Reads sector_scores.json (written by agent.py)
  2. Fetches quantitative signals via market_context.py
  3. Calls Gemini for macro analysis via llm_decision.py
  4. Applies regime decision to sector scores
  5. Sends enriched Telegram report

Does not touch Supabase or recalculate RS scores.
Reads agent.py output, adds macro layer, sends Telegram.
"""

import os
import json
import requests
from datetime import date

from market_context import get_market_context
from llm_decision   import get_llm_decision

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID")
TELEGRAM_LIMIT = 4000

BASE_PRC_THRESHOLD = 40   # default threshold, adjusted by regime


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(msg, use_markdown=True):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(f"⚠️  Telegram not configured.")
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


# ── Apply decision to sectors ─────────────────────────────────────────────────

def apply_decision(sector_scores: list, decision: dict, config: dict) -> dict:
    """
    Applies regime decision to sector scores:
      - Adjusts effective PRC threshold
      - Marks sectors with tailwind (flag despite weak RS)
      - Marks sectors with headwind (suppress despite strong RS)

    Returns dict with adjusted sector lists.
    """
    prc_adj   = decision.get("prc_adjustment", 0)
    threshold = BASE_PRC_THRESHOLD + prc_adj

    tailwinds = {t["sector"]: t["reason"] for t in decision["sector_flags"].get("tailwind", [])}
    headwinds = {h["sector"]: h["reason"] for h in decision["sector_flags"].get("headwind", [])}

    actionable  = []   # Strong RS + passes threshold + no headwind
    flagged     = []   # Weak/Mixed RS but has macro tailwind
    suppressed  = []   # Strong RS but has macro headwind
    watch       = []   # Strong RS, passes threshold, minor note

    for r in sector_scores:
        sector   = r["name"]
        prc      = r["prc"]
        category = r["category"]

        has_tailwind = sector in tailwinds
        has_headwind = sector in headwinds

        if has_headwind and category == "STRONG":
            suppressed.append({**r, "reason": headwinds[sector]})

        elif has_tailwind and category != "STRONG":
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


# ── Build Telegram messages ───────────────────────────────────────────────────

def build_messages(decision: dict, adjusted: dict, context: dict) -> list:
    """
    Builds up to 3 Telegram messages:
      1. Regime + macro summary + actionable sectors
      2. Flagged (tailwind) + suppressed (headwind) sectors
      3. Macro signal breakdown (key findings per topic)
    """
    today_fmt  = date.today().strftime("%d %b %Y")
    regime     = decision["regime"]
    score      = decision["final_score"]
    threshold  = adjusted["threshold"]
    prc_adj    = decision["prc_adjustment"]

    regime_emoji = {"BULL": "🐂", "NEUTRAL": "⚖️", "BEAR": "🐻"}.get(regime, "❓")

    # ── Message 1 — Regime + Actionable sectors ───────────────────────────────
    msg1  = f"🤖 *MACRO OVERLAY — {today_fmt}*\n\n"
    msg1 += f"{regime_emoji} *Regime: {regime}* (score: {score}/100)\n"
    msg1 += f"_{decision.get('regime_reason', '')}_\n\n"

    # Market context summary from Gemini
    summary = decision.get("summary", "")
    if summary:
        msg1 += f"📰 {summary}\n\n"

    # Quantitative signals snapshot
    vix   = context["vix_signal"]
    mom   = context["mom_signal"]
    sma   = context["sma_signal"]
    msg1 += f"`Nifty vs 20W SMA : {'✅ ABOVE' if sma['above_20w'] else '❌ BELOW'} ({sma['pct_from_20w']:+.1f}%)`\n"
    msg1 += f"`Nifty vs 50W SMA : {'✅ ABOVE' if sma['above_50w'] else '❌ BELOW'} ({sma['pct_from_50w']:+.1f}%)`\n"
    msg1 += f"`India VIX        : {vix['vix_now']} ({'⬆️ rising' if vix['vix_rising'] else '⬇️ falling'})`\n"
    msg1 += f"`Nifty 3M Return  : {mom['nifty_3m_return']:+.1f}%`\n\n"

    # Adjusted threshold note
    if prc_adj != 0:
        direction = "lowered" if prc_adj < 0 else "raised"
        msg1 += f"_PRC threshold {direction} to {threshold} ({prc_adj:+d} for {regime} regime)_\n\n"

    # Actionable sectors
    if adjusted["actionable"]:
        msg1 += f"✅ *ACTIONABLE — PRC ≥ {threshold}*\n"
        for r in adjusted["actionable"]:
            p3 = f"{r.get('p3', 0):+.1f}%" if r.get('p3') is not None else "N/A"
            p6 = f"{r.get('p6', 0):+.1f}%" if r.get('p6') is not None else "N/A"
            msg1 += f"`{r['name'][:10].ljust(10)} PRC:{r['prc']:>3}  3M:{p3}  6M:{p6}`\n"
    else:
        msg1 += "ℹ️ No sectors meet the adjusted threshold this week.\n"

    # ── Message 2 — Flags + Suppressions (plain text) ────────────────────────
    msg2 = f"🤖 MACRO OVERLAY — {today_fmt} (cont.)\n\n"

    if adjusted["flagged"]:
        msg2 += "⚡ MACRO TAILWIND (watch despite weak RS)\n"
        for r in adjusted["flagged"]:
            msg2 += f"{r['name']}: {r['reason']}\n"
        msg2 += "\n"

    if adjusted["suppressed"]:
        msg2 += "⚠️  MACRO HEADWIND (caution despite strong RS)\n"
        for r in adjusted["suppressed"]:
            msg2 += f"{r['name']}: {r['reason']}\n"
        msg2 += "\n"

    if adjusted["watch"]:
        msg2 += f"👀 WATCH (Strong but PRC below {threshold})\n"
        for r in adjusted["watch"]:
            msg2 += f"{r['name']}  PRC:{r['prc']}\n"

    if not any([adjusted["flagged"], adjusted["suppressed"], adjusted["watch"]]):
        msg2 += "No additional flags this week."

    # ── Message 3 — Macro findings breakdown ─────────────────────────────────
    macro_scores = decision.get("macro_scores", {})
    msg3 = f"📰 MACRO FINDINGS — {today_fmt}\n\n"

    for key, val in macro_scores.items():
        score   = val.get("score", "?")
        finding = val.get("finding", "No data")
        bar     = "🟢" if score >= 65 else "🔴" if score <= 35 else "🟡"
        label   = key.replace("_", " ").title()
        msg3   += f"{bar} {label} ({score})\n{finding}\n\n"

    return [msg1, msg2, msg3]


# ── Main ──────────────────────────────────────────────────────────────────────

def run_macro_agent():
    print("\n🤖 --- MACRO AGENT START ---")

    # ── Load config ───────────────────────────────────────────────────────────
    with open("config.json", "r") as f:
        config = json.load(f)

    # ── Read sector scores from agent.py output ───────────────────────────────
    try:
        with open("sector_scores.json", "r") as f:
            sector_scores = json.load(f)
        print(f"📂 Loaded {len(sector_scores)} sector scores from sector_scores.json")
    except FileNotFoundError:
        print("❌ sector_scores.json not found — run agent.py first")
        return
    except Exception as e:
        print(f"❌ Failed to load sector_scores.json: {e}")
        return

    # ── Get quantitative market context ───────────────────────────────────────
    context = get_market_context(config)

    # ── Get LLM macro decision ────────────────────────────────────────────────
    decision = get_llm_decision(
        quant_score    = context["quant_score"],
        signal_summary = context["signal_summary"],
        sector_scores  = sector_scores,
        config         = config,
    )

    # ── Apply decision to sectors ─────────────────────────────────────────────
    adjusted = apply_decision(sector_scores, decision, config)

    print(f"\n📊 Regime: {decision['regime']} | Score: {decision['final_score']}/100")
    print(f"   Threshold: {adjusted['threshold']} (base {BASE_PRC_THRESHOLD} {decision['prc_adjustment']:+d})")
    print(f"   Actionable: {len(adjusted['actionable'])} sectors")
    print(f"   Flagged:    {len(adjusted['flagged'])} sectors")
    print(f"   Suppressed: {len(adjusted['suppressed'])} sectors")

    # ── Save macro output ─────────────────────────────────────────────────────
    output = {
        "decision": decision,
        "adjusted": adjusted,
        "context" : {
            "quant_score"   : context["quant_score"],
            "signal_summary": context["signal_summary"],
        },
        "scan_date": str(date.today()),
    }
    with open("macro_output.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print("💾 macro_output.json saved")

    # ── Build and send Telegram messages ──────────────────────────────────────
    messages = build_messages(decision, adjusted, context)

    send_telegram(messages[0])                        # regime + actionable (markdown)
    send_telegram(messages[1], use_markdown=False)    # flags + suppressions (plain)
    send_telegram(messages[2], use_markdown=False)    # macro findings (plain)

    print("\n✅ Macro agent complete.")


if __name__ == "__main__":
    run_macro_agent()
