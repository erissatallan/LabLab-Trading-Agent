# AI Trading Agents Hackathon — Discussion Log

**Hackathon**: AI Trading Agents (lablab.ai)  
**Dates**: March 30 – April 12, 2026  
**Participant**: Allan Erissat (solo)  
**Started**: March 31, 2026  

---

## Session 1: Research & Strategy (Mar 31, 2026 08:27 EAT)

### Hackathon Overview
- **Total Prize Pool**: $55,000 across two tracks
- **Registration**: Must register project at early.surge.xyz for prize eligibility
- **Format**: Online, build-in-public, solo or team
- **Social Engagement Score**: Part of competition (Twitter/X, YouTube, blogs)

### Two Tracks

| Aspect | ERC-8004 Challenge | Kraken CLI Challenge |
|--------|-------------------|---------------------|
| **Goal** | Build trustless financial agent using ERC-8004 registries | Build autonomous trading agent using Kraken CLI |
| **Judging** | Risk-adjusted profitability, drawdown control, validation quality | Net PnL performance only |
| **Infrastructure** | Hackathon Capital Sandbox (vault + risk router on Base) | Kraken paper trading / live |
| **Verification** | On-chain validation artifacts | Read-only Kraken API key for leaderboard |
| **Top Prize** | $10,000 SURGE + Trading Capital Program fast-track | $1,800 (1st), $750 (2nd), $450 (3rd) |
| **Special Awards** | Best Yield/Portfolio ($2,500), Best Compliance & Risk ($2,500) | — |

### Strategic Decision: Focus on ERC-8004
**Rationale**:
1. Higher prize pool ($10K + $5K + special awards vs $3K total for Kraken)
2. Judged on risk-adjusted returns + quality, not raw PnL — better for a newcomer since we can compete on design quality
3. Special awards (Best Yield/Portfolio, Best Compliance & Risk Guardrails) are reachable for a solo builder focusing on design
4. ERC-8004 is newer, so fewer people will have deep expertise — more level playing field
5. We can still build Kraken CLI integration into the agent for Kraken track compatibility

### What is ERC-8004?
The "Trustless Agents" Ethereum standard with 3 on-chain registries:
1. **Identity Registry** (ERC-721 NFT) — unique agent identity with metadata (name, capabilities, endpoints)
2. **Reputation Registry** — standardized feedback/ratings after agent interactions
3. **Validation Registry** — independent verification of agent work (staking, zkML proofs, TEE attestations)

Deployed on Ethereum mainnet Jan 29, 2026. Works on EVM chains including Base (where hackathon sandbox is).

### Key Technology Stack
- **Kraken CLI**: Rust binary, built-in MCP server, 134 commands, paper trading sandbox
- **ERC-8004**: On-chain identity/reputation/validation contracts
- **Aerodrome Finance**: DEX on Base network (liquidity pools, swaps)
- **PRISM API**: Agent data resolution and market insights (Prism Finance SDK + Dapto multi-model gateway)
- **Base Network**: L2 where the hackathon sandbox operates

### Trading Strategy Research
Strategies with proven track records for algorithmic trading:

1. **Mean Reversion + RSI** — buy when oversold (RSI < 30), sell when overbought (RSI > 70). Works well in range-bound/sideways markets.
2. **Momentum + MACD** — follow trends using MACD crossovers. Works in trending markets.
3. **Bollinger Bands** — mean reversion variant using statistical bands for entry/exit.
4. **Combined Regime Detection** — detect market regime (trending vs sideways) and switch strategies accordingly. This is the most sophisticated and competitive approach.

**Decision**: Use a regime-detecting multi-strategy approach. Use MACD/momentum in trending markets, mean reversion in sideways markets. This maximizes risk-adjusted returns (what ERC-8004 track judges on).

### Project Concept: "Sentinel" — Trustless Regime-Adaptive Trading Agent
A DeFi trading agent that:
1. Registers on-chain via ERC-8004 (identity, capabilities, risk parameters)
2. Detects market regimes using statistical analysis
3. Switches between momentum and mean-reversion strategies
4. Logs all trades as validation artifacts on-chain
5. Manages risk with stop-losses, position sizing, max drawdown limits
6. Optionally integrates with Kraken CLI for CEX trading (Kraken track compatibility)

### Architecture (High-Level)
```
┌─────────────────────────────────────────────┐
│              Sentinel Agent                  │
├────────────┬──────────┬────────────────────┤
│  Strategy  │   Risk   │   ERC-8004         │
│  Engine    │  Manager │   Integration      │
│            │          │                     │
│ • Regime   │ • Stop   │ • Identity NFT     │
│   Detect   │   Loss   │ • Reputation Log   │
│ • RSI/MACD │ • Size   │ • Validation       │
│ • Bolling. │ • DD Cap │   Artifacts        │
├────────────┴──────────┴────────────────────┤
│            Data Layer                       │
│  Kraken CLI (MCP) | Aerodrome | PRISM API  │
└─────────────────────────────────────────────┘
```

