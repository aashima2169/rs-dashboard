"""
vcp_scanner.py
--------------
Scans NSE stocks for Volatility Contraction Pattern (VCP).
Based on Mark Minervini's method.

Flow:
  1. Reads STRONG sectors from Supabase (latest scan from agent.py)
  2. Fetches constituent stocks for those sectors via nsepython
  3. Scans each stock for VCP pattern
  4. Writes candidates directly to Supabase stock_candidates table

No CSV output — all results go to Supabase.
Does not affect agent.py or macro_agent.py.
"""

import os
import json
import warnings
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

warnings.filterwarnings('ignore')

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


# ── Sector to NSE index mapping ───────────────────────────────────────────────

SECTOR_INDEX_MAP = {
    'Pharma'      : '^CNXPHARMA',
    'Metal'       : '^CNXMETAL',
    'Energy'      : '^CNXENERGY',
    'Infra'       : '^CNXINFRA',
    'MNC'         : '^CNXMNC',
    'FMCG'        : '^CNXFMCG',
    'Media'       : '^CNXMEDIA',
    'Commodities' : '^CNXCOMMODITIES',
    'PSE'         : '^CNXPSE',
    'PSUBank'     : '^CNXPSUBANK',
    'IT'          : '^CNXIT',
    'Bank'        : '^NSEBANK',
    'Auto'        : '^CNXAUTO',
    'Realty'      : '^CNXREALTY',
    'Consumption' : '^CNXCONSUMPTION',
    'FinServices' : '^CNXFINANCE',
    'Services'    : '^CNXSERVICE',
}

# Curated liquid stocks per sector — used as fallback
SECTOR_STOCKS = {
    'Pharma'      : ['SUNPHARMA', 'DIVISLAB', 'CIPLA', 'DRREDDY', 'AUROPHARMA', 'ALKEM', 'TORNTPHARM', 'IPCALAB', 'GLENMARK', 'LUPIN'],
    'Metal'       : ['TATASTEEL', 'HINDALCO', 'JSWSTEEL', 'SAIL', 'NMDC', 'VEDL', 'NATIONALUM', 'HINDCOPPER', 'APLAPOLLO'],
    'Energy'      : ['RELIANCE', 'ONGC', 'BPCL', 'IOC', 'HINDPETRO', 'GAIL', 'IGL', 'MGL', 'PETRONET'],
    'Infra'       : ['LT', 'ADANIPORTS', 'ADANIENT', 'IRB', 'KNRCON', 'PNCINFRA', 'CONCOR', 'ENGINERSIN'],
    'MNC'         : ['ABBINDIA', 'SIEMENS', 'HONAUT', 'CUMMINSIND', 'ASIANPAINT', 'BOSCHLTD', 'SCHAEFFLER'],
    'FMCG'        : ['HINDUNILVR', 'ITC', 'NESTLEIND', 'BRITANNIA', 'DABUR', 'MARICO', 'GODREJCP', 'COLPAL', 'TATACONSUM'],
    'Media'       : ['ZEEL', 'SUNTV', 'PVRINOX', 'NAZARA', 'NAUKRI', 'AFFLE', 'SAREGAMA'],
    'Commodities' : ['HINDALCO', 'NMDC', 'COALINDIA', 'GRASIM', 'PIDILITIND', 'AARTIIND', 'DEEPAKNTR'],
    'PSE'         : ['NTPC', 'POWERGRID', 'BHEL', 'RVNL', 'IRFC', 'RECLTD', 'PFC', 'BEL', 'HAL'],
    'PSUBank'     : ['SBIN', 'BANKBARODA', 'PNB', 'CANBK', 'UNIONBANK', 'MAHABANK', 'INDIANB'],
    'IT'          : ['TCS', 'INFY', 'HCLTECH', 'WIPRO', 'TECHM', 'LTIM', 'MPHASIS', 'PERSISTENT', 'COFORGE'],
    'Bank'        : ['HDFCBANK', 'ICICIBANK', 'KOTAKBANK', 'AXISBANK', 'INDUSINDBK', 'FEDERALBNK', 'IDFCFIRSTB'],
    'Auto'        : ['MARUTI', 'TATAMOTORS', 'M&M', 'BAJAJ-AUTO', 'HEROMOTOCO', 'EICHERMOT', 'TVSMOTOR'],
    'Realty'      : ['DLF', 'GODREJPROP', 'PRESTIGE', 'OBEROIRLTY', 'BRIGADE', 'SOBHA'],
    'Consumption' : ['TITAN', 'VOLTAS', 'HAVELLS', 'CROMPTON', 'PAGEIND', 'TRENT', 'BATAINDIA'],
    'FinServices' : ['BAJFINANCE', 'BAJAJFINSV', 'MUTHOOTFIN', 'CHOLAFIN', 'SBICARD', 'HDFCLIFE'],
    'Services'    : ['IRCTC', 'CDSL', 'BSE', 'MCX', 'CAMS', 'ANGELONE'],
}


