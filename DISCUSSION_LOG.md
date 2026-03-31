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
