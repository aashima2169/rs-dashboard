"""
llm_decision.py
---------------
Calls Gemini API with Google Search grounding to analyse
current macro conditions and return a structured regime decision.
Uses the new google-genai package (replaces deprecated google-generativeai).
"""

import os
import json
from datetime import date

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


# ── Gemini client ─────────────────────────────────────────────────────────────

def get_gemini():
    if not GEMINI_API_KEY:
        print("⚠️  GEMINI_API_KEY not set — LLM decision skipped")
        return None
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        print("✅ Gemini client ready")
        return client
    except Exception as e:
        print(f"❌ Gemini setup failed: {e}")
        return None


# ── Build prompt ──────────────────────────────────────────────────────────────

def build_prompt(quant_score, signal_summary, sector_scores, config):
    queries     = config.get("market_signals", {}).get("qualitative", {}).get("search_queries", {})
    macro_links = config.get("market_signals", {}).get("sector_macro_links", {})

    scores_text = ""
    for r in sector_scores:
        scores_text += (
            f"  {r['name']:<14} PRC:{r['prc']:>3}  "
            f"3M:{r.get('p3', 'N/A')}%  "
            f"6M:{r.get('p6', 'N/A')}%  "
            f"Cat:{r['category']}\n"
        )

    links_text = ""
    for sector, factors in macro_links.items():
        links_text += f"  {sector}: {', '.join(factors)}\n"

    topics_text = ""
    for key, q in queries.items():
        topics_text += f"  {key} (weight:{q['weight']}): {q['query']}\n"

    today_date = date.today().strftime("%d %b %Y")
    return f"""
You are an expert Indian equity market analyst.
Today is {date.today().strftime('%d %b %Y')}.

QUANTITATIVE SIGNALS:
{signal_summary}

SECTOR RS SCORES:
{scores_text}

SECTOR-MACRO LINKS:
{links_text}

Search the web for current information on:
{topics_text}

Based on findings and quantitative signals, return ONLY valid JSON:
{{
  "macro_scores": {{
    "fii_dii_flows"    : {{"score": 0, "finding": "what you found"}},
    "rbi_policy"       : {{"score": 0, "finding": "what you found"}},
    "rupee_dollar"     : {{"score": 0, "finding": "what you found"}},
    "crude_oil"        : {{"score": 0, "finding": "what you found"}},
    "global_risk"      : {{"score": 0, "finding": "what you found"}},
    "tariffs_trade"    : {{"score": 0, "finding": "what you found"}},
    "geopolitical_war" : {{"score": 0, "finding": "what you found"}},
    "customs_duty_bans": {{"score": 0, "finding": "what you found"}},
    "healthcare_virus" : {{"score": 0, "finding": "what you found"}},
    "domestic_policy"  : {{"score": 0, "finding": "what you found"}}
  }},
  "sector_flags": {{
    "tailwind": [{{"sector": "Name", "reason": "reason"}}],
    "headwind": [{{"sector": "Name", "reason": "reason"}}]
  }},
  "regime"       : "BULL or NEUTRAL or BEAR",
  "regime_reason": "one sentence",
  "summary"      : "line 1. line 2."
}}

IMPORTANT INSTRUCTIONS:
- Only use news from the last 14 days. Today is {today_date}.
- If no significant news exists for a topic in the last 14 days, return null for that topic.
- Do NOT use articles older than 14 days.
- Do NOT fabricate or assume news.

Score 0-100: 0=very bearish, 50=neutral, 100=very bullish for Indian equities.
For topics with recent news: return score + finding.
For topics with no recent news: return null.

Example of null topic:
  "rbi_policy": null

No markdown, no explanation, JSON only.
""".strip()


# ── Qualitative score ─────────────────────────────────────────────────────────

