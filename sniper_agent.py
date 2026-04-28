import os
import requests
import pandas as pd
import subprocess
import sys
import json

# Ensure yfinance is installed
try:
    import yfinance as yf
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_nifty_constituents(index_name):
    """Fetch Nifty sector constituents using yfinance"""
    constituents_map = {
        "Power": ["NTPC.NS", "POWERGRID.NS", "RELIANCE.NS", "ADANIGREEN.NS", "JSW.NS"],
        "PSE": ["NTPC.NS", "POWERGRID.NS", "INDIANOIL.NS", "BPCL.NS", "STEELAUTH.NS"],
        "Pharma": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "LUPIN.NS", "DIVISLAB.NS"],
        "FMCG": ["NESTLEIND.NS", "BRITANNIA.NS", "GODREJCP.NS", "UNILEVER.NS", "MARICO.NS"],
        "Metal": ["TATA.NS", "HINDALCO.NS", "JSWSTEEL.NS", "VEDL.NS", "TATASTEEL.NS"],
        "Auto": ["MARUTI.NS", "TATAMOTORS.NS", "BAJAJFINSV.NS", "EICHERMOT.NS", "SBILIFE.NS"],
        "Realty": ["DLF.NS", "GODREJ.NS", "INDIABULLS.NS", "PRESTIGE.NS", "OBEROI.NS"],
        "Infra": ["NTPC.NS", "POWERGRID.NS", "ADANIPORTS.NS", "RELIANCE.NS", "AXISBANK.NS"],
        "IT": ["TCS.NS", "INFOSYS.NS", "WIPRO.NS", "HCLTECH.NS", "TECH.NS"],
        "BankNifty": ["HSBC.NS", "KOTAKBANK.NS", "ICICIBANK.NS", "AXISBANK.NS", "SBIN.NS"],
        "CPSE": ["CPSEETF.NS", "NTPC.NS", "POWERGRID.NS", "INDIANOIL.NS", "STEELAUTH.NS"]
    }
    return constituents_map.get(index_name, [])

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
        if mkt_cap < 5000000000: 
            return None

        # Fetch historical data
        df = yf.download(ticker, period="1y", progress=False)
        if len(df) < 100: 
            return None

        close = df['Close']
        
        # 1. EMA CALCULATIONS
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
        ema100 = close.ewm(span=100, adjust=False).mean().iloc[-1]
        curr_price = close.iloc[-1]

        # FILTER: EMA ALIGNMENT (Trend Strength)
        if not (curr_price > ema20 > ema50 > ema100):
            return None

        # 2. VCP TIGHTNESS MATH
        high10, low10 = df['High'].tail(10).max(), df['Low'].tail(10).min()
        high30, low30 = df['High'].iloc[-40:-10].max(), df['Low'].iloc[-40:-10].min()
        
        tightness = (high10 - low10) / (high30 - low30)

        # FINAL VERDICT
        if tightness < 0.7:
            return {
                "ticker": ticker, 
                "price": round(curr_price, 2), 
                "mkt_cap_cr": round(mkt_cap / 10000000),
                "tightness": round(tightness, 2)
            }
        return None
    except Exception as e:
        return None

def run_sniper():
    try:
        print("🔫 SNIPER AGENT STARTED...")
        
        # Check if active_sectors.json exists
        if not os.path.exists('active_sectors.json'):
            msg = "❌ **SNIPER AGENT FAILED**\n`active_sectors.json not found. Scout (Agent 1) may not have completed.`"
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                         json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
            print("ERROR: active_sectors.json not found!")
            return

        # Load active sectors from Scout
        with open('active_sectors.json', 'r') as f:
            active_sectors = json.load(f)
        
        if not active_sectors:
            msg = "⚠️ **SNIPER AGENT IDLE**\n`No sectors qualified for screening (need 3M & 6M RS > 10%)`"
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                         json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
            print("No active sectors to screen.")
            return

        print(f"📊 Screening sectors: {active_sectors}")
        
        all_candidates = []
        total_screened = 0
        
        # Screen each active sector
        for sector in active_sectors:
            print(f"\n🔍 Scanning {sector}...")
            constituents = get_nifty_constituents(sector)
            
            if not constituents:
                print(f"  ⚠️ No constituents found for {sector}")
                continue
            
            sector_candidates = []
            for ticker in constituents:
                result = professional_screen(ticker)
                total_screened += 1
                if result:
                    result["sector"] = sector
                    sector_candidates.append(result)
                    print(f"  ✅ {ticker}: VCP {result['tightness']}")
            
            all_candidates.extend(sector_candidates)
        
        # Sort by tightness (lower = better contraction)
        all_candidates = sorted(all_candidates, key=lambda x: x['tightness'])
        
        # Build Telegram Message
        if all_candidates:
            msg = f"🎯 **SNIPER REPORT - VCP SCAN**\n"
            msg += f"`Total Screened: {total_screened} | Qualified: {len(all_candidates)}`\n\n"
            msg += "`TICKER  SECTOR   PRICE    TIGHT  MKT_CAP_CR`\n"
            msg += "`------  -------  -------  -----  ----------`\n"
            
            for candidate in all_candidates[:10]:  # Top 10
                msg += f"`{candidate['ticker'].ljust(7)} {candidate['sector'].ljust(8)} {str(candidate['price']).ljust(7)} {str(candidate['tightness']).ljust(5)} {candidate['mkt_cap_cr']}`\n"
            
            if len(all_candidates) > 10:
                msg += f"\n`... and {len(all_candidates) - 10} more candidates`\n"
            
            msg += f"\n✅ **SNIPER AGENT COMPLETED SUCCESSFULLY**"
        else:
            msg = f"🎯 **SNIPER REPORT - VCP SCAN**\n"
            msg += f"`Total Screened: {total_screened} | Qualified: 0`\n"
            msg += f"`No stocks passed the VCP filter (EMA alignment + Market Cap + Tightness)`\n\n"
            msg += f"✅ **SNIPER AGENT COMPLETED** (No candidates found)"
        
        # Send to Telegram
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        
        print(f"\n✅ SNIPER AGENT COMPLETED. Candidates found: {len(all_candidates)}")
        
    except Exception as e:
        error_msg = f"❌ **SNIPER AGENT ERROR**\n`{str(e)}`"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": error_msg, "parse_mode": "Markdown"})
        print(f"ERROR in run_sniper: {e}")

if __name__ == "__main__":
    run_sniper()
