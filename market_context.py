"""
market_context.py
-----------------
Fetches quantitative market signals used by the macro agent.
All data sourced from yfinance — no API keys needed.

Signals:
  1. Nifty 50 vs 20-week SMA   (broad trend)
  2. Nifty 50 vs 50-week SMA   (long term trend)
  3. India VIX level            (fear gauge)
  4. India VIX direction        (is fear rising or falling)
  5. Nifty 3M momentum          (is market accelerating)

Returns a structured dict consumed by llm_decision.py
"""

import yfinance as yf
import pandas as pd
from datetime import date


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_weekly_close(ticker: str, period: str = "2y") -> pd.Series:
    """Downloads weekly OHLCV and returns Close series."""
    df = yf.download(ticker, period=period, interval="1wk",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df["Close"].dropna()


def get_daily_close(ticker: str, period: str = "1y") -> pd.Series:
    """Downloads daily OHLCV and returns Close series."""
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df["Close"].dropna()


# ── Individual signal functions ───────────────────────────────────────────────

def get_nifty_sma_signal(weekly_close: pd.Series, config: dict) -> dict:
    """
    Checks Nifty 50 vs 20-week and 50-week SMAs.
    Returns score contribution and direction for each.
    """
    cfg_20 = config["quantitative"]["nifty_vs_20w_sma"]
    cfg_50 = config["quantitative"]["nifty_vs_50w_sma"]

    cmp     = float(weekly_close.iloc[-1])
    sma_20w = float(weekly_close.tail(20).mean())
    sma_50w = float(weekly_close.tail(50).mean()) if len(weekly_close) >= 50 else None

    above_20w = cmp > sma_20w
    above_50w = (cmp > sma_50w) if sma_50w else None

    score_20w = cfg_20["weight"] if above_20w else 0
    score_50w = (cfg_50["weight"] if above_50w else 0) if above_50w is not None else 0

    pct_from_20w = round(((cmp - sma_20w) / sma_20w) * 100, 2)
    pct_from_50w = round(((cmp - sma_50w) / sma_50w) * 100, 2) if sma_50w else None

    return {
        "cmp"          : round(cmp, 2),
        "sma_20w"      : round(sma_20w, 2),
        "sma_50w"      : round(sma_50w, 2) if sma_50w else None,
        "above_20w"    : above_20w,
        "above_50w"    : above_50w,
        "pct_from_20w" : pct_from_20w,
        "pct_from_50w" : pct_from_50w,
        "score_20w"    : score_20w,
        "score_50w"    : score_50w,
        "label_20w"    : f"Nifty {'ABOVE' if above_20w else 'BELOW'} 20W SMA by {abs(pct_from_20w)}%",
        "label_50w"    : f"Nifty {'ABOVE' if above_50w else 'BELOW'} 50W SMA by {abs(pct_from_50w)}%" if pct_from_50w else "N/A",
    }


def get_vix_signal(config: dict) -> dict:
    """
    Fetches India VIX and calculates:
      - Current level vs calm/fearful thresholds
      - Direction (rising or falling vs 4 weeks ago)
    """
    cfg_level = config["quantitative"]["india_vix"]
    cfg_dir   = config["quantitative"]["vix_direction"]

    try:
        vix_series = get_weekly_close("^INDIAVIX", period="6m")
        if vix_series.empty:
            raise ValueError("Empty VIX data")

        vix_now  = float(vix_series.iloc[-1])
        vix_4w   = float(vix_series.iloc[-4]) if len(vix_series) >= 4 else vix_now
        vix_rising = vix_now > vix_4w

        calm_below    = cfg_level["calm_below"]
        fearful_above = cfg_level["fearful_above"]

        if vix_now < calm_below:
            vix_score = cfg_level["weight"]
            vix_label = f"VIX {vix_now:.1f} — CALM (below {calm_below})"
        elif vix_now > fearful_above:
            vix_score = 0
            vix_label = f"VIX {vix_now:.1f} — FEARFUL (above {fearful_above})"
        else:
            vix_score = cfg_level["weight"] // 2
            vix_label = f"VIX {vix_now:.1f} — NEUTRAL ({calm_below}–{fearful_above})"

        dir_score = 0 if vix_rising else cfg_dir["weight"]
        dir_label = f"VIX {'RISING' if vix_rising else 'FALLING'} vs 4 weeks ago ({vix_4w:.1f} → {vix_now:.1f})"

        return {
            "vix_now"   : round(vix_now, 2),
            "vix_4w_ago": round(vix_4w, 2),
            "vix_rising": vix_rising,
            "vix_score" : vix_score,
            "dir_score" : dir_score,
            "vix_label" : vix_label,
            "dir_label" : dir_label,
        }

    except Exception as e:
        print(f"  ⚠️  VIX fetch failed: {e}")
        return {
            "vix_now"   : None,
            "vix_4w_ago": None,
            "vix_rising": None,
            "vix_score" : 0,
            "dir_score" : 0,
            "vix_label" : "VIX data unavailable",
            "dir_label" : "VIX direction unavailable",
        }


def get_nifty_momentum_signal(daily_close: pd.Series, config: dict) -> dict:
    """
    Checks whether Nifty 50 itself has positive 3M momentum.
    Simple but useful — if the benchmark is weak, everything is harder.
    """
    cfg = config["quantitative"]["nifty_momentum"]

    if len(daily_close) < 63:
        return {
            "nifty_3m_return": None,
            "momentum_score" : 0,
            "momentum_label" : "Insufficient data for momentum",
        }

    nifty_3m = round(((daily_close.iloc[-1] / daily_close.iloc[-63]) - 1) * 100, 2)
    score    = cfg["weight"] if nifty_3m > 0 else 0
    label    = f"Nifty 3M return: {'+' if nifty_3m >= 0 else ''}{nifty_3m}% — {'POSITIVE' if nifty_3m > 0 else 'NEGATIVE'}"

    return {
        "nifty_3m_return": nifty_3m,
        "momentum_score" : score,
        "momentum_label" : label,
    }


# ── Main function ─────────────────────────────────────────────────────────────

def get_market_context(config: dict) -> dict:
    """
    Fetches all quantitative market signals and computes
    a composite quantitative score (0-100).

    Returns a structured dict consumed by llm_decision.py
    """
    print("\n📡 Fetching market context signals...")

    cfg_signals = config.get("market_signals", {})
    cfg_quant   = cfg_signals.get("quantitative", {})

    # ── Download data ─────────────────────────────────────────────────────────
    print("  📥 Downloading Nifty 50 weekly data...")
    nifty_weekly = get_weekly_close("^NSEI", period="2y")

    print("  📥 Downloading Nifty 50 daily data...")
    nifty_daily  = get_daily_close("^NSEI", period="1y")

    # ── Calculate signals ─────────────────────────────────────────────────────
    print("  🔢 Calculating SMA signals...")
    sma_signal = get_nifty_sma_signal(nifty_weekly, cfg_quant)

    print("  🔢 Calculating VIX signals...")
    vix_signal = get_vix_signal(cfg_quant)

    print("  🔢 Calculating Nifty momentum...")
    mom_signal = get_nifty_momentum_signal(nifty_daily, cfg_quant)

    # ── Composite quantitative score ──────────────────────────────────────────
    quant_score = (
        sma_signal["score_20w"]   +
        sma_signal["score_50w"]   +
        vix_signal["vix_score"]   +
        vix_signal["dir_score"]   +
        mom_signal["momentum_score"]
    )

    # Max possible = sum of all weights
    max_score = (
        cfg_quant.get("nifty_vs_20w_sma", {}).get("weight", 30) +
        cfg_quant.get("nifty_vs_50w_sma", {}).get("weight", 20) +
        cfg_quant.get("india_vix", {}).get("weight", 25)        +
        cfg_quant.get("vix_direction", {}).get("weight", 10)    +
        cfg_quant.get("nifty_momentum", {}).get("weight", 15)
    )

    # Normalise to 0-100
    quant_score_normalised = round((quant_score / max_score) * 100) if max_score > 0 else 0

    # ── Human-readable signal summary (passed to Gemini) ─────────────────────
    signal_summary = f"""
QUANTITATIVE MARKET SIGNALS — {date.today().strftime('%d %b %Y')}

Nifty 50:
  {sma_signal['label_20w']}
  {sma_signal['label_50w']}
  {mom_signal['momentum_label']}

India VIX:
  {vix_signal['vix_label']}
  {vix_signal['dir_label']}

Quantitative Score: {quant_score_normalised}/100
""".strip()

    print(f"\n📊 Quantitative score: {quant_score_normalised}/100")
    print(signal_summary)

    return {
        "quant_score"    : quant_score_normalised,
        "signal_summary" : signal_summary,
        "sma_signal"     : sma_signal,
        "vix_signal"     : vix_signal,
        "mom_signal"     : mom_signal,
        "scan_date"      : str(date.today()),
    }


if __name__ == "__main__":
    import json
    with open("config.json", "r") as f:
        config = json.load(f)
    context = get_market_context(config)
    print("\n✅ Market context fetched successfully")
