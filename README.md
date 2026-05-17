# 📊 Automated Equity Research System — NSE

A two-stage automated stock screening system for the Indian market built with Python and GitHub Actions. Applies institutional top-down analysis — **Market → Sector → Stock** — to surface high-probability breakout candidates from NSE-listed equities.

Delivers results via Telegram. No server required — runs entirely on GitHub Actions free tier.

---

## How It Works

```
Every Sunday (automated)
        │
        ▼
┌─────────────────────┐
│   SCOUT AGENT       │  Downloads sector index data
│   agent.py          │  Calculates 3M + 6M Relative Strength vs Nifty 50
│                     │  Ranks sectors by PRC score
└────────┬────────────┘
         │ Telegram report → you review
         ▼
    YOU decide which sectors are worth scanning
    (edit active_sectors.json)
         │
         ▼  Manual trigger
┌─────────────────────┐
│   SNIPER AGENT      │  Fetches all stocks in active sectors
│   sniper_agent.py   │  Applies global filters (EMA, market cap, liquidity)
│                     │  Scans for 3 chart patterns
└────────┬────────────┘
         │
         ▼
  candidates.json + Telegram alert
```

---

## Breakout Patterns Detected

| Pattern | What It Looks For |
|---|---|
| **VCP** (Volatility Contraction Pattern) | Tight base after a strong move, volume dry-up, within 20% of 52-week high |
| **Flag & Pole** | Sharp pole move, parallel declining channel pullback, price near breakout |
| **Big Base Breakout** | 6–24 week consolidation near highs, multiple support tests, volume declining |

---

## Global Filters Applied to Every Stock

Before any pattern check, every stock must pass:

- Price > ₹20 (no penny stocks)
- Avg daily turnover > ₹5 crore (no microcaps)
- 20-day avg volume > 1 lakh shares (liquidity)
- EMA 11 > EMA 20 > EMA 50 (rising trend structure)
- Price above EMA 50 (not broken down)

---

## Project Structure

```
├── agent.py                  # Scout — sector RS calculation + Telegram report
├── sniper_agent.py           # Sniper — stock scanner + pattern detection
├── bhavcopy.py               # Fetches sector constituent stocks (nsepython + cache)
├── config.json               # Sector tickers + all filter thresholds
│
├── filters/
│   ├── global_filters.py     # EMA, price, market cap, volume filters
│   ├── vcp.py                # Volatility Contraction Pattern
│   ├── flag_pole.py          # Flag & Pole pattern
│   └── big_base.py           # Big Base Breakout pattern
│
├── .github/workflows/
│   ├── sector_strength.yml   # Scout — runs every Sunday 4pm IST
│   └── sniper.yml            # Sniper — manual trigger only
│
├── sector_scores.json        # Output: RS scores for all sectors
├── active_sectors.json       # Input to Sniper: sectors you chose to scan
└── candidates.json           # Output: stocks matching breakout patterns
```

---

## Setup

### 1. Clone the repo
```bash
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
```

### 2. Install dependencies (for local runs)
```bash
pip install requests pandas yfinance numpy nsepython
```

### 3. Create a Telegram Bot
1. Open Telegram → search **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** you receive
4. Start a chat with your new bot, then visit:
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
5. Send any message to the bot and refresh — copy the **chat_id** from the response

### 4. Add GitHub Secrets
Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID from step 3 |

---

## Running the System

### Scout (Sector Report)
- **Automatic:** Runs every Sunday at 4:00 PM IST via `sector_strength.yml`
- **Manual:** GitHub Actions tab → *Scout Agent* → *Run workflow*

### Sniper (Stock Scanner)
1. Review the Telegram sector report
2. Edit `active_sectors.json` with sectors you want to scan:
   ```json
   ["Metal", "Pharma", "Energy"]
   ```
3. Commit and push
4. GitHub Actions tab → *Sniper Agent* → *Run workflow*

### Local Run
```bash
python agent.py          # Run Scout
python sniper_agent.py   # Run Sniper (needs active_sectors.json)
```

---

## Configuration

All thresholds are in `config.json` — no code changes needed to tune the system.

```json
"filters": {
  "global": {
    "min_price_inr": 20,
    "min_avg_turnover_cr": 5
  },
  "vcp": {
    "max_from_52wk_high_pct": 20,
    "min_pole_pct": 25
  }
}
```

To add a new sector, add one line each to `sectors` and `nse_index_names` in `config.json`. No code changes required.

---

## Tech Stack

| Layer | Tool |
|---|---|
| Data | Yahoo Finance (`yfinance`) |
| Constituents | `nsepython` (NSE index member lists) |
| Processing | Python, Pandas, NumPy |
| Scheduling | GitHub Actions (cron) |
| Alerts | Telegram Bot API |
| Config | JSON |

---

## Outputs

| File | Contents |
|---|---|
| `sector_scores.json` | PRC, 3M RS, 6M RS for every tracked sector |
| `candidates.json` | Stocks passing all filters, tagged by pattern |
| `candidates.csv` | Same data, spreadsheet-friendly |
| `sector_stocks_cache.json` | Cached constituent lists (refreshed daily) |
