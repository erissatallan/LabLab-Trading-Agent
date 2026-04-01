"""
Sentinel — Main agent entry point.

Orchestrates: data → strategy → risk → EIP-712 trade intent → execution → checkpoint.

ERC-8004 flow per iteration:
  1. Fetch OHLCV data
  2. Detect regime + generate signal
  3. For non-HOLD signals: sign TradeIntent → submit to RiskRouter (on-chain gate)
  4. If RiskRouter approves: execute via Kraken (or paper trade)
  5. Record signed EIP-712 checkpoint for every decision (checkpoints.jsonl + ValidationRegistry)
"""

import logging
import time
import json
import sys
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from agent.data.market import MarketDataProvider
from agent.strategy.ensemble import EnsembleStrategy
from agent.strategy.momentum import Signal
from agent.risk.manager import RiskManager
from agent.chain.identity import ERC8004Integration

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sentinel")


class SentinelAgent:
    """
    The Sentinel autonomous trading agent.

    Loop:
    1. Fetch market data
    2. Detect regime + generate signal
    3. Sign TradeIntent with EIP-712 → submit to RiskRouter (on-chain approval gate)
    4. If approved: execute trade
    5. Record signed checkpoint → checkpoints.jsonl + ValidationRegistry
    """

    def __init__(
        self,
        symbols: list[str] = None,
        initial_capital: float = 10000.0,
        interval_minutes: int = 60,
        loop_sleep_seconds: int = 60,
        data_source: str = "auto",
    ):
        self.symbols = symbols or ["BTCUSD", "ETHUSD"]
        self.interval = interval_minutes
        self.loop_sleep = loop_sleep_seconds

        logger.info("=" * 60)
        logger.info("SENTINEL — Initialising")
        logger.info("=" * 60)

        self.data_provider = MarketDataProvider(source=data_source)
        self.strategy = EnsembleStrategy(min_confidence=0.5)
        self.risk_manager = RiskManager(initial_capital=initial_capital)

        # ERC-8004 — full live integration
        # Reads agentId from agent-id.json, connects to Base Sepolia
        self.chain = ERC8004Integration()

        self.is_running = False
        self.iteration = 0

        chain_status = self.chain.get_status()
        logger.info(
            f"Sentinel ready | Symbols: {self.symbols} | Capital: ${initial_capital:,.2f} | "
            f"Agent ID: {chain_status['agentId']} | Chain: {chain_status['chain']} | "
            f"Signing: {'EIP-712 ✓' if chain_status['signingEnabled'] else 'unsigned'}"
        )

        if not chain_status["registered"]:
            logger.warning("⚠️  Agent not registered on-chain! Run: python scripts/register_agent.py")

    def run_once(self) -> dict:
        """
        Single iteration of the trading loop.
        Returns a summary dict of decisions, trades, and chain status.
        """
        self.iteration += 1
        summary = {
            "iteration": self.iteration,
            "timestamp": datetime.utcnow().isoformat(),
            "signals": [],
            "trades": [],
            "checkpoints": [],
            "risk_metrics": None,
            "erc8004": None,
        }

        for symbol in self.symbols:
            try:
                # ── Step 1: Fetch data ────────────────────────────────────
                df = self.data_provider.get_ohlcv(
                    symbol=symbol,
                    interval=self.interval,
                    count=200,
                )

                if df is None or len(df) < 60:
                    logger.warning(f"Insufficient data for {symbol}: {len(df) if df is not None else 0} candles")
                    continue

                current_price = float(df["close"].iloc[-1])

                # ── Step 2: Check stops on open positions ─────────────────
                self.risk_manager.check_stops(symbol, current_price)

                # ── Step 3: Regime detection + signal generation ──────────
                regime_signal, trade_signal = self.strategy.analyze(df)

                signal_record = {
                    "symbol": symbol,
                    "regime": regime_signal.regime.value,
                    "signal": trade_signal.signal.value,
                    "confidence": trade_signal.confidence,
                    "strategy": trade_signal.strategy,
                    "price": current_price,
                    "stop_loss": getattr(trade_signal, "stop_loss", 0),
                    "take_profit": getattr(trade_signal, "take_profit", 0),
                    "reasoning": trade_signal.reasoning,
                }
                summary["signals"].append(signal_record)

                # ── Step 4: ERC-8004 Trade Intent + Execution ─────────────
                if trade_signal.signal != Signal.HOLD:
                    # Risk sizing
                    approved_local, reason_local, size = self.risk_manager.validate_trade(
                        trade_signal, symbol
                    )

                    if not approved_local:
                        logger.info(f"[risk] {symbol} blocked by local risk: {reason_local}")
                        # Still record checkpoint for auditability
                        amount_usd = 0.0
                    else:
                        amount_usd = size * current_price

                        # ── EIP-712: Sign TradeIntent → RiskRouter ────────
                        # Map symbol to Kraken pair format
                        pair = _symbol_to_pair(symbol)
                        on_chain_approved, on_chain_reason = self.chain.validate_trade_intent(
                            pair=pair,
                            action=trade_signal.signal.value,
                            amount_usd=amount_usd,
                            signal=signal_record,
                        )

                        if not on_chain_approved:
                            logger.warning(f"[chain] {symbol} blocked by RiskRouter: {on_chain_reason}")
                            approved_local = False

                    # ── Execute trade if fully approved ───────────────────
                    if approved_local:
                        self.risk_manager.open_position(trade_signal, symbol, size)
                        trade_record = {
                            "symbol": symbol,
                            "action": trade_signal.signal.value,
                            "price": current_price,
                            "size": size,
                            "amount_usd": amount_usd,
                            "stop_loss": trade_signal.stop_loss,
                            "take_profit": trade_signal.take_profit,
                            "strategy": trade_signal.strategy,
                        }
                        summary["trades"].append(trade_record)
                        logger.info(
                            f"✅ TRADE | {trade_signal.signal.value} {symbol} "
                            f"@ ${current_price:,.2f} | size={size:.6f} | ${amount_usd:.2f}"
                        )

                # ── Step 5: Record EIP-712 signed checkpoint ──────────────
                # Called for EVERY decision (BUY, SELL, HOLD) — builds audit trail
                metrics = self.risk_manager.get_metrics()
                risk_snapshot = {
                    "equity": metrics.total_equity,
                    "peak_equity": metrics.peak_equity,
                    "drawdown": metrics.current_drawdown,
                    "daily_pnl": metrics.daily_pnl,
                    "open_positions": metrics.open_positions,
                    "status": metrics.risk_status,
                }

                checkpoint_hash = self.chain.record_decision(
                    signal=signal_record,
                    reasoning=trade_signal.reasoning,
                    risk_metrics=risk_snapshot,
                    post_to_chain=(trade_signal.signal != Signal.HOLD),  # only post trades to chain
                )
                summary["checkpoints"].append({
                    "symbol": symbol,
                    "hash": checkpoint_hash,
                    "signal": trade_signal.signal.value,
                })

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}", exc_info=True)

        # ── Final risk snapshot ───────────────────────────────────────────
        metrics = self.risk_manager.get_metrics()
        summary["risk_metrics"] = {
            "equity": metrics.total_equity,
            "peak_equity": metrics.peak_equity,
            "drawdown": metrics.current_drawdown,
            "daily_pnl": metrics.daily_pnl,
            "open_positions": metrics.open_positions,
            "status": metrics.risk_status,
        }

        summary["erc8004"] = self.chain.get_status()

        logger.info(
            f"[iter {self.iteration}] "
            f"Equity=${metrics.total_equity:,.2f} | "
            f"Drawdown={metrics.current_drawdown:.1%} | "
            f"Positions={metrics.open_positions} | "
            f"Checkpoints={summary['erc8004']['checkpoints'].get('total', 0)} | "
            f"On-chain={summary['erc8004'].get('onChainAttestations', '—')}"
        )

        return summary

    def run(self):
        """Main trading loop — runs continuously until stopped."""
        self.is_running = True
        logger.info("=" * 60)
        logger.info("SENTINEL AGENT RUNNING")
        logger.info("=" * 60)

        try:
            while self.is_running:
                summary = self.run_once()
                print(json.dumps(summary, indent=2, default=str))

                if self.is_running:
                    logger.info(f"Sleeping {self.loop_sleep}s until next iteration...")
                    time.sleep(self.loop_sleep)

        except KeyboardInterrupt:
            logger.info("Sentinel stopped by user")
        finally:
            self.is_running = False
            self._shutdown()

    def _shutdown(self):
        """Clean shutdown: final compliance report."""
        logger.info("Shutting down Sentinel...")

        report = self.risk_manager.get_compliance_report()
        audit_trail = self.strategy.get_audit_trail()
        checkpoint_stats = self.chain.checkpoints.get_stats()
        integrity = self.chain.checkpoints.verify_integrity()

        final_report = {
            "shutdown_time": datetime.utcnow().isoformat(),
            "compliance_report": report,
            "audit_trail": audit_trail,
            "checkpoint_log": checkpoint_stats,
            "checkpoint_integrity": integrity,
            "chain_status": self.chain.get_status(),
        }

        report_path = f"sentinel_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w") as f:
            json.dump(final_report, f, indent=2, default=str)

        logger.info(
            f"Final report: {report_path} | "
            f"Checkpoints: {checkpoint_stats.get('total', 0)} | "
            f"Signed: {checkpoint_stats.get('signed', 0)} | "
            f"Integrity: {'✓ VALID' if integrity['valid'] else '✗ BROKEN'}"
        )

    def stop(self):
        self.is_running = False


