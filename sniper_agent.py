def run_sniper():
    print("\n🚩 --- HTF STEP 1: DYNAMIC POLE DETECTION ---")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    for sector in active_sectors:
        tickers = get_stocks(sector)
        for t in tickers:
            try:
                # Need at least 250 days for 200 SMA validation
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if df.empty or len(df) < 200: continue
                
                close = df['Close']
                cmp = float(close.iloc[-1])

                # --- THE POLE: Dynamic Lookback ---
                # Check 10, 20, 30, and 40-day windows for a 20%+ move
                moves = [
                    ((cmp - close.iloc[-10]) / close.iloc[-10]) * 100,
                    ((cmp - close.iloc[-20]) / close.iloc[-20]) * 100,
                    ((cmp - close.iloc[-30]) / close.iloc[-30]) * 100,
                    ((cmp - close.iloc[-40]) / close.iloc[-40]) * 100
                ]
                best_pole = max(moves)

                # --- TREND TEMPLATE (Stage 2) ---
                ema10 = close.ewm(span=10).mean().iloc[-1]
                ema21 = close.ewm(span=21).mean().iloc[-1]
                ema50 = close.ewm(span=50).mean().iloc[-1]
                sma200 = close.rolling(window=200).mean().iloc[-1]

                # Filter: Pole > 20% AND trending above 200 SMA
                if best_pole >= 20.0 and cmp > sma200 and ema10 > ema21:
                    all_data.append({
                        "Ticker": t, 
                        "CMP": round(cmp, 2),
                        "Max_Pole_%": round(best_pole, 2)
                    })
            except: continue
            time.sleep(0.05)
