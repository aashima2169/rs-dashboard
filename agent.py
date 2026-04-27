import os
import requests
import pandas as pd
import yfinance as yf

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Focused Index List
sectors = {
    "Power/Energy": "^CNXENERGY", 
    "Infrastructure": "^CNXINFRA", 
    "PSE/Defense": "^CNXPSE", 
    "Realty": "^CNXREALTY", 
    "IT": "^CNXIT",
    "Banking": "^NSEBANK",
    "Metal": "^CNXMETAL",
    "Auto": "^CNXAUTO",
    "Pharma": "^CNXPHARMA",
    "FMCG": "^CNXFMCG"
}

def get_safe_close(df):
    return df['Adj Close'] if 'Adj Close' in df.columns else df['Close']

def run_agent():
    try:
        # Fetch Benchmark (Nifty 50)
        bm_raw = yf.download("^NSEI", period="2y", progress=False)
        bm_data = get_safe_close(bm_raw)
        
        report = "🛡️ **WEEKLY SECTOR RS SCAN**\n\n"
        report += "`SECTOR          1M   3M   6M   STATE` \n"
        report += "`------------------------------------` \n"

        results = []
        for name, ticker in sectors.items():
            try:
                s_raw = yf.download(ticker, period="2y", progress=False)
                if s_raw.empty: continue
                s_data = get_safe_close(s_raw)
                
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                rs = combined['s'] / combined['b']
                
                m1 = round(((rs.iloc[-1] / rs.iloc[-21]) - 1) * 100, 1)
                m3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                m6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)

                # State Logic
                if m1 > 0 and m6 > 0: state = "🚀 LEAD"
                elif m1 < 0 and m6 > 0: state = "⚠️ WEAK"
                elif m1 > 0 and m6 < 0: state = "📈 IMPROV"
                else: state = "😴 LAGG"

                results.append({"name": name, "m1": m1, "m3": m3, "m6": m6, "state": state})
            except: continue

        # Sort by 1-Month performance to see what's hot right now
        df = pd.DataFrame(results).sort_values("m1", ascending=False)

        for _, row in df.iterrows():
            name_p = row['name'].ljust(15)
            m1_p = str(row['m1']).ljust(4)
            m3_p = str(row['m3']).ljust(4)
            m6_p = str(row['m6']).ljust(4)
            report += f"`{name_p} {m1_p} {m3_p} {m6_p}` **{row['state']}**\n"

        report += "\n**Next Step:** Perform manual chart scan for `🚀 LEAD` and `📈 IMPROV` sectors."
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": report, "parse_mode": "Markdown"})
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_agent()
