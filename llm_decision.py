"""
llm_decision.py
---------------
Calls Gemini API with Google Search grounding to:
  1. Search for current macro signals (FII flows, RBI, tariffs, etc.)
  2. Score each signal qualitatively (0-100)
  3. Combine with quantitative score from market_context.py
  4. Determine market regime (Bull / Neutral / Bear)
  5. Adjust PRC thresholds and flag sectors with tailwinds/headwinds

Returns a structured decision dict consumed by macro_agent.py
"""

import os
import json
import time
import google.generativeai as genai
from datetime import date

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


# ── Gemini client ─────────────────────────────────────────────────────────────

def get_gemini():
    if not GEMINI_API_KEY:
        print("⚠️  GEMINI_API_KEY not set — LLM decision skipped")
        return None
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-pro",
            generation_config={"temperature": 0.2},  # low temp for consistent JSON
        )
        print("✅ Gemini client ready")
        return model
    except Exception as e:
        print(f"❌ Gemini setup failed: {e}")
        return None


# ── Build search queries ──────────────────────────────────────────────────────

def build_search_context(config: dict) -> str:
    """
    Returns a formatted string of all search queries from config.
    Gemini uses these to ground its response in current web data.
    """
    queries = config.get("market_signals", {}).get(
        "qualitative", {}
    ).get("search_queries", {})

    lines = []
    for key, q in queries.items():
        lines.append(f"- {q['query']}")

    return "\n".join(lines)


# ── Build prompt ──────────────────────────────────────────────────────────────

def build_prompt(
    quant_score    : int,
    signal_summary : str,
    sector_scores  : list[dict],
    config         : dict,
) -> str:
    """
    Builds the full prompt sent to Gemini.
    Includes quantitative signals, sector RS scores,
    and instructions to search + score macro factors.
    """
    queries    = config.get("market_signals", {}).get(
        "qualitative", {}
    ).get("search_queries", {})

    macro_links = config.get("market_signals", {}).get("sector_macro_links", {})

    # Format sector scores for prompt
    scores_text = ""
    for r in sector_scores:
        scores_text += (
            f"  {r['name']:<14} PRC:{r['prc']:>3}  "
            f"3M:{r.get('p3', 'N/A')}%  "
            f"6M:{r.get('p6', 'N/A')}%  "
            f"Cat:{r['category']}\n"
        )

    # Format macro links for prompt
    links_text = ""
    for sector, factors in macro_links.items():
        links_text += f"  {sector}: {', '.join(factors)}\n"

    # Format search topics for prompt
    topics_text = ""
    for key, q in queries.items():
        topics_text += f"  {key} (weight:{q['weight']}): {q['query']}\n"

    prompt = f"""
You are an expert Indian equity market analyst with deep knowledge of macro factors.

Today is {date.today().strftime('%d %b %Y')}.

═══════════════════════════════════════════
QUANTITATIVE MARKET SIGNALS (pre-calculated)
═══════════════════════════════════════════
{signal_summary}

═══════════════════════════════════════════
THIS WEEK'S SECTOR RS SCORES
═══════════════════════════════════════════
{scores_text}

═══════════════════════════════════════════
SECTOR-MACRO RELATIONSHIPS
═══════════════════════════════════════════
{links_text}

═══════════════════════════════════════════
YOUR TASK
═══════════════════════════════════════════

Search the web for CURRENT information on each of these topics:
{topics_text}

Based on what you find AND the quantitative signals above:

1. Score each macro topic 0-100 for Indian equities:
   0   = Very bearish (e.g. heavy FII selling, rate hike, new pandemic)
   50  = Neutral (no significant news)
   100 = Very bullish (e.g. heavy FII buying, rate cut, trade deal)

2. Identify sector-specific impacts:
   - TAILWIND: sector likely to benefit from current macro (even if RS is weak)
   - HEADWIND: sector likely to face pressure (even if RS is strong)

3. Determine overall market regime:
   - BULL   if overall conditions favour broad participation
   - BEAR   if conditions suggest caution and selectivity
   - NEUTRAL if mixed signals

4. Write a 2-line market context summary for a Telegram message.
   Be specific — mention actual events found (e.g. "FIIs bought ₹8,200cr this week")
   Not generic — avoid phrases like "markets remain volatile"

═══════════════════════════════════════════
RESPOND IN VALID JSON ONLY
No preamble, no markdown, no explanation outside the JSON.
═══════════════════════════════════════════

{{
  "macro_scores": {{
    "fii_dii_flows"    : {{ "score": 0-100, "finding": "one line of what you found" }},
    "rbi_policy"       : {{ "score": 0-100, "finding": "one line of what you found" }},
    "rupee_dollar"     : {{ "score": 0-100, "finding": "one line of what you found" }},
    "crude_oil"        : {{ "score": 0-100, "finding": "one line of what you found" }},
    "global_risk"      : {{ "score": 0-100, "finding": "one line of what you found" }},
    "tariffs_trade"    : {{ "score": 0-100, "finding": "one line of what you found" }},
    "geopolitical_war" : {{ "score": 0-100, "finding": "one line of what you found" }},
    "customs_duty_bans": {{ "score": 0-100, "finding": "one line of what you found" }},
    "healthcare_virus" : {{ "score": 0-100, "finding": "one line of what you found" }},
    "domestic_policy"  : {{ "score": 0-100, "finding": "one line of what you found" }}
  }},
  "sector_flags": {{
    "tailwind": [
      {{ "sector": "SectorName", "reason": "specific reason from current news" }}
    ],
    "headwind": [
      {{ "sector": "SectorName", "reason": "specific reason from current news" }}
    ]
  }},
  "regime"         : "BULL or NEUTRAL or BEAR",
  "regime_reason"  : "one sentence explaining the regime call",
  "summary"        : "line 1 of Telegram summary. line 2 of Telegram summary."
}}
""".strip()

    return prompt


