# Sentinel — Trustless Regime-Adaptive Trading Agent

> **LabLab AI Trading Agents Hackathon** ERC-8004 Track

## What is Sentinel?

Sentinel is an autonomous DeFi trading agent that adapts its strategy to current market conditions using regime detection. Unlike fixed-strategy bots, Sentinel detects whether the market is trending or ranging and switches between momentum and mean-reversion strategies accordingly.

All trading decisions are verified on-chain through the **ERC-8004** standard, establishing the agent's identity, building its reputation, and producing validation artifacts — making it a **trustless agent** that can prove its behavior.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Sentinel Agent                        │
├───────────────────┬──────────────┬──────────────────────────┤
│ Strategy Engine   │ Risk Manager │     ERC-8004 Integration │
│                   │              │                          │
│ • Regime          │ • Position   │ • Identity NFT           │
│   Detection       │   Sizing     │ • Reputation Log         │
│ • Momentum        │ • Stop-Loss  │ • Validation Artifacts   │
│   (MACD)          │ • Drawdown   │ • Compliance Reports     │
│ • Mean Rev.       │ • Daily Cap  │                          │
│   (BB + RSI)      │ • Kill Sw.   │                          │
├────────────────── ┴──────────────┴──────────────────────────┤
│                          Data Layer                         │
│  Kraken CLI (MCP) │   yfinance   │ Aerodrome │ PRISM        │
└─────────────────────────────────────────────────────────────┘
```

## Key Features

### Regime-Adaptive Strategy
- **ADX + EMA crossover** regime detection (trending vs sideways)
- **Momentum strategy**: MACD crossovers with trend confirmation
- **Mean reversion strategy**: Bollinger Bands + RSI for overbought/oversold
- Smooth regime transitions with confirmation periods

### Risk Management
- Position sizing: max 5% of equity per trade
- Per-trade stop-loss (ATR-based)
- Max drawdown limit: 10% → automatic halt
- Daily loss limit: 3%
- Anti-whipsaw trade interval enforcement

### ERC-8004 Trustless Identity
- On-chain agent identity (ERC-721 NFT on Base)
- Reputation registry: verifiable trade history
- Validation artifacts: signed proofs of trade decisions
- Full compliance reports for transparency

### Live Dashboard
- Real-time P&L tracking
- Regime and strategy visualization
- Risk metrics monitoring
- ERC-8004 on-chain status

## Quick Start

```bash
# Install dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run a single analysis iteration
python -m agent.main --once --source yfinance

# Run continuous trading (paper mode)
python -m agent.main --symbols BTCUSD ETHUSD --capital 10000 --interval 60

# With Kraken CLI (if installed)
python -m agent.main --source kraken --symbols BTCUSD ETHUSD
```

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Agent Core | Python 3.10+ |
| Trading Data | Kraken CLI, yfinance, ccxt |
| Strategy | pandas, numpy, custom indicators |
| On-Chain | Solidity, Web3.py, Base L2 |
| Dashboard | HTML/JS/CSS, Flask-SocketIO |
| Standard | ERC-8004 (Identity, Reputation, Validation) |

## Trading Strategies

### Regime Detection
Uses ADX (Average Directional Index) with EMA crossovers:
- ADX > 25 → **Trending** market → activate Momentum strategy
- ADX < 20 → **Sideways** market → activate Mean Reversion strategy
- Confirmation period prevents whipsaw between regimes

### Momentum (Trending Markets)
- Entry: MACD bullish/bearish crossover + price above/below EMA-50
- Exit: Trailing stop (1.5x ATR) or 2:1 reward/risk take-profit
- Confidence scoring: MACD histogram direction, RSI confirmation

### Mean Reversion (Sideways Markets)
- Entry: Price at Bollinger Band extremes + RSI overbought/oversold
- Exit: Price returns to middle band (SMA-20)
- Bollinger squeeze detection to avoid false signals during breakouts

## Project Structure

```
ERC-8004/
├── agent/                    # Python trading agent
│   ├── main.py              # Entry point & orchestrator
│   ├── strategy/            # Trading strategies
│   │   ├── regime.py        # Market regime detection
│   │   ├── momentum.py      # MACD momentum strategy
│   │   ├── mean_reversion.py # Bollinger + RSI
│   │   └── ensemble.py      # Regime-adaptive switcher
│   ├── risk/                # Risk management
│   │   └── manager.py       # Position sizing, stops, limits
│   ├── data/                # Market data
│   │   ├── market.py        # Multi-source data fetcher
│   │   └── indicators.py    # Technical indicators
│   └── chain/               # ERC-8004 integration
├── contracts/               # Solidity contracts
├── dashboard/               # Web monitoring dashboard
├── backtest/                # Backtesting framework
└── docs/                    # Documentation
```

## License

MIT

## Author

Built for the AI Trading Agents Hackathon 2026 (lablab.ai)
