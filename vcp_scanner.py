"""
vcp_scanner.py — NSE VCP Scanner with Supabase output
Based on Mark Minervini's Volatility Contraction Pattern method.

Changes from original:
  - Writes results to Supabase stock_candidates table
  - Keeps all existing logic intact
  - Adds composite score 0-100
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import json
import os
warnings.filterwarnings('ignore')

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# ── Sector mapping ────────────────────────────────────────────────────────────
SECTOR_MAP = {
    'TCS': 'IT', 'INFY': 'IT', 'WIPRO': 'IT', 'HCLTECH': 'IT', 'TECHM': 'IT',
    'LTIM': 'IT', 'MPHASIS': 'IT', 'COFORGE': 'IT', 'PERSISTENT': 'IT',
    'HDFCBANK': 'BANK', 'ICICIBANK': 'BANK', 'SBIN': 'BANK', 'KOTAKBANK': 'BANK',
    'AXISBANK': 'BANK', 'INDUSINDBK': 'BANK', 'BANDHANBNK': 'BANK', 'FEDERALBNK': 'BANK',
    'SUNPHARMA': 'PHARMA', 'DRREDDY': 'PHARMA', 'CIPLA': 'PHARMA', 'DIVISLAB': 'PHARMA',
    'AUROPHARMA': 'PHARMA', 'LUPIN': 'PHARMA', 'ALKEM': 'PHARMA',
    'MARUTI': 'AUTO', 'TATAMOTORS': 'AUTO', 'M&M': 'AUTO', 'BAJAJ-AUTO': 'AUTO',
    'EICHERMOT': 'AUTO', 'HEROMOTOCO': 'AUTO', 'TVSMOTOR': 'AUTO',
    'HINDUNILVR': 'FMCG', 'ITC': 'FMCG', 'NESTLEIND': 'FMCG', 'BRITANNIA': 'FMCG',
    'MARICO': 'FMCG', 'TATACONSUM': 'FMCG', 'DABUR': 'FMCG',
    'HONASA': 'NEW_AGE', 'ZOMATO': 'NEW_AGE', 'NYKAA': 'NEW_AGE',
    'TATASTEEL': 'METALS', 'JSWSTEEL': 'METALS', 'HINDALCO': 'METALS',
    'VEDL': 'METALS', 'SAIL': 'METALS', 'NMDC': 'METALS',
    'RELIANCE': 'ENERGY', 'ONGC': 'ENERGY', 'POWERGRID': 'ENERGY',
    'NTPC': 'ENERGY', 'ADANIGREEN': 'ENERGY', 'TATAPOWER': 'ENERGY',
    'ULTRACEMCO': 'CEMENT', 'SHREECEM': 'CEMENT', 'GRASIM': 'CEMENT',
    'BAJFINANCE': 'FINANCE', 'BAJAJFINSV': 'FINANCE', 'CHOLAFIN': 'FINANCE',
}

SECTOR_INDICES = {
    'IT':     '^CNXIT',
    'BANK':   '^NSEBANK',
    'METALS': 'NIFTY_METAL.NS',
    'ENERGY': 'NIFTY_ENERGY.NS',
}

NIFTY_STOCKS = [
    'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS',
    'HINDUNILVR.NS', 'SBIN.NS', 'BHARTIARTL.NS', 'KOTAKBANK.NS', 'LT.NS',
    'AXISBANK.NS', 'ASIANPAINT.NS', 'MARUTI.NS', 'SUNPHARMA.NS', 'TITAN.NS',
    'ULTRACEMCO.NS', 'NESTLEIND.NS', 'WIPRO.NS', 'POWERGRID.NS', 'NTPC.NS',
    'ONGC.NS', 'TATAMOTORS.NS', 'M&M.NS', 'BAJFINANCE.NS', 'HCLTECH.NS',
    'HONASA.NS', 'ZOMATO.NS', 'NYKAA.NS', 'DELHIVERY.NS',
    'TATASTEEL.NS', 'JSWSTEEL.NS', 'ADANIPORTS.NS',
    'BAJAJFINSV.NS', 'BRITANNIA.NS', 'CIPLA.NS', 'DRREDDY.NS',
    'EICHERMOT.NS', 'GRASIM.NS', 'DIVISLAB.NS', 'HEROMOTOCO.NS',
    'HINDALCO.NS', 'INDUSINDBK.NS', 'ITC.NS', 'SHREECEM.NS',
    'TATACONSUM.NS', 'TECHM.NS', 'VEDL.NS', 'COFORGE.NS',
    'PERSISTENT.NS', 'LTIM.NS', 'MPHASIS.NS', 'TVSMOTOR.NS',
    'CHOLAFIN.NS', 'MUTHOOTFIN.NS', 'FEDERALBNK.NS',
]

_sector_cache = {}

def get_sector_momentum(sector):
    if sector in _sector_cache:
        return _sector_cache[sector]
    index_symbol = SECTOR_INDICES.get(sector)
    if not index_symbol:
        return 'Unknown'
    try:
        df    = yf.download(index_symbol, period='3mo', interval='1d', progress=False)
        if df is None or len(df) < 20:
            return 'Unknown'
        close = df[('Close', index_symbol)] if isinstance(df.columns[0], tuple) else df['Close']
        close = close.dropna()
        if len(close) < 20:
            return 'Unknown'
        ma20  = close.rolling(20).mean().iloc[-1]
        ma50  = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else ma20
        curr  = close.iloc[-1]
        ret1m = (curr - close.iloc[-20]) / close.iloc[-20] * 100
        if curr > ma20 > ma50 and ret1m > 3:
            momentum = 'Strong'
        elif curr < ma20 and ret1m < -3:
            momentum = 'Weak'
        else:
            momentum = 'Neutral'
        _sector_cache[sector] = momentum
        return momentum
    except:
        return 'Unknown'


# ── Supabase writer ───────────────────────────────────────────────────────────

def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️  Supabase not configured — results saved to CSV only")
        return None
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase connected")
        return client
    except Exception as e:
        print(f"❌ Supabase failed: {e}")
        return None


def write_to_supabase(sb, results, scan_date):
    if not sb or not results:
        return
    try:
        # Clear today's existing VCP rows
        sb.table("stock_candidates") \
          .delete() \
          .eq("scan_date", scan_date) \
          .eq("pattern", "VCP") \
          .execute()

        rows = []
        for r in results:
            bo = r.get('breakout_info', {})
            vi = r.get('volume_info', {})
            rows.append({
                "scan_date"        : scan_date,
                "symbol"           : r['symbol'],
                "sector"           : r.get('sector', 'OTHER'),
                "pattern"          : "VCP",
                "current_price"    : r.get('current_price'),
                "pivot"            : r.get('pivot'),
                "pct_from_pivot"   : r.get('pct_from_pivot'),
                "stop_loss"        : r.get('stop_loss'),
                "risk_per_share"   : r.get('risk_per_share'),
                "target_1"         : r.get('target_1'),
                "target_2"         : r.get('target_2'),
                "target_3"         : r.get('target_3'),
                "risk_reward"      : r.get('risk_reward'),
                "vcp_stage"        : r.get('vcp_stage'),
                "num_contractions" : r.get('num_contractions'),
                "volume_drying"    : vi.get('drying', False),
                "vol_pct_of_avg"   : vi.get('pct_of_avg'),
                "sector_momentum"  : r.get('sector_momentum'),
                "base_start_date"  : r.get('base_start_date'),
                "first_seen"       : r.get('first_seen_scanner'),
                "broke_out"        : bo.get('broke_out', False),
                "breakout_date"    : bo['date'].strftime('%Y-%m-%d') if bo.get('date') else None,
                "days_to_t1"       : r.get('days_to_t1'),
                "score"            : r.get('score', 0),
            })

        sb.table("stock_candidates").insert(rows).execute()
        print(f"✅ {len(rows)} VCP candidates written to Supabase")
    except Exception as e:
        print(f"❌ Supabase write failed: {e}")


# ── Scoring ───────────────────────────────────────────────────────────────────

def calculate_score(r):
    score = 0
    # More contractions = better (max 30)
    score += min(30, r.get('num_contractions', 0) * 10)
    # Volume drying (20)
    if r.get('volume_info', {}).get('drying'):
        score += 20
    # Risk reward (max 25)
    rr = r.get('risk_reward', 0)
    if rr >= 3:   score += 25
    elif rr >= 2: score += 15
    elif rr >= 1: score += 8
    # Close to pivot (max 25)
    pct = abs(r.get('pct_from_pivot', 10))
    if pct <= 2:  score += 25
    elif pct <= 5: score += 15
    elif pct <= 10: score += 8
    return min(100, score)


# ── VCP Scanner class (unchanged logic, added score + Supabase) ───────────────

class VCPScanner:

    def __init__(self, symbols, period='1y'):
        self.symbols  = symbols
        self.period   = period
        self.results  = []
        self.log_file = 'vcp_history.json'
        self.history  = self._load_history()

    def download_data(self, symbol):
        try:
            df = yf.download(symbol, period=self.period, interval='1d', progress=False)
            if df is None or len(df) < 100:
                return None
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            return df.dropna()
        except:
            return None

    def find_swings(self, series_high, series_low, window=5):
        highs, lows = [], []
        for i in range(window, len(series_high) - window):
            if series_high.iloc[i] == series_high.iloc[i-window:i+window+1].max():
                highs.append((i, series_high.iloc[i], series_high.index[i]))
            if series_low.iloc[i] == series_low.iloc[i-window:i+window+1].min():
                lows.append((i, series_low.iloc[i], series_low.index[i]))
        return highs, lows

    def detect_contractions(self, df, base_start_idx):
        base_df = df.iloc[base_start_idx:]
        if len(base_df) < 15:
            return []
        highs, lows = self.find_swings(base_df['High'], base_df['Low'], window=4)
        contractions = []
        for i in range(len(highs) - 1):
            h1_i, h1_p, h1_d = highs[i]
            h2_i, h2_p, h2_d = highs[i + 1]
            between_lows = [(li, lp, ld) for li, lp, ld in lows if h1_i < li < h2_i]
            if not between_lows:
                continue
            trough = min(between_lows, key=lambda x: x[1])
            contractions.append({
                'number':          len(contractions) + 1,
                'high_price':      round(h1_p, 2),
                'low_price':       round(trough[1], 2),
                'contraction_pct': round((h1_p - trough[1]) / h1_p * 100, 2),
                'duration_days':   h2_i - h1_i,
                'avg_volume':      int(base_df['Volume'].iloc[h1_i:h2_i].mean()),
                'start_date':      h1_d,
            })
        return contractions

    def is_valid_vcp(self, contractions):
        if len(contractions) < 2:
            return False
        for i in range(1, len(contractions)):
            if contractions[i]['contraction_pct'] >= contractions[i-1]['contraction_pct'] + 1:
                return False
        return True

    def get_vcp_stage(self, contractions, current_price, pivot):
        n = len(contractions)
        pct_from_pivot = (pivot - current_price) / pivot * 100
        if n == 0:    label = 'No Pattern'
        elif n == 1:  label = 'Early VCP (T1) — Base forming'
        elif n == 2:  label = 'Mid VCP (T2) — Tightening'
        else:
            last_c = contractions[-1]['contraction_pct']
            label  = f'Late VCP (T{n}) — Tight Coil' if last_c < 5 else f'Late VCP (T{n}) — Near pivot'
        if pct_from_pivot <= 3:   label += ' — VERY CLOSE TO PIVOT'
        elif pct_from_pivot <= 7: label += ' — Approaching pivot'
        return label

    def find_base_start(self, df):
        lookback = min(len(df), 200)
        peak_idx = df.tail(lookback)['High'].idxmax()
        pos      = df.index.get_loc(peak_idx)
        return max(0, pos)

    def check_prior_uptrend(self, df):
        if len(df) < 150:
            return False
        close  = df['Close']
        ma50   = close.rolling(50).mean().iloc[-1]
        ma150  = close.rolling(150).mean().iloc[-1]
        curr   = close.iloc[-1]
        low52w = df['Low'].tail(252).min()
        return (curr > ma50 and ma50 > ma150 and curr >= low52w * 1.20)

    def get_pivot(self, df, base_start_idx):
        return round(float(df['High'].iloc[base_start_idx:].max()), 2)

    def get_stop_loss(self, df, contractions):
        if contractions:
            return round(float(contractions[-1]['low_price']), 2)
        return round(float(df['Low'].tail(30).min()), 2)

    def calculate_targets(self, pivot):
        return {
            'T1': round(pivot * 1.15, 2),
            'T2': round(pivot * 1.25, 2),
            'T3': round(pivot * 1.40, 2),
        }

    def check_breakout(self, df, pivot):
        avg_vol = float(df['Volume'].rolling(50).mean().iloc[-1])
        window  = df.tail(30)
        for i in range(len(window)):
            row    = window.iloc[i]
            close  = float(row['Close'])
            volume = float(row['Volume'])
            if close > pivot and volume > avg_vol * 1.5:
                breakout_date = window.index[i]
                after         = window.iloc[i:]
                held          = all(float(r['Close']) > pivot * 0.97 for _, r in after.iterrows())
                gain_pct      = round((float(df['Close'].iloc[-1]) - close) / close * 100, 2)
                return {
                    'broke_out': True,
                    'date':      breakout_date,
                    'held':      held,
                    'gain_since': gain_pct,
                    'status':    '✅ Held above pivot' if held else '⚠️ Gave back gains',
                }
        return {'broke_out': False}

    def days_to_target(self, df, pivot, target_price):
        avg_vol = df['Volume'].rolling(50).mean()
        for i in range(50, len(df) - 1):
            close = float(df['Close'].iloc[i])
            vol   = float(df['Volume'].iloc[i])
            avg_v = float(avg_vol.iloc[i])
            if close > pivot and vol > avg_v * 1.5:
                after      = df.iloc[i:]
                target_hit = after[after['High'] >= target_price]
                if not target_hit.empty:
                    return (target_hit.index[0] - df.index[i]).days
                return None
        return None

    def volume_analysis(self, df):
        recent_vol = float(df['Volume'].tail(20).mean())
        base_vol   = float(df['Volume'].tail(60).head(40).mean())
        return {
            'drying':     recent_vol < base_vol * 0.75,
            'recent_avg': int(recent_vol),
            'base_avg':   int(base_vol),
            'pct_of_avg': round(recent_vol / base_vol * 100, 1),
        }

    def exit_signals(self, df, pivot, stop_loss):
        signals = []
        curr    = float(df['Close'].iloc[-1])
        prev    = float(df['Close'].iloc[-2])
        avg_vol = float(df['Volume'].rolling(50).mean().iloc[-1])
        curr_v  = float(df['Volume'].iloc[-1])
        if curr < stop_loss:
            signals.append('STOP LOSS HIT — Exit immediately')
        if curr_v > avg_vol * 2 and curr < prev * 0.97:
            signals.append('Large red candle on high volume — possible distribution')
        recent_highs = df['High'].tail(10).values
        if all(recent_highs[i] >= recent_highs[i+1] for i in range(4)):
            signals.append('Lower highs forming — trend weakening')
        return signals if signals else ['No exit signals — hold position']

    def _load_history(self):
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_history(self, symbol, scan_date):
        if symbol not in self.history:
            self.history[symbol] = {'first_seen': scan_date, 'appearances': 0}
        self.history[symbol]['appearances'] += 1
        self.history[symbol]['last_seen'] = scan_date
        try:
            with open(self.log_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except:
            pass

    def get_first_seen(self, symbol):
        clean = symbol.replace('.NS', '')
        if clean in self.history:
            return self.history[clean].get('first_seen', 'Today')
        return 'Today'

    def scan_stock(self, symbol):
        df = self.download_data(symbol)
        if df is None:
            return None
        if not self.check_prior_uptrend(df):
            return None

        base_start_idx = self.find_base_start(df)
        base_df_len    = len(df) - base_start_idx
        if base_df_len < 15 or base_df_len > 200:
            return None

        contractions = self.detect_contractions(df, base_start_idx)
        if not self.is_valid_vcp(contractions):
            return None

        pivot         = self.get_pivot(df, base_start_idx)
        current_price = round(float(df['Close'].iloc[-1]), 2)
        pct_from_pivot = (pivot - current_price) / pivot * 100

        if pct_from_pivot < -5 or pct_from_pivot > 10:
            return None

        stop_loss     = self.get_stop_loss(df, contractions)
        targets       = self.calculate_targets(pivot)
        risk          = current_price - stop_loss
        reward_t1     = targets['T1'] - current_price
        rr            = round(reward_t1 / risk, 2) if risk > 0 else 0

        clean_symbol  = symbol.replace('.NS', '')
        sector        = SECTOR_MAP.get(clean_symbol, 'OTHER')
        today_str     = datetime.now().strftime('%Y-%m-%d')
        self._save_history(clean_symbol, today_str)

        result = {
            'symbol':             clean_symbol,
            'current_price':      current_price,
            'pivot':              pivot,
            'pct_from_pivot':     round(pct_from_pivot, 2),
            'stop_loss':          stop_loss,
            'risk_per_share':     round(risk, 2),
            'target_1':           targets['T1'],
            'target_2':           targets['T2'],
            'target_3':           targets['T3'],
            'risk_reward':        rr,
            'vcp_stage':          self.get_vcp_stage(contractions, current_price, pivot),
            'num_contractions':   len(contractions),
            'contractions':       contractions,
            'breakout_info':      self.check_breakout(df, pivot),
            'volume_info':        self.volume_analysis(df),
            'exit_signals':       self.exit_signals(df, pivot, stop_loss),
            'sector':             sector,
            'sector_momentum':    get_sector_momentum(sector),
            'base_start_date':    df.index[base_start_idx].strftime('%Y-%m-%d'),
            'first_seen_scanner': self.get_first_seen(clean_symbol),
            'days_to_t1':         self.days_to_target(df, pivot, targets['T1']),
        }
        result['score'] = calculate_score(result)
        return result

    def scan(self):
        print(f'\nVCP SCANNER | {datetime.now().strftime("%d %b %Y %H:%M")}')
        print(f'Scanning {len(self.symbols)} stocks...\n')
        for i, symbol in enumerate(self.symbols):
            print(f'  [{i+1:02d}/{len(self.symbols)}] {symbol:<20}', end='\r')
            result = self.scan_stock(symbol)
            if result:
                self.results.append(result)
        print(f'\n✅ Found {len(self.results)} VCP setups\n')
        return self.results

    def save_csv(self, filename='vcp_results.csv'):
        if not self.results:
            return
        rows = []
        for r in self.results:
            bo = r['breakout_info']
            vi = r['volume_info']
            rows.append({
                'Symbol': r['symbol'], 'Price': r['current_price'],
                'Pivot': r['pivot'], '% From Pivot': r['pct_from_pivot'],
                'Stop Loss': r['stop_loss'], 'T1': r['target_1'],
                'T2': r['target_2'], 'T3': r['target_3'],
                'R:R': r['risk_reward'], 'Stage': r['vcp_stage'],
                'Contractions': r['num_contractions'], 'Score': r['score'],
                'Sector': r['sector'], 'Sector Momentum': r['sector_momentum'],
                'Vol Drying': vi['drying'], 'Vol %': vi['pct_of_avg'],
                'Broke Out': bo.get('broke_out', False),
            })
        pd.DataFrame(rows).to_csv(filename, index=False)
        print(f'📁 Saved → {filename}')


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    scanner  = VCPScanner(NIFTY_STOCKS)
    results  = scanner.scan()
    scanner.save_csv()

    # Write to Supabase
    sb        = get_supabase()
    scan_date = datetime.now().strftime('%Y-%m-%d')
    write_to_supabase(sb, results, scan_date)

    print(f'\nDone. {len(results)} VCP setups found.')
    for r in sorted(results, key=lambda x: x['score'], reverse=True):
        bo = r['breakout_info']
        print(f"  {r['symbol']:<12} Score:{r['score']:>3}  "
              f"Pivot:₹{r['pivot']}  Stop:₹{r['stop_loss']}  "
              f"T1:₹{r['target_1']}  R:R:{r['risk_reward']}  "
              f"{'⚡ BROKE OUT' if bo.get('broke_out') else ''}")
