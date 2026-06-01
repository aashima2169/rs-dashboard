"""
For agent.py - save_nifty_ohlc() function with fixed yfinance handling

Replace the old save_nifty_ohlc() function with this one:
"""

def save_nifty_ohlc(sb, scan_date: str):
    """
    Fetch today's Nifty OHLC and save to Supabase.
    Called at end of agent.py before returning.
    
    Args:
        sb: Supabase client
        scan_date: str in YYYY-MM-DD format (today)
    """
    try:
        # Fetch today's Nifty OHLC
        nifty = yf.download("^NSEI", start=scan_date, end=scan_date, progress=False, auto_adjust=True)
        
        if nifty.empty:
            print(f"⚠️  No Nifty data for {scan_date} (market holiday?)")
            return
        
        # Handle multi-level columns
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
        
        data = nifty.iloc[0]
        
        # Extract OHLC
        nifty_open = float(data["Open"])
        nifty_close = float(data["Close"])
        pct_return = ((nifty_close - nifty_open) / nifty_open) * 100
        
        # Derive actual regime
        if pct_return > 1:
            actual_regime = "BULL"
        elif pct_return < -1:
            actual_regime = "BEAR"
        else:
            actual_regime = "NEUTRAL"
        
        # Log to eval_daily
        # macro_agent will UPDATE this row with prediction
        row = {
            "prediction_date": scan_date,
            "nifty_open": nifty_open,
            "nifty_close": nifty_close,
            "nifty_pct_return": pct_return,
            "actual_regime": actual_regime,
            "created_at": None,  # Supabase auto-timestamp
        }
        
        sb.table("eval_daily").insert(row).execute()
        
        emoji = "🐂" if actual_regime == "BULL" else "🐻" if actual_regime == "BEAR" else "⚖️"
        print(f"✅ eval_daily: Nifty logged ({emoji} {actual_regime}, {pct_return:+.2f}%)")
        
    except Exception as e:
        print(f"⚠️  eval_daily insert failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