# ── Supabase ──────────────────────────────────────────────────────────────────

def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️  Supabase not configured")
        return None
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase connected")
        return client
    except Exception as e:
        print(f"❌ Supabase failed: {e}")
        return None


def get_strong_sectors(sb):
    """Read latest STRONG sectors from sector_scores table."""
    try:
        latest = sb.table("sector_scores") \
                   .select("scan_date") \
                   .order("scan_date", desc=True) \
                   .limit(1).execute()
        if not latest.data:
            return []
        scan_date = latest.data[0]['scan_date']
        result = sb.table("sector_scores") \
                   .select("sector, prc, category") \
                   .eq("scan_date", scan_date) \
                   .eq("category", "STRONG") \
                   .order("prc", desc=True) \
                   .execute()
        sectors = [r['sector'] for r in result.data]
        print(f"✅ Strong sectors ({scan_date}): {sectors}")
        return sectors
    except Exception as e:
        print(f"❌ get_strong_sectors failed: {e}")
        return []


def get_stocks_for_sectors(sectors):
    """Return deduplicated list of stocks from strong sectors."""
    stocks = []
    for sector in sectors:
        sector_stocks = SECTOR_STOCKS.get(sector, [])
        for s in sector_stocks:
            if s not in stocks:
                stocks.append(s)
    print(f"📊 {len(stocks)} stocks to scan across {len(sectors)} strong sectors")
    return stocks


def write_to_supabase(sb, results, scan_date):
    if not sb or not results:
        print("ℹ️  No results to write")
        return
    try:
        # Clear today's existing VCP rows
        sb.table("stock_candidates") \
          .delete().eq("scan_date", scan_date).eq("pattern", "VCP").execute()

        rows = []
        for r in results:
            bo = r.get('breakout_info', {})
            vi = r.get('volume_info', {})
            rows.append({
                "scan_date"        : scan_date,
                "symbol"           : r['symbol'],
                "sector"           : r.get('sector', 'Other'),
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
                "sector_momentum"  : r.get('sector_momentum', 'Unknown'),
                "base_start_date"  : r.get('base_start_date'),
                "first_seen"       : r.get('first_seen'),
                "broke_out"        : bo.get('broke_out', False),
                "breakout_date"    : bo['date'].strftime('%Y-%m-%d') if bo.get('date') else None,
                "days_to_t1"       : r.get('days_to_t1'),
                "score"            : r.get('score', 0),
                "ema_aligned"      : r.get('ema_aligned', False),
                "bb_squeeze"       : r.get('bb_squeeze', False),
                "obv_rising"       : r.get('obv_rising', False),
                "rsi_in_zone"      : r.get('rsi_in_zone', False),
                "rsi_value"        : r.get('rsi_value'),
                "rising_lows"      : r.get('rising_lows', False),
                "handle_formed"    : r.get('handle_formed', False),
                "pivot_rejections" : r.get('pivot_rejections', 0),
                "near_52w_high"    : r.get('near_52w_high', False),
                "pct_from_52w_high": r.get('pct_from_52w_high'),
            })

        sb.table("stock_candidates").insert(rows).execute()
        print(f"✅ {len(rows)} VCP candidates written to Supabase")
    except Exception as e:
        print(f"❌ Supabase write failed: {e}")


# ── Data helpers ──────────────────────────────────────────────────────────────

def download(symbol):
    try:
        df = yf.download(f"{symbol}.NS", period='1y',
                         interval='1d', progress=False)
        if df is None or len(df) < 100:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df.dropna()
    except:
        return None


def find_swings(high, low, window=4):
    highs, lows = [], []
    for i in range(window, len(high) - window):
        if high.iloc[i] == high.iloc[i-window:i+window+1].max():
            highs.append((i, float(high.iloc[i]), high.index[i]))
        if low.iloc[i] == low.iloc[i-window:i+window+1].min():
            lows.append((i, float(low.iloc[i]), low.index[i]))
    return highs, lows


# ── VCP logic ─────────────────────────────────────────────────────────────────

