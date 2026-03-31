"""
Technical indicator calculations for the Sentinel trading agent.
Uses pandas for vectorized computation. All functions accept a DataFrame
with at minimum: 'close' column. Some need 'high', 'low', 'volume'.
"""

import pandas as pd
import numpy as np


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index.
    Returns values 0-100. Oversold < 30, Overbought > 70.
    """
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """
    MACD (Moving Average Convergence Divergence).
    Returns: (macd_line, signal_line, histogram)
    """
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(close: pd.Series, period: int = 20, std_dev: float = 2.0):
    """
    Bollinger Bands.
    Returns: (upper_band, middle_band, lower_band, bandwidth, %b)
    """
    middle = sma(close, period)
    std = close.rolling(window=period).std()
    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)

    bandwidth = (upper - lower) / middle
    pct_b = (close - lower) / (upper - lower)

    return upper, middle, lower, bandwidth, pct_b


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Average Directional Index — measures trend strength.
    ADX > 25 = trending market, ADX < 20 = sideways/range-bound.
    """
    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = true_range(high, low, close)
    atr_val = tr.ewm(com=period - 1, min_periods=period).mean()

    plus_di = 100 * (plus_dm.ewm(com=period - 1, min_periods=period).mean() / atr_val)
    minus_di = 100 * (minus_dm.ewm(com=period - 1, min_periods=period).mean() / atr_val)

    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
    adx_val = dx.ewm(com=period - 1, min_periods=period).mean()

    return adx_val


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True Range — used by ATR and ADX."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range — volatility measure for position sizing."""
    tr = true_range(high, low, close)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Volume Weighted Average Price."""
    typical_price = (high + low + close) / 3
    cumulative_tp_vol = (typical_price * volume).cumsum()
    cumulative_vol = volume.cumsum()
    return cumulative_tp_vol / cumulative_vol


def rolling_volatility(close: pd.Series, period: int = 20) -> pd.Series:
    """Annualized rolling volatility (log returns)."""
    log_returns = np.log(close / close.shift(1))
    return log_returns.rolling(window=period).std() * np.sqrt(365)  # crypto = 365 days