# ── Compute qualitative score ─────────────────────────────────────────────────

def compute_qualitative_score(macro_scores: dict, config: dict) -> int:
    """
    Weighted average of all macro topic scores.
    Weights come from config.json search_queries block.
    """
    queries      = config.get("market_signals", {}).get(
        "qualitative", {}
    ).get("search_queries", {})

    total_weight = 0
    weighted_sum = 0

    for key, q in queries.items():
        weight = q.get("weight", 10)
        score  = macro_scores.get(key, {}).get("score", 50)  # default neutral
        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0:
        return 50

    return round(weighted_sum / total_weight)


# ── Compute final regime ──────────────────────────────────────────────────────

def compute_final_regime(
    quant_score : int,
    qual_score  : int,
    config      : dict,
) -> tuple[str, int]:
    """
    Combines quant and qualitative scores using weights from config.
    Returns (regime, final_score).
    """
    weights     = config.get("market_signals", {}).get("weights", {})
    quant_wt    = weights.get("quantitative", 60) / 100
    qual_wt     = weights.get("qualitative", 40) / 100

    final_score = round((quant_score * quant_wt) + (qual_score * qual_wt))

    thresholds  = config.get("market_signals", {}).get("regime_thresholds", {})
    bull_min    = thresholds.get("bull_score_min", 65)
    bear_max    = thresholds.get("bear_score_max", 35)

    if final_score >= bull_min:
        regime = "BULL"
    elif final_score <= bear_max:
        regime = "BEAR"
    else:
        regime = "NEUTRAL"

    return regime, final_score


# ── Get PRC adjustment ────────────────────────────────────────────────────────

def get_prc_adjustment(regime: str, config: dict) -> int:
    """
    Returns the PRC threshold adjustment based on regime.
    Negative = lower threshold (more sectors pass in bull)
    Positive = raise threshold (fewer sectors pass in bear)
    """
    adjustments = config.get("market_signals", {}).get("prc_adjustments", {})
    return adjustments.get(regime.lower(), 0)


# ── Main function ─────────────────────────────────────────────────────────────

