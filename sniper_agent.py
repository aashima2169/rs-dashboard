def professional_screen(ticker):
    """
    Advanced Filter: 
    1. EMA Alignment (20 > 50 > 100)
    2. Market Cap > 500 Cr (Avoid Penny Stocks)
    3. VCP Tightness Check
    """
    try:
        # Fetch fundamental data for Market Cap
        t_obj = yf.Ticker(ticker)
        mkt_cap = t_obj.info.get('marketCap', 0)
        
        # Filter: Only Mid/Large Cap (Minimum 500 Crore INR)
        # Note: yfinance returns Market Cap in absolute numbers
        if mkt_cap < 5000000000: 
            return None

        # Fetch historical data
        df = yf.download(ticker, period="1y", progress=False)
        if len(df) < 100: return None

        close = df['Close']
        
        # 1. EMA CALCULATIONS
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
        ema100 = close.ewm(span=100, adjust=False).mean().iloc[-1]
        curr_price = close.iloc[-1]

        # FILTER: EMA ALIGNMENT (Trend Strength)
        # Price must be above all, and MAs must be in order
        if not (curr_price > ema20 > ema50 > ema100):
            return None

        # 2. VCP TIGHTNESS MATH
        # Look for the 'Coil': 10-day range vs 30-day range
        high10, low10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
        high30, low30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
        
        tightness = (high10 - low10) / (high30 - low30)

        # FINAL VERDICT
        if tightness < 0.7:  # 30% reduction in volatility (Contraction)
            return {
                "ticker": ticker, 
                "price": round(curr_price, 2), 
                "mkt_cap_cr": round(mkt_cap / 10000000),
                "tightness": round(tightness, 2)
            }
        return None
    except Exception as e:
        return None