def compute_qualitative_score(macro_scores, config):
    queries      = config.get("market_signals", {}).get("qualitative", {}).get("search_queries", {})
    total_weight = 0
    weighted_sum = 0
    for key, q in queries.items():
        weight    = q.get("weight", 10)
        val       = macro_scores.get(key)
        # null topic = no recent news, treat as neutral 50 for scoring only
        score     = val.get("score", 50) if val else 50
        weighted_sum += score * weight
        total_weight += weight
    return round(weighted_sum / total_weight) if total_weight else 50


# ── Final regime ──────────────────────────────────────────────────────────────

def compute_final_regime(quant_score, qual_score, config):
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


def get_prc_adjustment(regime, config):
    adjustments = config.get("market_signals", {}).get("prc_adjustments", {})
    return adjustments.get(regime.lower(), 0)


# ── Main ──────────────────────────────────────────────────────────────────────

def get_llm_decision(quant_score, signal_summary, sector_scores, config):
    print("\n🤖 Running LLM macro analysis...")

    client = get_gemini()
    if not client:
        return _fallback_decision(quant_score, config)

    prompt = build_prompt(quant_score, signal_summary, sector_scores, config)

    try:
        from google import genai
        from google.genai import types

        print("  📡 Calling Gemini with Google Search grounding...")

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

        raw = response.text.strip()

        # Strip markdown fences if present
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                try:
                    json.loads(part)
                    raw = part
                    break
                except Exception:
                    continue

        decision_raw = json.loads(raw)
        print("  ✅ Gemini response parsed successfully")

    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parse failed: {e}")
        return _fallback_decision(quant_score, config)
    except Exception as e:
        print(f"  ❌ Gemini call failed: {type(e).__name__}: {e}")
        return _fallback_decision(quant_score, config)

    macro_scores            = decision_raw.get("macro_scores", {})
    qual_score              = compute_qualitative_score(macro_scores, config)
    regime, final_score     = compute_final_regime(quant_score, qual_score, config)

    # Defer to LLM regime if it disagrees (it saw the news)
    llm_regime = decision_raw.get("regime", regime)
    if llm_regime != regime:
        print(f"  ℹ️  Score regime: {regime} → LLM regime: {llm_regime} — using LLM")
        regime = llm_regime

    prc_adjustment = get_prc_adjustment(regime, config)

    decision = {
        "regime"        : regime,
        "final_score"   : final_score,
        "quant_score"   : quant_score,
        "qual_score"    : qual_score,
        "prc_adjustment": prc_adjustment,
        "macro_scores"  : macro_scores,
        "sector_flags"  : decision_raw.get("sector_flags", {"tailwind": [], "headwind": []}),
        "regime_reason" : decision_raw.get("regime_reason", ""),
        "summary"       : decision_raw.get("summary", ""),
        "scan_date"     : str(date.today()),
    }

    print(f"\n  📊 Quant:{quant_score} | Qual:{qual_score} | Final:{final_score}")
    print(f"  🎯 Regime: {regime} (PRC adj: {prc_adjustment:+d})")
    for key, val in macro_scores.items():
        if val is None:
            print(f"     {key:<22} No recent news")
        else:
            print(f"     {key:<22} score:{val.get('score','?'):>3}  {val.get('finding','')}")

    return decision


def _fallback_decision(quant_score, config):
    print("  ⚠️  Fallback: quant signals only")
    regime = "BULL" if quant_score >= 65 else "BEAR" if quant_score <= 35 else "NEUTRAL"
    return {
        "regime"        : regime,
        "final_score"   : quant_score,
        "quant_score"   : quant_score,
        "qual_score"    : None,
        "prc_adjustment": get_prc_adjustment(regime, config),
        "macro_scores"  : {},
        "sector_flags"  : {"tailwind": [], "headwind": []},
        "regime_reason" : f"Quantitative signals only (score: {quant_score})",
        "summary"       : "Macro web analysis unavailable — quantitative signals only.",
        "scan_date"     : str(date.today()),
    }


if __name__ == "__main__":
    import json
    from market_context import get_market_context
    with open("config.json", "r") as f:
        config = json.load(f)
    context = get_market_context(config)
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
