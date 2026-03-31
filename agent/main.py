"""
Sentinel — Main agent entry point.

Orchestrates: data → strategy → risk → execution → on-chain reporting.
"""

import logging
import time
import json
import sys
from datetime import datetime
from typing import Optional

from agent.data.market import MarketDataProvider
from agent.strategy.ensemble import EnsembleStrategy
from agent.strategy.momentum import Signal
from agent.risk.manager import RiskManager
from agent.chain.identity import ERC8004Integration

# Configure logging
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
    3. Validate with risk manager
    4. Execute trade (paper or live)
    5. Log validation artifacts for ERC-8004
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

        self.data_provider = MarketDataProvider(source=data_source)
        self.strategy = EnsembleStrategy(min_confidence=0.5)
        self.risk_manager = RiskManager(initial_capital=initial_capital)
        self.chain = ERC8004Integration(simulation_mode=True)

        self.is_running = False
        self.iteration = 0

        # Register agent identity on ERC-8004
        self.chain.register_agent()

        logger.info(
            f"Sentinel initialized | Symbols: {self.symbols} | "
            f"Capital: ${initial_capital:,.2f} | Interval: {interval_minutes}m"
        )

    def run_once(self) -> dict:
        """
        Run a single iteration of the trading loop.
        Returns a summary dict of what happened.
        """
        self.iteration += 1
        summary = {
            "iteration": self.iteration,
            "timestamp": datetime.utcnow().isoformat(),
            "signals": [],
            "trades": [],
            "risk_metrics": None,
        }

        for symbol in self.symbols:
            try:
                # Step 1: Fetch data
                df = self.data_provider.get_ohlcv(
                    symbol=symbol,
                    interval=self.interval,
                    count=200,
                )

                if df is None or len(df) < 60:
                    logger.warning(f"Insufficient data for {symbol}: {len(df) if df is not None else 0} candles")
                    continue

                current_price = float(df["close"].iloc[-1])

                # Step 2: Check existing stops
                self.risk_manager.check_stops(symbol, current_price)

                # Step 3: Analyze market + generate signal
                regime_signal, trade_signal = self.strategy.analyze(df)

                signal_record = {
                    "symbol": symbol,
                    "regime": regime_signal.regime.value,
                    "signal": trade_signal.signal.value,
                    "confidence": trade_signal.confidence,
                    "strategy": trade_signal.strategy,
                    "price": current_price,
                    "reasoning": trade_signal.reasoning,
                }
                summary["signals"].append(signal_record)

                # Step 4: Risk validation + execution
                if trade_signal.signal != Signal.HOLD:
                    # Submit trade intent artifact BEFORE execution (ERC-8004)
                    self.chain.submit_trade_intent(signal_record)

                    approved, reason, size = self.risk_manager.validate_trade(trade_signal, symbol)

                    if approved:
                        self.risk_manager.open_position(trade_signal, symbol, size)
                        trade_record = {
                            "symbol": symbol,
                            "action": trade_signal.signal.value,
                            "price": current_price,
                            "size": size,
                            "stop_loss": trade_signal.stop_loss,
                            "take_profit": trade_signal.take_profit,
                            "strategy": trade_signal.strategy,
                        }
                        summary["trades"].append(trade_record)
                        logger.info(f"TRADE EXECUTED: {trade_record}")
                    else:
                        logger.info(f"Trade rejected for {symbol}: {reason}")

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}", exc_info=True)

        # Step 5: Risk metrics snapshot
        metrics = self.risk_manager.get_metrics()
        risk_snapshot = {
            "equity": metrics.total_equity,
            "peak_equity": metrics.peak_equity,
            "drawdown": metrics.current_drawdown,
            "daily_pnl": metrics.daily_pnl,
            "open_positions": metrics.open_positions,
            "status": metrics.risk_status,
        }
        summary["risk_metrics"] = risk_snapshot

        # Submit risk check artifact (ERC-8004)
        self.chain.submit_risk_check(risk_snapshot)

        # Add on-chain status to summary
        summary["erc8004"] = self.chain.get_on_chain_status()

        logger.info(
            f"Iteration {self.iteration} complete | "
            f"Equity: ${metrics.total_equity:,.2f} | "
            f"Drawdown: {metrics.current_drawdown:.1%} | "
            f"Positions: {metrics.open_positions} | "
            f"Status: {metrics.risk_status} | "
            f"Artifacts: {summary['erc8004']['total_artifacts']}"
        )

        return summary

    def run(self):
        """Main trading loop. Runs continuously until stopped."""
        self.is_running = True
        logger.info("=" * 60)
        logger.info("SENTINEL AGENT STARTED")
        logger.info("=" * 60)

        try:
            while self.is_running:
                summary = self.run_once()

                # Print summary to stdout for monitoring
                print(json.dumps(summary, indent=2, default=str))

                if self.is_running:
                    logger.info(f"Sleeping {self.loop_sleep}s until next iteration...")
                    time.sleep(self.loop_sleep)

        except KeyboardInterrupt:
            logger.info("Sentinel stopped by user (KeyboardInterrupt)")
        finally:
            self.is_running = False
            self._shutdown()

    def _shutdown(self):
        """Clean shutdown: close all positions, generate final report."""
        logger.info("Shutting down Sentinel...")

        # Generate final compliance report
        report = self.risk_manager.get_compliance_report()
        audit_trail = self.strategy.get_audit_trail()

        final_report = {
            "shutdown_time": datetime.utcnow().isoformat(),
            "compliance_report": report,
            "audit_trail": audit_trail,
        }

        # Save report to file
        report_path = f"sentinel_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w") as f:
            json.dump(final_report, f, indent=2, default=str)

        logger.info(f"Final report saved to {report_path}")
        logger.info("Sentinel shutdown complete.")

    def stop(self):
        """Gracefully stop the agent."""
        self.is_running = False


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Sentinel — Trustless Regime-Adaptive Trading Agent")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSD", "ETHUSD"],
                        help="Trading pairs to monitor")
    parser.add_argument("--capital", type=float, default=10000.0,
                        help="Initial capital (USD)")
    parser.add_argument("--interval", type=int, default=60,
                        help="Candle interval in minutes")
    parser.add_argument("--sleep", type=int, default=60,
                        help="Seconds between iterations")
    parser.add_argument("--source", default="auto",
                        choices=["auto", "kraken", "yfinance"],
                        help="Market data source")
    parser.add_argument("--once", action="store_true",
                        help="Run a single iteration and exit")

    args = parser.parse_args()

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
