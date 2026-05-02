import os, requests, json, time
import pandas as pd
import yfinance as yf

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_stocks(sector_key):
    """Fetches stock list with detailed connection logging."""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.nseindia.com/market-data/live-equity-market"
        }
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        print(f"   📡 Calling NSE API for: {official_name}")
        response = session.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            stocks = [f"{s['symbol']}.NS" for s in data['data'] if s['symbol'] != official_name]
            print(f"   ✅ Received {len(stocks)} symbols from NSE.")
            return list(set(stocks))
        else:
            print(f"   ❌ NSE API Error: Status {response.status_code}")
            return []
    except Exception as e:
        print(f"   ❌ Connection Error: {e}")
        return []

def professional_screen(ticker):
    """Logs the reason for stock rejection."""
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 50:
            return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close'].dropna()
        curr_price = float(close.iloc[-1])
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        
        # Log 1: Trend Check
        if not (curr_price > ema20 > ema50):
            # We don't print every fail to keep logs clean, but we track them
            return None

        # Log 2: Tightness Check
        range_now = df['High'].tail(10).max() - df['Low'].tail(10).min()
        range_before = df['High'].iloc[-30:-10].max() - df['Low'].iloc[-30:-10].min()
        tightness = range_now / range_before

        if tightness < 1.15: # Successfully identified a squeeze
            print(f"      🔥 HIT: {ticker} (Tightness: {round(tightness, 2)})")
            return {"ticker": ticker, "price": round(curr_price, 2), "tight": round(float(tightness), 2)}
        
        return None
    except:
        return None

def run_sniper():
    print("\n🔫 --- SNIPER AGENT START ---")
    
    # 1. Check for the Handoff File
    if not os.path.exists('active_sectors.json'):
        print("❌ FATAL: 'active_sectors.json' not found. Scout did not hand over any data.")
        return
        
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)
    
    print(f"📦 RECEIVED FROM SCOUT: {active_sectors}")
    
    if not active_sectors:
        print("ℹ️ Handoff was empty. Nothing to scan.")
        return

    all_candidates = []
    
    # 2. Start Processing
    for sector in active_sectors:
        print(f"\n📂 Processing Sector: {sector}")
        tickers = get_stocks(sector)
        
        if not tickers:
            print(f"   ⚠️ Skipping {sector}: No stocks found.")
            continue
            
        print(f"   🔍 Screening {len(tickers)} stocks for VCP setups...")
        hits_in_sector = 0
