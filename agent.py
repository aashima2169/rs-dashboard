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
    "Power": "^CNXENERGY", "PSE": "^CNXPSE", "CPSE": "^CNXCPSE",
    "BankNifty": "^NSEBANK", "NiftyIT": "^CNXIT", "Pharma": "^CNXPHARMA",
    "FMCG": "^CNXFMCG", "Metal": "^CNXMETAL", "Auto": "^CNXAUTO",
    "Realty": "^CNXREALTY", "Infra": "^CNXINFRA"
}
rail_tickers = ["IRFC.NS", "RVNL.NS", "IRCON.NS", "RITES.NS"]

def get_safe_close(df):
    return df['Adj Close'] if 'Adj Close' in df.columns else df['Close']

def calc_percentile(series):
    if series.empty: return 0
    current = series.iloc[-1]
    return (series < current).mean() * 100

def run_agent():
    try:
        bm_raw = yf.download("^NSEI", period="3y", progress=False)
        bm_data = get_safe_close(bm_raw)
        results = []

        # Process Official Sectors
        for name, ticker in sectors.items():
            try:
                s_raw = yf.download(ticker, period="3y", progress=False)
                s_data = get_safe_close(s_raw)
                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                rs = combined['s'] / combined['b']
                
                p3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                r3 = round(calc_percentile(rs.pct_change(63).tail(252)))
                r6 = round(calc_percentile(rs.pct_change(126).tail(252)))
                results.append({"name": name, "p3": p3, "r3": r3, "r6": r6, "prc": round((r3+r6)/2)})
            except:
                continue

        # Process Railways
        try:
            rail_raw = yf.download(rail_tickers, period="3y", progress=False)['Adj Close']
            rail_index = rail_raw.mean(axis=1)
            combined_r = pd.concat([rail_index, bm_data], axis=1).dropna()
            combined_r.columns = ['s', 'b']
            rs_r = combined_r['s'] / combined_r['b']
            
            p3_val = round(((rs_r.iloc[-1] / rs_r.iloc[-63]) - 1) * 100, 1)
            r3_val = round(calc_percentile(rs_r.pct_change(63).tail(252)))
            r6_val = round(calc_percentile(rs_r.pct_change(126).tail(252)))
            results.append({"name": "Railways*", "p3": p3_val, "r3": r3_val, "r6": r6_val, "prc": round((r3_val + r6_val) / 2)})
        except:
            pass

        df = pd.DataFrame(results).sort_values("prc", ascending=False)

        # Build Message
        msg = "📊 **RANKING & VELOCITY**\n`SECTOR        PRC  3M_%` \n`------------------------` \n"
        for _, row in df.iterrows():
            msg += f"`{row['name'].ljust(12)} {str(row['prc']).ljust(4)} {str(row['p3']).ljust(5)}` \n"

        # Strategy Summary
        summary = "\n💡 **STRATEGY SUMMARY**\n"
        top = df.iloc[0]
        summary += f"✅ **TOP LEAD:** {top['name']} (PRC {top['prc']})\n"
        
        # Improvement Logic
        improving = df[df['r3'] > (df['r6'] + 15)].head(1)
        if not improving.empty:
            summary += f"🔄 **REVERSAL:** {improving.iloc[0]['name']} waking up.\n"
        
        # Avoid Logic (Fixed the syntax error here)
        laggard = df.sort_values("prc").iloc[0]
        summary += f"🚫 **AVOID:** {laggard['name']} is dead money.\n"

        final_msg = msg + summary
        
        # Send to Telegram
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": final_msg, "parse_mode": "Markdown"})
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_agent()