def check_prior_uptrend(df):
    if len(df) < 150:
        return False
    close = df['Close']
    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma150 = float(close.rolling(150).mean().iloc[-1])
    curr  = float(close.iloc[-1])
    low52 = float(df['Low'].tail(252).min())
    return curr > ma50 and ma50 > ma150 and curr >= low52 * 1.20


def find_base_start(df):
    lookback = min(len(df), 200)
    peak_idx = df.tail(lookback)['High'].idxmax()
    return max(0, df.index.get_loc(peak_idx))


def detect_contractions(df, base_start):
    base = df.iloc[base_start:]
    if len(base) < 15:
        return []
    highs, lows = find_swings(base['High'], base['Low'])
    contractions = []
    for i in range(len(highs) - 1):
        h1_i, h1_p, h1_d = highs[i]
        h2_i, h2_p, h2_d = highs[i + 1]
        between = [(li, lp, ld) for li, lp, ld in lows if h1_i < li < h2_i]
        if not between:
            continue
        trough = min(between, key=lambda x: x[1])
        contractions.append({
            'number'         : len(contractions) + 1,
            'high_price'     : round(h1_p, 2),
            'low_price'      : round(trough[1], 2),
            'contraction_pct': round((h1_p - trough[1]) / h1_p * 100, 2),
            'duration_days'  : h2_i - h1_i,
            'start_date'     : str(h1_d),
        })
    return contractions


def is_valid_vcp(contractions):
    if len(contractions) < 2:
        return False
    for i in range(1, len(contractions)):
        if contractions[i]['contraction_pct'] >= contractions[i-1]['contraction_pct'] + 1:
            return False
    return True


def vcp_stage(contractions, current_price, pivot):
    n   = len(contractions)
    pct = (pivot - current_price) / pivot * 100
    if n == 1:   label = 'Early VCP (T1) — Base forming'
    elif n == 2: label = 'Mid VCP (T2) — Tightening'
    else:
        last  = contractions[-1]['contraction_pct']
        label = f'Late VCP (T{n}) — Tight Coil' if last < 5 else f'Late VCP (T{n}) — Near pivot'
    if pct <= 3:   label += ' — VERY CLOSE TO PIVOT'
    elif pct <= 7: label += ' — Approaching pivot'
    return label


def volume_analysis(df):
    recent = float(df['Volume'].tail(20).mean())
    base   = float(df['Volume'].tail(60).head(40).mean())
    return {
        'drying'    : recent < base * 0.75,
        'recent_avg': int(recent),
        'base_avg'  : int(base),
        'pct_of_avg': round(recent / base * 100, 1) if base > 0 else 100,
    }


def check_breakout(df, pivot):
    avg_vol = float(df['Volume'].rolling(50).mean().iloc[-1])
    for i in range(len(df) - 30, len(df)):
        close = float(df['Close'].iloc[i])
        vol   = float(df['Volume'].iloc[i])
        if close > pivot and vol > avg_vol * 1.5:
            after    = df.iloc[i:]
            held     = all(float(r['Close']) > pivot * 0.97 for _, r in after.iterrows())
            gain_pct = round((float(df['Close'].iloc[-1]) - close) / close * 100, 2)
            return {
                'broke_out' : True,
                'date'      : df.index[i],
                'held'      : held,
                'gain_since': gain_pct,
            }
    return {'broke_out': False}


def days_to_target(df, pivot, target):
    avg_vol = df['Volume'].rolling(50).mean()
    for i in range(50, len(df) - 1):
        if float(df['Close'].iloc[i]) > pivot and \
           float(df['Volume'].iloc[i]) > float(avg_vol.iloc[i]) * 1.5:
            after = df.iloc[i:]
            hit   = after[after['High'] >= target]
            return (hit.index[0] - df.index[i]).days if not hit.empty else None
    return None


# ── Technical signals ────────────────────────────────────────────────────────

def check_ema_alignment(df):
    """EMA 8 > 21 > 50 > 200 = clean uptrend structure"""
    close = df['Close']
    if len(close) < 200:
        return False
    e8   = float(close.ewm(span=8).mean().iloc[-1])
    e21  = float(close.ewm(span=21).mean().iloc[-1])
    e50  = float(close.ewm(span=50).mean().iloc[-1])
    e200 = float(close.ewm(span=200).mean().iloc[-1])
    return e8 > e21 > e50 > e200


def check_obv_rising(df):
    """OBV rising in base = institutions accumulating quietly"""
    if len(df) < 40:
        return False
    obv = (df['Volume'] * df['Close'].diff().apply(
        lambda x: 1 if x > 0 else -1 if x < 0 else 0)).cumsum()
    recent = obv.tail(20)
    return float(recent.tail(10).mean()) > float(recent.head(10).mean())


