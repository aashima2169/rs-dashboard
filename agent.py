import os
import requests
import pandas as pd
import subprocess
import sys

try:
    import yfinance as yf
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

sectors = {
    "Bank Nifty": "^NSEBANK", "IT": "^CNXIT", "Pharma": "^CNXPHARMA",
    "FMCG": "^CNXFMCG", "Metal": "^CNXMETAL", "Auto": "^CNXAUTO",
    "Realty": "^CNXREALTY", "Energy": "^CNXENERGY", "Infra": "^CNXINFRA",
    "PSE (Govt)": "^CNXPSE", "Commodities": "^CNXCMDT", "Fin Service": "^CNXFIN"
}

def get_safe_close(df):
    if 'Adj Close' in df.columns: return df['Adj Close']
    return df['Close']

def run_agent():
    try:
        # Fetch Benchmark (Nifty 50)
        bm_raw = yf.download("^NSEI", period="1y", progress=False)
        bm_data = get_safe_close(bm_raw)
            
        results = []

        for name, ticker in sectors.items():
            try:
                s_raw = yf.download(ticker, period="1y", progress=False)
                if s_raw.empty: continue
                s_data = get_safe_close(s_raw)
                
                # Align data
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                
                # RS Ratio Calculation
                rs = combined['s'] / combined['b']
                
                # 20-Day Moving Average of RS (Institutional Trend)
                rs_ma20 = rs.rolling(window=20).mean()
                
                # Momentum Calculations
                m1 = round(((rs.iloc[-1] / rs.iloc[-21]) - 1) * 100, 1) # 1 Month
                m3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1) # 3 Month
                
                # QUADRANT LOGIC
                if m1 > 0 and m3 > 0:
                    quadrant = "🚀 LEAD" # Leading
                elif m1 < 0 and m3 > 0:
                    quadrant = "⚠️ WEAK" # Weakening
                elif m1 > 0 and m3 < 0:
                    quadrant = "📈 IMPROV" # Improving
                else:
                    quadrant = "😴 LAGG" # Lagging

                # TREND CHECK (Is it above its 20-day trend line?)
                trend = "🔥" if rs.iloc[-1] > rs_ma20.iloc[-1] else "❄️"
                
                results.append({
                    "name": name, "m1": m1, "m3": m3, 
                    "quad": quadrant, "trend": trend
                })
            except: continue

        # Sort by 1-Month Strength
        df = pd.DataFrame(results).sort_values("m1", ascending=False)

        # PREPARE TELEGRAM MESSAGE
        message = "🛡️ **INSTITUTIONAL RS STRATEGY**\n\n"
        message += "`SECTOR          1M%    3M%    STATE` \n"
        message += "`------------------------------------` \n"
        
        for _, row in df.iterrows():
            name_p = row['name'].ljust(15)
            m1_p = str(row['m1']).ljust(6)
            m3_p = str(row['m3']).ljust(6)
            # Quadrant + Trend Icon
            message += f"`{name_p} {m1_p} {m3_p}` **{row['quad']}** {row['trend']}\n"

        message += "\n**Legend:**\n🚀=Buy Leader | 📈=Watch for Entry\n⚠️=Book Profits | 😴=Avoid\n🔥=Trend Up | ❄️=Trend Down"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_agent()
