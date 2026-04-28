import os
import requests
import pandas as pd
import subprocess
import sys
import json  # Added for the hand-off to Agent 2

# Check for required libraries
for lib in ["yfinance", "google-generativeai"]:
    try:
        __import__(lib.replace("-", "_"))
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

import yfinance as yf
import google.generativeai as genai  # Added AI layer

# 1. SETUP SECRETS
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") # Ensure this is in your env vars

# Configure Gemini
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

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
    current = series.iloc[-1]
    return (series < current).mean() * 100

def get_ai_summary(data_string):
    """Generates an intelligent summary using Gemini."""
    if not GEMINI_KEY:
        return "⚠️ Gemini API Key missing. Skipping AI summary."
    
    prompt = f"""
    Analyze this NSE Sector Relative Strength (RS) data:
    {data_string}
    
    You are a professional trader. In 3 short bullet points:
    1. Identify the 'Alpha' sector and why it's leading.
    2. Spot any 'hidden' rotation where 3M velocity is higher than 6M.
    3. Give a 1-sentence tactical 'Buy/Avoid' advice.
    Keep it punchy for Telegram.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "⚠️ AI Summary failed to generate."

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
                p6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)
                r3 = round(calc_percentile(rs.pct_change(63).tail(252)))
                r6 = round(calc_percentile(rs.pct_change(126).tail(252)))
                results.append({"name": name, "p3": p3, "p6": p6, "r3": r3, "r6": r6, "prc": round((r3+r6)/2)})
            except: continue

        # Process Railways
        try:
            rail_raw = yf.download(rail_tickers, period="3y", progress=False)['Adj Close']
            rail_idx = rail_raw.mean(axis=1)
            comb_r = pd.concat([rail_idx, bm_data], axis=1).dropna()
            comb_r.columns = ['s', 'b']
            rs_r = comb_r['s'] / comb_r['b']
            p3_r = round(((rs_r.iloc[-1] / rs_r.iloc[-63]) - 1) * 100, 1)
            p6_r = round(((rs_r.iloc[-1] / rs_r.iloc[-126]) - 1) * 100, 1)
            r3_r = round(calc_percentile(rs_r.pct_change(63).tail(252)))
            r6_r = round(calc_percentile(rs_r.pct_change(126).tail(252)))
            results.append({"name": "Railways*", "p3": p3_r, "p6": p6_r, "r3": r3_r, "r6": r6_r, "prc": round((r3_r+r6_r)/2)})
        except: pass

        df = pd.DataFrame(results).sort_values("prc", ascending=False)

        # --- DYNAMIC HAND-OFF (FOR AGENT 2) ---
        # We save any sector in the top quartile (PRC > 75) for the VCP Sniper to scan.
        active_sectors = df[df['prc'] >= 75]['name'].tolist()
        with open('active_sectors.json', 'w') as f:
            json.dump(active_sectors, f)
        # --------------------------------------

        # Build Table Message
        msg = "📊 **RANKING REPORT (R)**\n`SECTOR        3M_R  6M_R  PRC` \n`------------------------------` \n"
        for _, row in df.iterrows():
            msg += f"`{row['name'].ljust(12)} {str(row['r3']).ljust(5)} {str(row['r6']).ljust(5)} {str(row['prc']).ljust(3)}` \n"

        # Generate AI Summary
        raw_summary_data = df[['name', 'p3', 'p6', 'prc']].to_string()
        ai_summary_text = get_ai_summary(raw_summary_data)

        final_msg = msg + "\n💡 **AI INTELLIGENCE**\n" + ai_summary_text + "\n\n*R=Rank, %=Gain vs Nifty. Active Sectors saved for Sniper Agent.*"
        
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={"chat_id": CHAT_ID, "text": final_msg, "parse_mode": "Markdown"})
        
        print(f"Successfully sent report. Active sectors: {active_sectors}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_agent()
