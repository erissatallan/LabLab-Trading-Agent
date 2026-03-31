"""
Market regime detection for the Sentinel trading agent.

Classifies market conditions into three regimes:
- TRENDING_UP: Strong upward trend (use momentum strategy)
- TRENDING_DOWN: Strong downward trend (use momentum strategy, short bias)
- SIDEWAYS: Range-bound market (use mean reversion strategy)

Uses ADX for trend strength and directional indicators for direction.
"""

import pandas as pd
import numpy as np
from enum import Enum
from dataclasses import dataclass
from agent.data.indicators import adx, ema, rolling_volatility, atr


class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    SIDEWAYS = "sideways"


@dataclass
class RegimeSignal:
    """Output of regime detection."""
    regime: MarketRegime
    confidence: float  # 0.0 - 1.0
    adx_value: float
    volatility: float
    trend_direction: float  # +1 to -1

    @property
    def is_trending(self) -> bool:
        return self.regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN)

    def __str__(self) -> str:
        return f"Regime: {self.regime.value} (conf={self.confidence:.2f}, ADX={self.adx_value:.1f})"


class RegimeDetector:
    """
    Detects market regime using multiple signals:
    1. ADX for trend strength (>25 = trending, <20 = sideways)
    2. EMA crossover for trend direction
    3. Rolling volatility for regime transitions
    """

    def __init__(
        self,
        adx_period: int = 14,
        adx_trending_threshold: float = 25.0,
        adx_sideways_threshold: float = 20.0,
        ema_fast: int = 20,
        ema_slow: int = 50,
        volatility_period: int = 20,
        lookback_confirmation: int = 3,
    ):
        self.adx_period = adx_period
        self.adx_trending_threshold = adx_trending_threshold
        self.adx_sideways_threshold = adx_sideways_threshold
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.volatility_period = volatility_period
        self.lookback_confirmation = lookback_confirmation

        self._prev_regime = None
        self._regime_count = 0  # how many candles we've been in current regime

    def detect(self, df: pd.DataFrame) -> RegimeSignal:
        """
        Detect the current market regime from OHLCV data.
        
        Args:
            df: DataFrame with 'high', 'low', 'close' columns (minimum 50+ rows).
        
        Returns:
            RegimeSignal with regime classification and metadata.
        """
        if len(df) < self.ema_slow + self.adx_period:
            # Not enough data — default to sideways (conservative)
            return RegimeSignal(
                regime=MarketRegime.SIDEWAYS,
                confidence=0.0,
                adx_value=0.0,
                volatility=0.0,
                trend_direction=0.0,
            )

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # 1. ADX for trend strength
        adx_values = adx(high, low, close, self.adx_period)
        current_adx = adx_values.iloc[-1]

        # 2. EMA crossover for direction
        ema_fast_vals = ema(close, self.ema_fast)
        ema_slow_vals = ema(close, self.ema_slow)
        ema_diff = (ema_fast_vals - ema_slow_vals) / ema_slow_vals  # normalized
        trend_direction = float(np.clip(ema_diff.iloc[-1] * 100, -1, 1))

        # 3. Volatility context
        vol = rolling_volatility(close, self.volatility_period)
        current_vol = vol.iloc[-1] if not pd.isna(vol.iloc[-1]) else 0.0

        # Classification logic
        if current_adx >= self.adx_trending_threshold:
            if trend_direction > 0:
                regime = MarketRegime.TRENDING_UP
            else:
                regime = MarketRegime.TRENDING_DOWN
            # Confidence scales with ADX strength above threshold
            confidence = min(1.0, (current_adx - self.adx_sideways_threshold) / 30)
        elif current_adx <= self.adx_sideways_threshold:
            regime = MarketRegime.SIDEWAYS
            confidence = min(1.0, (self.adx_trending_threshold - current_adx) / 15)
        else:
            # In the buffer zone between thresholds — use previous regime with lower confidence
            regime = self._prev_regime or MarketRegime.SIDEWAYS
            confidence = 0.3

        # Regime persistence: require confirmation before switching
        if regime != self._prev_regime:
            self._regime_count = 1
            if self._regime_count < self.lookback_confirmation and self._prev_regime is not None:
                # Not enough confirmation — stick with previous
                regime = self._prev_regime
                confidence *= 0.5
        else:
            self._regime_count += 1

        self._prev_regime = regime

        return RegimeSignal(
            regime=regime,
            confidence=confidence,
            adx_value=float(current_adx) if not pd.isna(current_adx) else 0.0,
            volatility=float(current_vol),
            trend_direction=trend_direction,
        )

    def reset(self):
        """Reset regime detection state."""
        self._prev_regime = None
        self._regime_count = 0
