"""
Mean reversion strategy for the Sentinel trading agent.

Used when the regime detector identifies a sideways/range-bound market.
Core signals: Bollinger Bands + RSI for overbought/oversold conditions.
"""

import pandas as pd
import numpy as np
from agent.data.indicators import bollinger_bands, rsi, atr, sma
from agent.strategy.momentum import TradeSignal, Signal


class MeanReversionStrategy:
    """
    Bollinger Bands + RSI mean reversion strategy.

    Entry rules:
    - BUY: Price at/below lower Bollinger Band AND RSI < 35 (oversold)
    - SELL: Price at/above upper Bollinger Band AND RSI > 65 (overbought)

    Exit rules:
    - Price crosses the middle Bollinger Band (SMA-20)
    - RSI returns to neutral zone (40-60)
    - Time-based exit: close after N candles if no exit triggered

    Risk management:
    - Stop-loss at 2x ATR beyond entry
    - Tighter stops than momentum (mean reversion has faster expected resolution)
    """

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: float = 35.0,
        rsi_overbought: float = 65.0,
        atr_period: int = 14,
        atr_stop_multiplier: float = 2.0,
        rr_ratio: float = 1.5,
    ):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.atr_period = atr_period
        self.atr_stop_multiplier = atr_stop_multiplier
        self.rr_ratio = rr_ratio

    def generate_signal(self, df: pd.DataFrame) -> TradeSignal:
        """
        Generate a mean reversion trading signal from OHLCV data.

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
        upper, middle, lower, bandwidth, pct_b = bollinger_bands(
            close, self.bb_period, self.bb_std
        )
        rsi_vals = rsi(close, self.rsi_period)
        atr_vals = atr(high, low, close, self.atr_period)

        current_upper = float(upper.iloc[-1])
        current_middle = float(middle.iloc[-1])
        current_lower = float(lower.iloc[-1])
        current_pct_b = float(pct_b.iloc[-1])
        current_rsi = float(rsi_vals.iloc[-1])
        current_atr = float(atr_vals.iloc[-1])
        current_bw = float(bandwidth.iloc[-1])

        # Check for squeeze (low bandwidth = potential breakout — avoid mean reversion)
        avg_bandwidth = float(bandwidth.rolling(50).mean().iloc[-1]) if len(bandwidth) > 50 else current_bw
        is_squeeze = current_bw < avg_bandwidth * 0.5

        if is_squeeze:
            return TradeSignal(
                signal=Signal.HOLD,
                confidence=0.0,
                strategy="mean_reversion",
                entry_price=current_price,
                stop_loss=0.0,
                take_profit=0.0,
                reasoning=f"Bollinger squeeze detected (BW={current_bw:.4f} vs avg={avg_bandwidth:.4f}). "
                         f"Potential breakout — avoiding mean reversion.",
            )

        # Oversold: Buy signal
        if current_price <= current_lower and current_rsi < self.rsi_oversold:
            stop_loss = current_price - (self.atr_stop_multiplier * current_atr)
            take_profit = current_middle  # Target the middle band (mean)
            risk = current_price - stop_loss

            # Confidence based on how extreme the signal is
            confidence = 0.6
            rsi_extremity = (self.rsi_oversold - current_rsi) / self.rsi_oversold
            bb_extremity = max(0, -current_pct_b)  # How far below lower band
            confidence += rsi_extremity * 0.2
            confidence += min(bb_extremity * 0.2, 0.2)

            return TradeSignal(
                signal=Signal.BUY,
                confidence=min(1.0, confidence),
                strategy="mean_reversion",
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning=f"Oversold: Price ({current_price:.2f}) at lower BB ({current_lower:.2f}), "
                         f"RSI={current_rsi:.1f} < {self.rsi_oversold}. "
                         f"Target middle band at {current_middle:.2f}.",
            )

        # Overbought: Sell signal
        elif current_price >= current_upper and current_rsi > self.rsi_overbought:
            stop_loss = current_price + (self.atr_stop_multiplier * current_atr)
            take_profit = current_middle  # Target the middle band
            risk = stop_loss - current_price

            confidence = 0.6
            rsi_extremity = (current_rsi - self.rsi_overbought) / (100 - self.rsi_overbought)
            bb_extremity = max(0, current_pct_b - 1.0)
            confidence += rsi_extremity * 0.2
            confidence += min(bb_extremity * 0.2, 0.2)

            return TradeSignal(
                signal=Signal.SELL,
                confidence=min(1.0, confidence),
                strategy="mean_reversion",
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning=f"Overbought: Price ({current_price:.2f}) at upper BB ({current_upper:.2f}), "
                         f"RSI={current_rsi:.1f} > {self.rsi_overbought}. "
                         f"Target middle band at {current_middle:.2f}.",
            )

        else:
            return TradeSignal(
                signal=Signal.HOLD,
                confidence=0.0,
                strategy="mean_reversion",
                entry_price=current_price,
                stop_loss=0.0,
                take_profit=0.0,
                reasoning=f"No mean reversion signal. Price={current_price:.2f}, "
                         f"BB=[{current_lower:.2f}, {current_middle:.2f}, {current_upper:.2f}], "
                         f"%B={current_pct_b:.2f}, RSI={current_rsi:.1f}.",
            )