def _symbol_to_pair(symbol: str) -> str:
    """Convert internal symbol to Kraken pair format."""
    mapping = {
        "BTCUSD": "XBTUSD",
        "ETHUSD": "ETHUSD",
        "SOLUSD": "SOLUSD",
        "AVAXUSD": "AVAXUSD",
    }
    return mapping.get(symbol.upper(), symbol)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sentinel — ERC-8004 Regime-Adaptive Trading Agent")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSD", "ETHUSD"])
    parser.add_argument("--capital", type=float, default=10000.0)
    parser.add_argument("--interval", type=int, default=60, help="Candle interval in minutes")
    parser.add_argument("--sleep", type=int, default=60,  help="Seconds between iterations")
    parser.add_argument("--source", default="auto", choices=["auto", "kraken", "yfinance"])
    parser.add_argument("--once", action="store_true", help="Single iteration then exit")
    parser.add_argument("--status", action="store_true", help="Print chain status and exit")

    args = parser.parse_args()

    if args.status:
        chain = ERC8004Integration()
        print(json.dumps(chain.get_status(), indent=2, default=str))
        return

    agent = SentinelAgent(
        symbols=args.symbols,
        initial_capital=args.capital,
        interval_minutes=args.interval,
        loop_sleep_seconds=args.sleep,
        data_source=args.source,
    )

    if args.once:
        summary = agent.run_once()
        print(json.dumps(summary, indent=2, default=str))
    else:
        agent.run()


if __name__ == "__main__":
    main()
