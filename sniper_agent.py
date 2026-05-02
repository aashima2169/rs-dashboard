import os, requests, json, time
import pandas as pd
import yfinance as yf
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_stocks(sector_key):
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        official_name = config.get("nse_index_mapping", {}).get(sector_key)
        headers = {"User-Agent": "Mozilla/5.0"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        url = f"https://www.nseindia.com/api/equity-stockIndices?index={official_name.replace(' ', '%20')}"
        response = session.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return [f"{s['symbol']}.NS" for s in response.json()['data'] if s['symbol'] != official_name]
        return []
    except: return []

def send_telegram_file(file_path):
    """Sends the CSV directly to Telegram."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(file_path, "rb") as file:
            requests.post(url, data={"chat_id": CHAT_ID}, files={"document": file})
    except Exception as e:
        print(f"❌ File Send Error: {e}")

def run_sniper():
    print("\n🎯 --- SNIPER MISSION: FULL DATA SCAN ---")
    if not os.path.exists('active_sectors.json'): return
    with open('active_sectors.json', 'r') as f:
        active_sectors = json.load(f)

    all_data = [] 
    for sector in active_sectors:
        tickers = get_stocks(sector)
        for t in tickers:
            try:
                df = yf.download(t, period="1y", progress=False, auto_adjust=True)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                if df.empty or len(df) < 60: continue
                
                close = df['Close'].dropna()
                cmp = round(float(close.iloc[-1]), 2)
                ema10 = round(close.ewm(span=10).mean().iloc[-1], 2)
                ema20 = round(close.ewm(span=20).mean().iloc[-1], 2)
                ema50 = round(close.ewm(span=50).mean().iloc[-1], 2)
                
                dist_ema20 = round(((cmp - ema20) / ema20) * 100, 2)
                h10, l10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
                h30, l30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
                tightness = round(float((h10 - l10) / ((h30 - l30) if (h30-l30) != 0 else 1.0)), 2)

                # Criteria: Stacked EMAs + Tightness < 1.35
                if cmp > ema10 > ema20 > ema50 and dist_ema20 < 5.0 and tightness < 1.35:
                    all_data.append({
                        "Ticker": t, "Sector": sector, "CMP": cmp,
                        "EMA10": ema10, "EMA20": ema20, "EMA50": ema50,
                        "Dist_EMA20_%": dist_ema20, "Tightness": tightness
                    })
            except: continue
            time.sleep(0.1)

    if all_data:
        filename = "sniper_candidates.csv"
        pd.DataFrame(all_data).to_csv(filename, index=False)
        send_telegram_file(filename)
        
        msg = "🎯 **SNIPER ELITE REPORT**\n`TICKER   CMP      E10    E20    E50` \n"
        for c in all_data[:10]:
            msg += f"`{c['Ticker'].ljust(8)} {str(c['CMP']).ljust(8)} {str(c['EMA10']).ljust(6)} {str(c['EMA20']).ljust(6)} {str(c['EMA50']).ljust(6)}` \n"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    else:
        print("ℹ️ No matches today.")

if __name__ == "__main__":
    run_sniper()
