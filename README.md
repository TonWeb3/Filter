# Polymarket BTC 15m Assistant (Python FastAPI)

A real-time, high-performance automated trading assistant for Polymarket **"Bitcoin Up or Down" 15-minute** binary options markets, powered by FastAPI and the **Stage 7 (Overall Champion) 🏆** quantitative strategy.

> **📖 Empirical Backtest Reference:** Tested and validated on historical 15m Polymarket BTC markets in `Scripts/FILTERS_REPORT.md` and `Scripts/results/optimization_report.md` (Net Profit: **+$214,357.25**, Win Rate: **77.2%**, Profit Factor: **2.60**).

---

## 🏆 Stage 7 (Overall Champion) Strategy

The bot utilizes the Stage 7 quantitative engine, combining latency arbitrage with structural trend filters and systematic drawdown defense:

### 1. Alpha & Conviction Gates
- **Closed-Form Fair Probability Model**: High-frequency Geometric Brownian Motion (GBM) calculating true directional probability from live Binance spot ticks vs Polymarket CLOB ask prices.
- **Expected Value (EV) Gate (`ev_threshold: 0.04`)**: Requires at least a **4¢ net edge** ($\text{fair prob} - \text{market ask} \ge 0.04$) before placing orders.
- **Directional Floor (`min_prob: 0.55`)**: Forbids 50/50 coin-flip entries even if EV appears slightly positive.
- **Strike Moneyness Lead (`min_strike_distance_bp: 6.0`)**: Requires Bitcoin spot to have moved at least **6.0 basis points** ($\approx \$60$ on BTC) away from the market opening strike in the bet direction, completely eliminating the hostile 50/50 chop noise zone.
- **15m Structural Heiken-Ashi (`use_15m_ha: true`)**: Analyzes the active 15m Heiken-Ashi candle. Automatically blocks counter-trend DOWN bets during flat-bottom green expansion candles (institutional bull trends) and blocks UP bets during flat-top red candles (institutional bear trends).
- **Micro-Vetoes OFF**: 1m RSI and 1m/5m Heiken-Ashi exhaustion streak vetoes are **completely bypassed**. Backtesting demonstrated that micro-vetoes prematurely halted strong 15m trend continuations that held a $69.5\%$ win rate.

### 2. Drawdown Defense Architecture
- **Consecutive Loss Circuit Breaker (`circuit_breaker_losses: 2`, `pause_markets: 4`)**: Reaching **2 consecutive losses** indicates hostile consolidation chop. The bot automatically halts new entries for **4 markets (60 minutes)** to protect capital, resetting on the next win.
- **Realized Volatility / 1h ATR Ceiling (`max_1h_vol_bp: 45.0`)**: Evaluates the trailing 1-hour True Range across active 15m klines. Blocks trades when volatility exceeds $45.0\text{ bp}$ (violent macro whipsaws).
- **Window Timing Envelope (`min_entry_second: 90`, `max_entry_second: 600`)**: Trades only between second 90 and second 600 (minute 1.5 to minute 10) of each 15m candle, skipping chaotic open spreads and late-candle volatility decay.
- **Transition Hours Filter (`skip_hours: [18, 23] UTC`)**: Automatically sits out 18:00 UTC (US equity cash close rebalance) and 23:00 UTC (daily funding settlement).

---

## Features

- **Real-Time Web Dashboard**: Responsive dark-mode interface built with FastAPI, Jinja2, Alpine.js, and WebSockets.
- **Stage 7 Strategy Monitor**: Live visual tracking of Moneyness Lead, 15m HA Structure, 1h Realized Volatility, Timing Gate, and Circuit Breaker status.
- **Multi-Stream Ingestion**: Concurrent WebSocket streams for Binance Spot, Binance Klines (1m, 5m, 15m), Polymarket CLOB Level 2 Orderbook, and Chainlink Price Feeds.
- **Trading Modes**: Seamless toggle between zero-risk **Paper Trading** and on-chain **Live Trading**.
- **Gasless Polymarket CLOB V2 Execution**: Places Fill-Or-Kill (FOK) market orders via `polymarket-apis` using the official gasless deposit-wallet flow.
- **Capital Extractor**: Configurable auto-withdrawal state machine to sweep accumulated profits to your cold storage or EOA wallet.
- **Telegram Notifications**: Real-time alerts for Trade Entries, Wins, Losses, Circuit Breaker triggers, and Auto-Withdrawals.

---

## Requirements

- Python **3.12+**
- pip package manager

---

## Quick Start

### 1) Install Dependencies

```bash
pip install -r requirements.txt
```

### 2) Configuration (`config.json`)

All parameters are centrally managed in `config.json` and editable live in the dashboard **Settings** page:

```json
{
  "mode": "paper",
  "paper_balance_usd": 1000.0,
  "trading": {
    "symbol": "BTCUSDT",
    "candle_window_minutes": 15,
    "risk_type": "percent",
    "risk_value": 10
  },
  "strategy": {
    "ev_threshold": 0.04,
    "min_prob": 0.55,
    "min_strike_distance_bp": 6.0,
    "min_entry_second": 90,
    "max_entry_second": 600,
    "use_15m_ha": true,
    "circuit_breaker_losses": 2,
    "pause_markets": 4,
    "max_1h_vol_bp": 45.0,
    "skip_hours": [18, 23],
    "min_book_liquidity_usd": 20.0,
    "max_book_age_s": 3.0
  }
}
```

### 3) Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open your browser to `http://localhost:8000`.

---

## Live Trading Setup (Gasless CLOB V2)

To enable real-money trading on Polymarket:

1. **Private Key**: Provide your Polygon private key in `config.json` or on the Settings page. This key signs orders locally; gas is sponsored by Polymarket's relayer.
2. **Relayer API Key**: Obtain a Polymarket Builder / Relayer API key and configure it under `relayer.api_key`.
3. **Wallet Connection**: In the Settings page, click **Test Connection** to detect your deposit wallet and view current pUSD balances.
4. **Deploy & Approve**: Click **Setup Wallet (gasless)** to execute one-time token approvals.
5. **Start Trading**: Switch mode to `live`, set your risk parameters, and press **Start** on the main dashboard.

---

## Safety & Disclaimer

This software is for quantitative research and educational purposes. Automated trading involves substantial financial risk. Run extensively in **Paper Mode** to confirm performance and latency alignment before risking capital in live markets.