def get_llm_decision(
    quant_score    : int,
    signal_summary : str,
    sector_scores  : list[dict],
    config         : dict,
) -> dict:
    """
    Main entry point called by macro_agent.py.
    Returns full decision dict.
    """
    print("\n🤖 Running LLM macro analysis...")

    model = get_gemini()
    if not model:
        return _fallback_decision(quant_score, config)

    prompt = build_prompt(quant_score, signal_summary, sector_scores, config)

    try:
        print("  📡 Calling Gemini with web search grounding...")

        # Enable Google Search grounding
        response = model.generate_content(
            contents=prompt,
            tools=[{"google_search_retrieval": {}}],
        )

        raw = response.text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        decision_raw = json.loads(raw)
        print("  ✅ Gemini response received and parsed")

    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parse failed: {e}")
        print(f"  Raw response: {raw[:500]}")
        return _fallback_decision(quant_score, config)

    except Exception as e:
        print(f"  ❌ Gemini call failed: {type(e).__name__}: {e}")
        return _fallback_decision(quant_score, config)

    # ── Compute scores ────────────────────────────────────────────────────────
    macro_scores = decision_raw.get("macro_scores", {})
    qual_score   = compute_qualitative_score(macro_scores, config)
    regime, final_score = compute_final_regime(quant_score, qual_score, config)

    # Use Gemini's regime if it strongly disagrees (it saw the news)
    llm_regime = decision_raw.get("regime", regime)
    if llm_regime != regime:
        print(f"  ℹ️  Score-based regime: {regime}, LLM regime: {llm_regime} — using LLM")
        regime = llm_regime

    prc_adjustment = get_prc_adjustment(regime, config)

    decision = {
        "regime"         : regime,
        "final_score"    : final_score,
        "quant_score"    : quant_score,
        "qual_score"     : qual_score,
        "prc_adjustment" : prc_adjustment,
        "macro_scores"   : macro_scores,
        "sector_flags"   : decision_raw.get("sector_flags", {"tailwind": [], "headwind": []}),
        "regime_reason"  : decision_raw.get("regime_reason", ""),
        "summary"        : decision_raw.get("summary", ""),
        "scan_date"      : str(date.today()),
    }

    # ── Log findings ──────────────────────────────────────────────────────────
    print(f"\n  📊 Scores: Quant={quant_score} | Qual={qual_score} | Final={final_score}")
    print(f"  🎯 Regime: {regime} (PRC adjustment: {prc_adjustment:+d})")
    print(f"  📰 Key findings:")
    for key, val in macro_scores.items():
        score   = val.get("score", "?")
        finding = val.get("finding", "")
        print(f"     {key:<20} score:{score:>3}  {finding}")

    tailwinds = decision["sector_flags"].get("tailwind", [])
    headwinds = decision["sector_flags"].get("headwind", [])
    if tailwinds:
        print(f"  ⚡ Tailwinds: {[t['sector'] for t in tailwinds]}")
    if headwinds:
        print(f"  ⚠️  Headwinds: {[h['sector'] for h in headwinds]}")

    return decision


# ── Fallback if Gemini fails ──────────────────────────────────────────────────

def _fallback_decision(quant_score: int, config: dict) -> dict:
    """
    Returns a neutral decision based on quant score alone
    if Gemini is unavailable.
    """
    print("  ⚠️  Using fallback decision (quant only)")

    if quant_score >= 65:
        regime = "BULL"
    elif quant_score <= 35:
        regime = "BEAR"
    else:
        regime = "NEUTRAL"

    prc_adjustment = get_prc_adjustment(regime, config)

    return {
        "regime"         : regime,
        "final_score"    : quant_score,
        "quant_score"    : quant_score,
        "qual_score"     : None,
        "prc_adjustment" : prc_adjustment,
        "macro_scores"   : {},
        "sector_flags"   : {"tailwind": [], "headwind": []},
        "regime_reason"  : f"Based on quantitative signals only (score: {quant_score})",
        "summary"        : "Macro analysis unavailable — quantitative signals only.",
        "scan_date"      : str(date.today()),
    }


if __name__ == "__main__":
    # Quick test — runs without macro_agent.py
    import json
    from market_context import get_market_context

    with open("config.json", "r") as f:
        config = json.load(f)

    # Get quantitative context
    context = get_market_context(config)

    # Dummy sector scores for testing
    test_scores = [
        {"name": "Metal",  "prc": 55, "p3": 19.3, "p6": 37.5, "category": "STRONG"},
        {"name": "Pharma", "prc": 62, "p3": 21.7, "p6": 19.8, "category": "STRONG"},
        {"name": "IT",     "prc": 8,  "p3": -14.9,"p6": -16.0,"category": "WEAK"},
    ]

    decision = get_llm_decision(
        quant_score    = context["quant_score"],
        signal_summary = context["signal_summary"],
        sector_scores  = test_scores,
        config         = config,
    )

    print("\n✅ Decision:")
    print(json.dumps(decision, indent=2))
