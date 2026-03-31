"""
Momentum strategy for the Sentinel trading agent.

Used when the regime detector identifies a trending market.
Core signals: MACD crossovers with trend confirmation from EMAs.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from enum import Enum
from agent.data.indicators import macd, ema, rsi, atr


class Signal(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class TradeSignal:
    """Output signal from a strategy."""
    signal: Signal
    confidence: float   # 0.0 - 1.0
    strategy: str
    entry_price: float
    stop_loss: float
    take_profit: float
    reasoning: str

    def __str__(self) -> str:
        return f"[{self.strategy}] {self.signal.value.upper()} @ {self.entry_price:.2f} (conf={self.confidence:.2f})"


class MomentumStrategy:
    """
    MACD-based momentum strategy.

    Entry rules:
    - BUY: MACD line crosses above signal line AND price above EMA-50
    - SELL: MACD line crosses below signal line AND price below EMA-50

    Exit rules:
    - Trailing stop based on ATR
    - Take profit at 2:1 reward/risk ratio
    - MACD histogram reversal

    Risk management:
    - Stop-loss at 1.5x ATR below entry
    - Position sized by ATR-based volatility
    """

    def __init__(
        self,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        ema_trend: int = 50,
        atr_period: int = 14,
        atr_stop_multiplier: float = 1.5,
        rr_ratio: float = 2.0,
    ):
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.ema_trend = ema_trend
        self.atr_period = atr_period
        self.atr_stop_multiplier = atr_stop_multiplier
        self.rr_ratio = rr_ratio

    def generate_signal(self, df: pd.DataFrame) -> TradeSignal:
        """
        Generate a trading signal from OHLCV data.

        Args:
            df: DataFrame with 'open', 'high', 'low', 'close', 'volume' columns.

        Returns:
            TradeSignal with direction, confidence, stop-loss, and take-profit levels.
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]
        current_price = float(close.iloc[-1])

        # Calculate indicators
        macd_line, signal_line, histogram = macd(
            close, self.macd_fast, self.macd_slow, self.macd_signal
        )
        ema_trend = ema(close, self.ema_trend)
        atr_val = atr(high, low, close, self.atr_period)
        rsi_val = rsi(close)

        current_macd = float(macd_line.iloc[-1])
        prev_macd = float(macd_line.iloc[-2])
        current_signal = float(signal_line.iloc[-1])
        prev_signal = float(signal_line.iloc[-2])
        current_hist = float(histogram.iloc[-1])
        prev_hist = float(histogram.iloc[-2])
        current_ema = float(ema_trend.iloc[-1])
        current_atr = float(atr_val.iloc[-1])
        current_rsi = float(rsi_val.iloc[-1])

        # Detect MACD crossover
        bullish_cross = prev_macd <= prev_signal and current_macd > current_signal
        bearish_cross = prev_macd >= prev_signal and current_macd < current_signal

        # Histogram momentum
        hist_rising = current_hist > prev_hist
        hist_falling = current_hist < prev_hist

        # Trend alignment
        above_ema = current_price > current_ema
        below_ema = current_price < current_ema

        # Generate signal
        if bullish_cross and above_ema:
            # Strong buy: MACD cross + trend alignment
            stop_loss = current_price - (self.atr_stop_multiplier * current_atr)
            risk = current_price - stop_loss
            take_profit = current_price + (risk * self.rr_ratio)

            confidence = 0.7
            if hist_rising:
                confidence += 0.1
            if current_rsi < 65:  # Not yet overbought
                confidence += 0.1
            if current_price > current_ema * 1.01:  # Solid above EMA
                confidence += 0.1

            return TradeSignal(
                signal=Signal.BUY,
                confidence=min(1.0, confidence),
                strategy="momentum",
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning=f"MACD bullish cross (MACD={current_macd:.4f} > Signal={current_signal:.4f}), "
                         f"price above EMA-{self.ema_trend} ({current_ema:.2f}), RSI={current_rsi:.1f}",
            )

        elif bearish_cross and below_ema:
            # Strong sell: MACD cross + trend alignment
            stop_loss = current_price + (self.atr_stop_multiplier * current_atr)
            risk = stop_loss - current_price
            take_profit = current_price - (risk * self.rr_ratio)

            confidence = 0.7
            if hist_falling:
                confidence += 0.1
            if current_rsi > 35:  # Not yet oversold
                confidence += 0.1
            if current_price < current_ema * 0.99:
                confidence += 0.1

            return TradeSignal(
                signal=Signal.SELL,
                confidence=min(1.0, confidence),
                strategy="momentum",
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning=f"MACD bearish cross (MACD={current_macd:.4f} < Signal={current_signal:.4f}), "
                         f"price below EMA-{self.ema_trend} ({current_ema:.2f}), RSI={current_rsi:.1f}",
            )

        else:
            # No clear signal
            return TradeSignal(
                signal=Signal.HOLD,
                confidence=0.0,
                strategy="momentum",
                entry_price=current_price,
                stop_loss=0.0,
                take_profit=0.0,
                reasoning=f"No MACD crossover or trend misalignment. "
                         f"MACD={current_macd:.4f}, Signal={current_signal:.4f}, "
                         f"EMA-{self.ema_trend}={current_ema:.2f}, RSI={current_rsi:.1f}",
            )