def check_rsi_zone(df):
    """RSI 40-65 = ideal pre-breakout zone"""
    close = df['Close'].tail(15)
    delta = close.diff()
    gain  = delta.clip(lower=0).mean()
    loss  = (-delta.clip(upper=0)).mean()
    rs    = gain / loss if loss != 0 else 100
    rsi   = 100 - (100 / (1 + rs))
    return 40 <= rsi <= 65, round(float(rsi), 1)


def check_rising_lows(df):
    """At least 5 of last 10 weekly lows are higher than previous"""
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    weekly_low = df['Low'].resample('W').min().tail(10)
    if len(weekly_low) < 6:
        return False
    rising = sum(1 for i in range(1, len(weekly_low))
                 if weekly_low.iloc[i] >= weekly_low.iloc[i-1])
    return rising >= 5


def check_handle_formed(df, base_start):
    """Tight consolidation in upper half of base = handle"""
    base = df.iloc[base_start:]
    if len(base) < 20:
        return False
    base_high = float(base['High'].max())
    base_low  = float(base['Low'].min())
    mid       = (base_high + base_low) / 2
    recent    = base.tail(10)
    tight     = (float(recent['High'].max()) - float(recent['Low'].min())) / base_high * 100 < 10
    upper     = float(recent['Close'].mean()) > mid
    return tight and upper


def count_pivot_rejections(df, pivot):
    """Price touched pivot zone but closed below — bearish signal"""
    recent     = df.tail(60)
    rejections = 0
    for i in range(len(recent)):
        high  = float(recent['High'].iloc[i])
        close = float(recent['Close'].iloc[i])
        if high >= pivot * 0.98 and close < pivot * 0.99:
            rejections += 1
    return rejections


def enhance_result(result, df):
    """Compute all technical signals and attach to result"""
    base_start = result.get('_base_start', 0)
    pivot      = result.get('pivot', 0)

    result['ema_aligned']      = check_ema_alignment(df)
    result['obv_rising']       = check_obv_rising(df)
    rsi_ok, rsi_val            = check_rsi_zone(df)
    result['rsi_in_zone']      = rsi_ok
    result['rsi_value']        = rsi_val
    result['rising_lows']      = check_rising_lows(df)
    result['handle_formed']    = check_handle_formed(df, base_start)
    result['pivot_rejections'] = count_pivot_rejections(df, pivot)

    curr   = float(df['Close'].iloc[-1])
    high52 = float(df['High'].tail(252).max())
    result['pct_from_52w_high'] = round((high52 - curr) / high52 * 100, 1)
    result['near_52w_high']     = result['pct_from_52w_high'] <= 15

    return result


def calculate_score(r):
    """
    VCP score 0-100 using 7 core signals + penalty.

    Contractions quality   max 20
    Volume drying          max 15
    Distance from pivot    max 15
    Risk:Reward            max 10
    EMA aligned            max 10
    OBV rising             max 10
    RSI in zone            max 8
    Rising lows            max 8
    Handle formed          max 7
    Pivot rejections       max -12 (penalty)
    """
    score = 0

    # Contraction quality (max 20)
    score += min(20, r.get('num_contractions', 0) * 7)

    # Volume drying (max 15)
    if r.get('volume_info', {}).get('drying'):
        score += 15

    # Distance from pivot (max 15)
    pct = abs(r.get('pct_from_pivot', 10))
    if pct <= 2:    score += 15
    elif pct <= 5:  score += 10
    elif pct <= 10: score += 5

    # Risk:Reward (max 10)
    rr = r.get('risk_reward', 0)
    if rr >= 4:    score += 10
    elif rr >= 3:  score += 8
    elif rr >= 2:  score += 5
    elif rr >= 1:  score += 2

    # EMA alignment (max 10)
    if r.get('ema_aligned'):
        score += 10

    # OBV rising (max 10)
    if r.get('obv_rising'):
        score += 10

    # RSI in zone (max 8)
    if r.get('rsi_in_zone'):
        score += 8

    # Rising lows (max 8)
    if r.get('rising_lows'):
        score += 8

    # Handle formed (max 7)
    if r.get('handle_formed'):
        score += 7

    # Pivot rejections penalty
    score -= min(12, r.get('pivot_rejections', 0) * 4)

    return max(0, min(100, score))


# ── History tracking ──────────────────────────────────────────────────────────

_history    = {}
HISTORY_FILE = 'vcp_history.json'

def load_history():
    global _history
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                _history = json.load(f)
        except:
            pass

