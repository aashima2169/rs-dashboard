"""
backfill_eval_daily.py
----------------------
Reconstructs eval_daily from historical data (past 15-20 days).

Uses:
  1. macro_summaries table (already has regime + score from your past runs)
  2. Nifty OHLC from yfinance (historical prices)

Outputs:
  - Fills eval_daily table with backfilled data
  - Shows accuracy baseline
  - Verifies model performance
"""

import os
import sys
from datetime import date, timedelta
import yfinance as yf
import pandas as pd

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def get_supabase():
    """Connect to Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Supabase env vars not set")
        return None
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        return None


def get_nifty_ohlc_bulk(start_date: str, end_date: str):
    """
    Fetch Nifty OHLC for a date range.
    
    Args:
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
    
    Returns:
        dict keyed by date with OHLC data
    """
    try:
        nifty = yf.download("^NSEI", start=start_date, end=end_date, progress=False)
        
        if nifty.empty:
            print(f"⚠️  No Nifty data for {start_date} to {end_date}")
            return {}
        
        result = {}
        for idx, row in nifty.iterrows():
            date_str = idx.strftime("%Y-%m-%d")
            result[date_str] = {
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
            }
        
        print(f"✅ Fetched Nifty OHLC for {len(result)} trading days")
        return result
        
    except Exception as e:
        print(f"❌ Failed to fetch Nifty OHLC: {e}")
        return {}


def backfill_eval_daily(days_back: int = 20):
    """
    Backfill eval_daily from historical macro_summaries + Nifty OHLC.
    
    Args:
        days_back: how many days to go back (default 20)
    """
    print("\n🔄 --- BACKFILL EVAL_DAILY START ---\n")
    
    sb = get_supabase()
    if not sb:
        print("❌ Cannot proceed without Supabase")
        return
    
    # ── Step 1: Fetch historical macro_summaries ──────────────────────────────
    print(f"📖 Fetching macro_summaries from past {days_back} days...")
    
    since_date = str(date.today() - timedelta(days=days_back))
    
    try:
        result = sb.table("macro_summaries") \
            .select("scan_date, regime, final_score") \
            .gte("scan_date", since_date) \
            .order("scan_date") \
            .execute()
        
        if not result.data:
            print(f"⚠️  No macro_summaries found since {since_date}")
            return
        
        summaries = pd.DataFrame(result.data)
        print(f"✅ Found {len(summaries)} historical predictions")
        print(f"   Date range: {summaries['scan_date'].min()} to {summaries['scan_date'].max()}")
        
    except Exception as e:
        print(f"❌ Failed to fetch macro_summaries: {e}")
        return
    
    # ── Step 2: Fetch Nifty OHLC for the date range ────────────────────────────
    print(f"\n📈 Fetching Nifty OHLC...")
    
    start_date = summaries['scan_date'].min()
    end_date = summaries['scan_date'].max()
    
    nifty_ohlc = get_nifty_ohlc_bulk(start_date, end_date)
    if not nifty_ohlc:
        print("❌ Could not fetch Nifty OHLC")
        return
    
    # ── Step 3: Reconstruct eval_daily ────────────────────────────────────────
    print(f"\n🔨 Reconstructing eval_daily...\n")
    
    eval_rows = []
    mismatches = []
    
    for _, row in summaries.iterrows():
        scan_date = row["scan_date"]
        predicted_regime = row["regime"]
        predicted_score = row["final_score"]
        
        # Get Nifty OHLC for this date
        if scan_date not in nifty_ohlc:
            print(f"   ⚠️  {scan_date}: No Nifty data (market holiday?)")
            continue
        
        nifty = nifty_ohlc[scan_date]
        nifty_open = nifty["open"]
        nifty_close = nifty["close"]
        pct_return = ((nifty_close - nifty_open) / nifty_open) * 100
        
        # Derive actual regime
        if pct_return > 1:
            actual_regime = "BULL"
        elif pct_return < -1:
            actual_regime = "BEAR"
        else:
            actual_regime = "NEUTRAL"
        
        # Compute is_correct
        is_correct = (predicted_regime == actual_regime)
        
        # Log to console
        emoji_pred = "🐂" if predicted_regime == "BULL" else "🐻" if predicted_regime == "BEAR" else "⚖️"
        emoji_actual = "🐂" if actual_regime == "BULL" else "🐻" if actual_regime == "BEAR" else "⚖️"
        check = "✅" if is_correct else "❌"
        
        print(f"{scan_date}: {emoji_pred} {predicted_regime} (score {predicted_score}) → {emoji_actual} {actual_regime} ({pct_return:+.2f}%) {check}")
        
        if not is_correct:
            mismatches.append({
                "date": scan_date,
                "predicted": predicted_regime,
                "actual": actual_regime,
                "return": pct_return
            })
        
        # Build row for eval_daily
        eval_rows.append({
            "prediction_date": scan_date,
            "predicted_regime": predicted_regime,
            "predicted_score": int(predicted_score),
            "nifty_open": nifty_open,
            "nifty_close": nifty_close,
            "nifty_pct_return": pct_return,
            "actual_regime": actual_regime,
            "is_correct": is_correct,
        })
    
    if not eval_rows:
        print("❌ No valid data to backfill")
        return
    
    # ── Step 4: Insert into eval_daily ────────────────────────────────────────
    print(f"\n💾 Inserting {len(eval_rows)} rows into eval_daily...")
    
    try:
        # Delete existing data for these dates (to avoid duplicates)
        dates_to_delete = [row["prediction_date"] for row in eval_rows]
        
        for date_str in dates_to_delete:
            sb.table("eval_daily").delete().eq("prediction_date", date_str).execute()
        
        # Insert backfilled data
        sb.table("eval_daily").insert(eval_rows).execute()
        print(f"✅ Inserted {len(eval_rows)} rows")
        
    except Exception as e:
        print(f"❌ Insert failed: {type(e).__name__}: {e}")
        return
    
    # ── Step 5: Calculate and display accuracy ────────────────────────────────
    print(f"\n📊 BACKFILL RESULTS\n" + "=" * 50)
    
    correct = sum(1 for r in eval_rows if r["is_correct"])
    total = len(eval_rows)
    accuracy = (correct / total) * 100
    
    print(f"Total predictions: {total}")
    print(f"Correct: {correct}")
    print(f"Wrong: {total - correct}")
    print(f"Accuracy: {accuracy:.1f}%")
    
    # Accuracy by regime
    bull_rows = [r for r in eval_rows if r["predicted_regime"] == "BULL"]
    bear_rows = [r for r in eval_rows if r["predicted_regime"] == "BEAR"]
    neutral_rows = [r for r in eval_rows if r["predicted_regime"] == "NEUTRAL"]
    
    if bull_rows:
        bull_correct = sum(1 for r in bull_rows if r["is_correct"])
        bull_acc = (bull_correct / len(bull_rows)) * 100
        print(f"\nBULL predictions: {bull_correct}/{len(bull_rows)} = {bull_acc:.1f}%")
    
    if bear_rows:
        bear_correct = sum(1 for r in bear_rows if r["is_correct"])
        bear_acc = (bear_correct / len(bear_rows)) * 100
        print(f"BEAR predictions: {bear_correct}/{len(bear_rows)} = {bear_acc:.1f}%")
    
    if neutral_rows:
        neutral_correct = sum(1 for r in neutral_rows if r["is_correct"])
        neutral_acc = (neutral_correct / len(neutral_rows)) * 100
        print(f"NEUTRAL predictions: {neutral_correct}/{len(neutral_rows)} = {neutral_acc:.1f}%")
    
    # Show mismatches
    if mismatches:
        print(f"\n⚠️  MISMATCHES ({len(mismatches)}):")
        for m in mismatches:
            print(f"   {m['date']}: predicted {m['predicted']}, actual {m['actual']} ({m['return']:+.2f}%)")
    
    print("\n" + "=" * 50)
    print("✅ Backfill complete!")
    print("\nNext steps:")
    print("  1. Review accuracy baseline")
    print("  2. Check which signals are causing mismatches")
    print("  3. Adjust thresholds if needed")
    print("  4. Going forward, eval_daily will populate daily")


if __name__ == "__main__":
    # Run backfill for past 20 days
    # Adjust the parameter if you want fewer/more days
    backfill_eval_daily(days_back=20)
