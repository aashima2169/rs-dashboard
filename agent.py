import os, requests, json
import pandas as pd
import yfinance as yf

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_safe_close(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df['Close'].dropna()

def calc_percentile(series):
    if series.empty: return 0
    current = series.iloc[-1]
    return (series < current).mean() * 100

def run_agent():
    print("📊 --- SCOUT AGENT SESSION START ---")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        sector_tickers = config.get("sectors", {})
        bm_data = get_safe_close(yf.download("^NSEI", period="1y", progress=False))
        
        results = []
        for name, ticker in sector_tickers.items():
            print(f"🔍 [SCANNING] {name}")
            try:
                s_data = get_safe_close(yf.download(ticker, period="1y", progress=False))
                if s_data.empty or len(s_data) < 126: continue

                combined = pd.concat([s_data, bm_data], axis=1).dropna()
                combined.columns = ['s', 'b']
                rs = combined['s'] / combined['b']
                
                # Performance Math (%)
                p3 = round(((rs.iloc[-1] / rs.iloc[-63]) - 1) * 100, 1)
                p6 = round(((rs.iloc[-1] / rs.iloc[-126]) - 1) * 100, 1)
                
                # Rank Math (Percentile)
                r3 = round(calc_percentile(rs.pct_change(63).tail(252)))
                r6 = round(calc_percentile(rs.pct_change(126).tail(252)))
                
                results.append({
                    "name": name, 
                    "p3": p3, "p6": p6, 
                    "r3": r3, "r6": r6, 
                    "prc": round((r3+r6)/2)
                })
            except Exception as e:
                print(f"   ⚠️ Error: {e}")

        df = pd.DataFrame(results).sort_values("prc", ascending=False)
        # Sniper Filter: Positive velocity only
        active_sectors = df[(df['p3'] > 0) & (df['p6'] > 0)]['name'].tolist()

        with open('active_sectors.json', 'w') as f:
            json.dump(active_sectors, f)

        # --- TELEGRAM MESSAGE ---
        msg = "📊 **SCOUT REPORT - SECTOR RANKINGS**\n\n"
        msg += "`SECTOR         3M_R  6M_R  PRC` \n"
        msg += "`------------------------------` \n"
        for _, r in df.iterrows():
            msg += f"`{r['name'].ljust(14)} {str(r['r3']).ljust(5)} {str(r['r6']).ljust(5)} {str(r['prc']).ljust(3)}` \n"

        msg += "\n🚀 **VELOCITY REPORT (%)**\n"
        msg += "`SECTOR         3M_%    6M_%` \n"
        msg += "`---------------------------` \n"
        for _, r in df.iterrows():
            msg += f"`{r['name'].ljust(14)} {str(r['p3']).ljust(7)} {str(r['p6']).ljust(7)}` \n"

        if not df.empty:
            top = df.iloc[0]
            msg += f"\n💡 **TOP LEAD:** {top['name']} (PRC {top['prc']})"
        
        msg += f"\n🎯 **SNIPER TARGETS:** {', '.join(active_sectors)}"

        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                     json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
        
        print(f"✅ SCOUT COMPLETED. Active: {active_sectors}")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")

if __name__ == "__main__":
    run_agent()