def save_history(symbol, today):
    if symbol not in _history:
        _history[symbol] = {'first_seen': today, 'count': 0}
    _history[symbol]['count']    += 1
    _history[symbol]['last_seen'] = today
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(_history, f, indent=2)
    except:
        pass

def first_seen(symbol):
    return _history.get(symbol, {}).get('first_seen', 'Today')


# ── Scan single stock ─────────────────────────────────────────────────────────

def scan_stock(symbol, sector):
    df = download(symbol)
    if df is None:
        return None
    if not check_prior_uptrend(df):
        return None

    base_start = find_base_start(df)
    base_len   = len(df) - base_start
    if base_len < 15 or base_len > 200:
        return None

    contractions = detect_contractions(df, base_start)
    if not is_valid_vcp(contractions):
        return None

    pivot          = round(float(df['High'].iloc[base_start:].max()), 2)
    current_price  = round(float(df['Close'].iloc[-1]), 2)
    pct_from_pivot = (pivot - current_price) / pivot * 100

    if pct_from_pivot < -5 or pct_from_pivot > 10:
        return None

    stop_loss = round(float(contractions[-1]['low_price']), 2)
    t1        = round(pivot * 1.15, 2)
    t2        = round(pivot * 1.25, 2)
    t3        = round(pivot * 1.40, 2)
    risk      = current_price - stop_loss
    rr        = round((t1 - current_price) / risk, 2) if risk > 0 else 0

    today = datetime.now().strftime('%Y-%m-%d')
    save_history(symbol, today)

    vol_info = volume_analysis(df)
    breakout = check_breakout(df, pivot)

    result = {
        'symbol'          : symbol,
        'sector'          : sector,
        'current_price'   : current_price,
        'pivot'           : pivot,
        'pct_from_pivot'  : round(pct_from_pivot, 2),
        'stop_loss'       : stop_loss,
        'risk_per_share'  : round(risk, 2),
        'target_1'        : t1,
        'target_2'        : t2,
        'target_3'        : t3,
        'risk_reward'     : rr,
        'vcp_stage'       : vcp_stage(contractions, current_price, pivot),
        'num_contractions': len(contractions),
        'contractions'    : contractions,
        'volume_info'     : vol_info,
        'breakout_info'   : breakout,
        'sector_momentum' : 'Strong',
        'base_start_date' : df.index[base_start].strftime('%Y-%m-%d'),
        'first_seen'      : first_seen(symbol),
        'days_to_t1'      : days_to_target(df, pivot, t1),
        '_base_start'     : base_start,
    }
    result = enhance_result(result, df)
    result['score'] = calculate_score(result)
    result.pop('_base_start', None)
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print(f"\n🎯 VCP SCANNER | {datetime.now().strftime('%d %b %Y %H:%M')}")

    load_history()
    sb        = get_supabase()
    scan_date = datetime.now().strftime('%Y-%m-%d')

    # Get strong sectors from Supabase
    if sb:
        strong_sectors = get_strong_sectors(sb)
    else:
        strong_sectors = list(SECTOR_STOCKS.keys())
        print(f"⚠️  Supabase not available — scanning all sectors")

    if not strong_sectors:
        print("❌ No strong sectors found — exiting")
        return

    # Get stocks for strong sectors
    stocks_to_scan = get_stocks_for_sectors(strong_sectors)

    if not stocks_to_scan:
        print("❌ No stocks to scan")
        return

    print(f"   Scanning {len(stocks_to_scan)} stocks...\n")

    results = []
    for i, symbol in enumerate(stocks_to_scan):
        sector = next((s for s, stocks in SECTOR_STOCKS.items()
                      if symbol in stocks), 'Other')
        print(f"  [{i+1:02d}/{len(stocks_to_scan)}] {symbol:<15}", end='\r')
        result = scan_stock(symbol, sector)
        if result:
            results.append(result)

    results.sort(key=lambda x: x['score'], reverse=True)
    print(f"\n✅ Found {len(results)} VCP setups in strong sectors\n")

    for r in results:
        bo = r['breakout_info']
        print(f"  {r['symbol']:<12} Score:{r['score']:>3}  "
              f"T{r['num_contractions']}  "
              f"Pivot:₹{r['pivot']}  Stop:₹{r['stop_loss']}  "
              f"T1:₹{r['target_1']}  R:R:{r['risk_reward']}  "
              f"{'⚡ BROKE OUT' if bo.get('broke_out') else ''}")

    # Write to Supabase only — no CSV
    write_to_supabase(sb, results, scan_date)
    print(f"\nDone.")
    return results


if __name__ == '__main__':
    run()
