"""
Ensemble strategy — the regime-adaptive switcher.

This is the brain of Sentinel. It:
1. Detects the current market regime
2. Routes to the appropriate sub-strategy
3. Manages transitions to avoid whipsaw
4. Aggregates confidence across signals
"""

import pandas as pd
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

from agent.strategy.regime import RegimeDetector, RegimeSignal, MarketRegime
from agent.strategy.momentum import MomentumStrategy, TradeSignal, Signal
from agent.strategy.mean_reversion import MeanReversionStrategy

logger = logging.getLogger(__name__)


@dataclass
class EnsembleState:
    """Track the ensemble strategy's internal state."""
    current_regime: Optional[MarketRegime] = None
    active_strategy: Optional[str] = None
    last_signal: Optional[TradeSignal] = None
    regime_history: list = field(default_factory=list)
    signal_history: list = field(default_factory=list)
    total_signals: int = 0
    total_trades: int = 0


class EnsembleStrategy:
    """
    Regime-adaptive ensemble strategy.

    In TRENDING markets → uses MomentumStrategy (MACD crossovers)
    In SIDEWAYS markets → uses MeanReversionStrategy (Bollinger + RSI)

    Features:
    - Smooth regime transitions (doesn't flip on every candle)
    - Minimum confidence threshold before generating actionable signals
    - Full audit trail for ERC-8004 validation artifacts
    """

    def __init__(
        self,
        min_confidence: float = 0.5,
        regime_detector: Optional[RegimeDetector] = None,
        momentum: Optional[MomentumStrategy] = None,
        mean_reversion: Optional[MeanReversionStrategy] = None,
    ):
        self.min_confidence = min_confidence
        self.regime_detector = regime_detector or RegimeDetector()
        self.momentum = momentum or MomentumStrategy()
        self.mean_reversion = mean_reversion or MeanReversionStrategy()
        self.state = EnsembleState()

    def analyze(self, df: pd.DataFrame) -> tuple[RegimeSignal, TradeSignal]:
        """
        Full analysis pipeline: regime detection → strategy signal.

        Args:
            df: OHLCV DataFrame (minimum ~60 rows for stable indicators).

        Returns:
            Tuple of (RegimeSignal, TradeSignal)
        """
        # Step 1: Detect regime
        regime_signal = self.regime_detector.detect(df)
        self.state.current_regime = regime_signal.regime

        # Step 2: Route to appropriate strategy
        if regime_signal.is_trending:
            self.state.active_strategy = "momentum"
            trade_signal = self.momentum.generate_signal(df)
        else:
            self.state.active_strategy = "mean_reversion"
            trade_signal = self.mean_reversion.generate_signal(df)

        # Step 3: Adjust confidence based on regime confidence
        adjusted_confidence = trade_signal.confidence * regime_signal.confidence
        trade_signal = TradeSignal(
            signal=trade_signal.signal if adjusted_confidence >= self.min_confidence else Signal.HOLD,
            confidence=adjusted_confidence,
            strategy=trade_signal.strategy,
            entry_price=trade_signal.entry_price,
            stop_loss=trade_signal.stop_loss,
            take_profit=trade_signal.take_profit,
            reasoning=f"[{regime_signal}] {trade_signal.reasoning}" +
                      (f" | Below min confidence ({adjusted_confidence:.2f} < {self.min_confidence})"
                       if adjusted_confidence < self.min_confidence and trade_signal.signal != Signal.HOLD
                       else ""),
        )

        # Step 4: Update state
        self.state.last_signal = trade_signal
        self.state.total_signals += 1
        if trade_signal.signal != Signal.HOLD:
            self.state.total_trades += 1

        self.state.regime_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "regime": regime_signal.regime.value,
            "adx": regime_signal.adx_value,
            "confidence": regime_signal.confidence,
        })

        self.state.signal_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "signal": trade_signal.signal.value,
            "strategy": trade_signal.strategy,
            "confidence": trade_signal.confidence,
            "price": trade_signal.entry_price,
            "reasoning": trade_signal.reasoning,
        })

        # Keep history bounded
        if len(self.state.regime_history) > 1000:
            self.state.regime_history = self.state.regime_history[-500:]
        if len(self.state.signal_history) > 1000:
            self.state.signal_history = self.state.signal_history[-500:]

        logger.info(f"{regime_signal} → {trade_signal}")

        return regime_signal, trade_signal

    def get_audit_trail(self) -> dict:
        """
        Get full audit trail for ERC-8004 validation artifacts.
        This is what gets submitted on-chain.
        """
        return {
            "agent": "sentinel",
            "version": "0.1.0",
            "current_regime": self.state.current_regime.value if self.state.current_regime else None,
            "active_strategy": self.state.active_strategy,
            "total_signals": self.state.total_signals,
            "total_trades": self.state.total_trades,
            "recent_regimes": self.state.regime_history[-10:],
            "recent_signals": self.state.signal_history[-10:],
        }

    def reset(self):
        """Reset all state."""
        self.regime_detector.reset()
        self.state = EnsembleState()