### Immediate Action Items
- [ ] Register on lablab.ai hackathon
- [ ] Register project at early.surge.xyz
- [ ] Install Kraken CLI (`curl --proto '=https' --tlsv1.2 -LsSf https://github.com/krakenfx/kraken-cli/releases/latest/download/kraken-cli-installer.sh | sh`)
- [ ] Read ERC-8004 EIP spec & developer tutorial
- [ ] Set up project scaffolding
- [ ] Begin building Strategy Engine with backtesting

### Open Questions for Allan
1. Do you have an Ethereum wallet / can you create one for Base network interactions?
2. Do you have a Kraken account (needed for Kraken track)?
3. Any preference on programming language? (Python recommended for rapid development + backtesting libraries)
4. Should we post build progress on Twitter/X for the Social Engagement Score?

---

*Next session: Project scaffolding and initial implementation.*

---

## Session 2: Core Build (Mar 31, 2026 09:09 EAT)

### Open Questions Resolved
- ✅ **Wallet**: Base-compatible via MetaMask — `0x0f38EC46e5eb7A57cF5371cb259546DE0F896c0A`
- ✅ **Kraken CLI**: Installed at `~/.cargo/bin/kraken` — verified live (status "online", BTC ticker ~$67,450)
- ✅ **Python**: Confirmed, venv set up with all dependencies
- ✅ **PRISM API key**: Configured in `.env`
- ✅ **Twitter**: Yes, will build in public for Social Engagement Score

### Implementation Completed

**Strategy Engine** (all tested, live-verified):
- `indicators.py` — RSI, MACD, Bollinger Bands, ADX, ATR, VWAP, volatility
- `regime.py` — ADX/EMA regime detection (trending up/down, sideways)
- `momentum.py` — MACD crossover strategy with ATR-based stops
- `mean_reversion.py` — Bollinger + RSI with squeeze detection
- `ensemble.py` — regime-adaptive switcher with audit trail

**Risk Management** (`risk/manager.py`):
- Position sizing: 5% max per trade
- Stop-loss: ATR-based (per-strategy)
- Max drawdown: 10% → trading halt
- Daily loss limit: 3% → day halt
- Anti-whipsaw: 60s min between trades
- Compliance report generator for ERC-8004

**Market Data** (`data/market.py`):
- Auto-detects Kraken CLI in `~/.cargo/bin/`
- Falls back to yfinance for backtesting
- PRISM API integration for canonical asset resolution

**ERC-8004 On-Chain Integration**:
- `contracts/SentinelAgent.sol` — interacts with Identity/Reputation/Validation registries
- `agent/chain/identity.py` — Agent Card metadata, artifact hashing, registration
- Simulation mode operational; live chain mode ready for Base Sepolia deployment
- Each iteration submits risk_check artifact; trades submit trade_intent artifacts

**Main Agent** (`agent/main.py`):
- Full orchestration: data → strategy → risk → ERC-8004 → output
- CLI with `--once`, `--source`, `--symbols`, `--capital` flags
- Shutdown generates compliance report + audit trail JSON

**Dashboard** (`dashboard/`):
- Premium dark UI (HTML/CSS/JS)
- Equity chart, regime indicator, live signals, risk guardrails
- ERC-8004 status panel with wallet, identity, reputation, artifacts
- Responsive layout

### Live Test Results (Kraken CLI data source)
```
ERC-8004: Agent registered (simulated) ID=1
Kraken CLI: available (bin=~/.cargo/bin/kraken)
BTCUSD: sideways (ADX=15.9, conf=0.60) → mean_reversion → HOLD @ $67,383
ETHUSD: sideways (ADX=15.3, conf=0.64) → mean_reversion → HOLD @ $2,056
Risk: $10,000 equity, 0.0% drawdown, status=normal
ERC-8004: 1 risk_check artifact submitted (hash=0x331249ff...)
```

### Infrastructure
- Git repo initialized (`main` branch, first commit)
- `.env` with secrets (gitignored)
- `.gitignore` configured

### Next Steps
- [ ] Backtesting framework with historical data
- [ ] Deploy Solidity contracts to Base Sepolia testnet
- [ ] Connect dashboard to live agent via WebSocket/SSE
- [ ] Register on lablab.ai and early.surge.xyz
- [ ] First Twitter post (#BuildInPublic)
- [ ] Video demo for submission

### Twitter Post Draft
> 🤖 Day 1 building "Sentinel" for the @lababorai AI Trading Agents hackathon
> 
> A regime-adaptive trading agent that detects whether markets are trending or ranging and switches strategies accordingly. All decisions verified on-chain via ERC-8004.
> 
> Kraken CLI → ADX regime detection → MACD/Bollinger ensemble → risk guardrails → on-chain validation artifacts
> 
> Built: strategy engine, risk manager, Solidity contracts, live dashboard
> 
> Solo builder, 12 days to go 🏗️ #AI #DeFi #ERC8004 #BuildInPublic

---

*Next session: Backtesting + Base testnet deployment.*
