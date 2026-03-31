"""
Market data fetching for the Sentinel trading agent.

Supports multiple data sources:
1. Kraken CLI (via subprocess) — primary for hackathon
2. yfinance — fallback for backtesting
3. PRISM API — canonical asset resolution
"""

import pandas as pd
import numpy as np
import subprocess
import json
import logging
import os
import requests
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

PRISM_API_BASE = "https://api.prismapi.ai/v1"
PRISM_API_KEY = os.getenv("PRISM_API_KEY", "")


class MarketDataProvider:
    """
    Fetch OHLCV market data from multiple sources.
    Primary: Kraken CLI (if installed). Fallback: yfinance.
    Also integrates PRISM API for canonical asset resolution.
    """

    KRAKEN_PATHS = [
        "kraken",
        os.path.expanduser("~/.cargo/bin/kraken"),
        "/usr/local/bin/kraken",
    ]

    def __init__(self, source: str = "auto"):
        self.source = source
        self._kraken_available: Optional[bool] = None
        self._kraken_bin: Optional[str] = None

    def _find_kraken(self) -> Optional[str]:
        for path in self.KRAKEN_PATHS:
            try:
                result = subprocess.run(
                    [path, "status", "-o", "json"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None

    def is_kraken_available(self) -> bool:
        if self._kraken_available is not None:
            return self._kraken_available
        self._kraken_bin = self._find_kraken()
        self._kraken_available = self._kraken_bin is not None
        logger.info(f"Kraken CLI available: {self._kraken_available} (bin={self._kraken_bin})")
        return self._kraken_available

    def get_ohlcv(self, symbol: str, interval: int = 60, count: int = 200,
                  source: Optional[str] = None) -> pd.DataFrame:
        use_source = source or self.source
        if use_source == "auto":
            use_source = "kraken" if self.is_kraken_available() else "yfinance"

        if use_source == "kraken":
            return self._fetch_kraken(symbol, interval, count)
        elif use_source == "yfinance":
            return self._fetch_yfinance(symbol, interval, count)
        else:
            raise ValueError(f"Unknown data source: {use_source}")

    def get_ticker(self, symbol: str) -> dict:
        if self.source == "auto" and self.is_kraken_available():
            return self._ticker_kraken(symbol)
        return self._ticker_yfinance(symbol)

    def resolve_asset(self, query: str, context: str = "crypto") -> Optional[dict]:
        """Use PRISM API to resolve an asset identifier to canonical form."""
        if not PRISM_API_KEY:
            return None
        try:
            resp = requests.get(
                f"{PRISM_API_BASE}/resolve",
                params={"q": query, "context": context},
                headers={"Authorization": f"Bearer {PRISM_API_KEY}"},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"PRISM resolve failed ({resp.status_code})")
        except Exception as e:
            logger.warning(f"PRISM API error: {e}")
        return None

    def _fetch_kraken(self, symbol: str, interval: int, count: int) -> pd.DataFrame:
        kraken = self._kraken_bin or "kraken"
        try:
            result = subprocess.run(
                [kraken, "ohlc", symbol, "--interval", str(interval), "-o", "json"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                logger.warning(f"Kraken CLI error: {result.stderr}")
                return self._fetch_yfinance(symbol, interval, count)

            data = json.loads(result.stdout)
            if isinstance(data, dict) and "result" in data:
                for key, ohlc_data in data["result"].items():
                    if key != "last":
                        df = pd.DataFrame(
                            ohlc_data,
                            columns=["time", "open", "high", "low", "close", "vwap", "volume", "count"]
                        )
                        df["time"] = pd.to_datetime(df["time"], unit="s")
                        df = df.set_index("time")
                        for col in ["open", "high", "low", "close", "volume"]:
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                        return df[["open", "high", "low", "close", "volume"]].tail(count)
            return self._fetch_yfinance(symbol, interval, count)
        except Exception as e:
            logger.warning(f"Kraken fetch failed: {e}, falling back to yfinance")
            return self._fetch_yfinance(symbol, interval, count)

    def _fetch_yfinance(self, symbol: str, interval: int, count: int) -> pd.DataFrame:
        import yfinance as yf
        yf_map = {
            "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
            "XRPUSD": "XRP-USD", "ADAUSD": "ADA-USD", "DOTUSD": "DOT-USD",
            "AVAXUSD": "AVAX-USD", "LINKUSD": "LINK-USD", "UNIUSD": "UNI-USD",
        }
        yf_symbol = yf_map.get(symbol.upper(), f"{symbol[:3]}-{symbol[3:]}")
        interval_map = {1: "1m", 5: "5m", 15: "15m", 30: "30m", 60: "1h", 240: "4h", 1440: "1d"}
        yf_interval = interval_map.get(interval, "1h")
        period = "7d" if interval <= 60 else ("60d" if interval <= 240 else "1y")

        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period, interval=yf_interval)
        df.columns = [c.lower() for c in df.columns]
        for drop_col in ["adj close", "dividends", "stock splits"]:
            if drop_col in df.columns:
                df = df.drop(columns=[drop_col])
        return df[["open", "high", "low", "close", "volume"]].tail(count)

    def _ticker_kraken(self, symbol: str) -> dict:
        kraken = self._kraken_bin or "kraken"
        try:
            result = subprocess.run(
                [kraken, "ticker", symbol, "-o", "json"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as e:
            logger.warning(f"Kraken ticker failed: {e}")
        return self._ticker_yfinance(symbol)

    def _ticker_yfinance(self, symbol: str) -> dict:
        import yfinance as yf
        yf_map = {"BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD"}
        yf_symbol = yf_map.get(symbol.upper(), f"{symbol[:3]}-{symbol[3:]}")
        ticker = yf.Ticker(yf_symbol)
        info = ticker.fast_info
        return {
            "symbol": symbol,
            "last": float(info.last_price) if hasattr(info, 'last_price') else 0,
            "source": "yfinance",
        }
