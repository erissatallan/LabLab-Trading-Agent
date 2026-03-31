"""
Risk manager for the Sentinel trading agent.

Enforces position sizing, stop-losses, drawdown limits, and daily loss caps.
All decisions are logged for ERC-8004 compliance & validation artifacts.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from agent.strategy.momentum import TradeSignal, Signal

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents an open position."""
    symbol: str
    side: str             # "long" or "short"
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    entry_time: str
    strategy: str
    unrealized_pnl: float = 0.0

    @property
    def notional_value(self) -> float:
        return self.entry_price * self.quantity


@dataclass
class RiskMetrics:
    """Current risk state of the portfolio."""
    total_equity: float
    peak_equity: float
    current_drawdown: float    # as a fraction (0.05 = 5%)
    daily_pnl: float
    open_positions: int
    total_exposure: float      # sum of notional values
    risk_status: str           # "normal", "caution", "halted"


class RiskManager:
    """
    Portfolio-level risk management.

    Rules:
    - Max position size: 5% of equity per trade
    - Stop-loss: enforced per trade (from strategy)
    - Max drawdown: 10% from peak → halt all trading
    - Daily loss limit: 3% → halt for the day
    - Max concurrent positions: 5
    - Min time between trades: 60 seconds (anti-whipsaw)
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        max_position_pct: float = 0.05,
        max_drawdown_pct: float = 0.10,
        daily_loss_limit_pct: float = 0.03,
        max_positions: int = 5,
        min_trade_interval_seconds: int = 60,
    ):
        self.initial_capital = initial_capital
        self.equity = initial_capital
        self.peak_equity = initial_capital
        self.max_position_pct = max_position_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.max_positions = max_positions
        self.min_trade_interval = timedelta(seconds=min_trade_interval_seconds)

        self.positions: dict[str, Position] = {}
        self.closed_trades: list[dict] = []
        self.last_trade_time: Optional[datetime] = None
        self.daily_pnl = 0.0
        self.daily_reset_date = datetime.utcnow().date()
        self.is_halted = False
        self.halt_reason = ""

    def validate_trade(self, signal: TradeSignal, symbol: str) -> tuple[bool, str, float]:
        """
        Pre-trade validation. Returns (approved, reason, position_size).

        Checks:
        1. Not halted
        2. Position limit not exceeded
        3. Drawdown within limits
        4. Daily loss within limits
        5. Trade interval respected
        6. Position size within limits
        """
        # Reset daily PnL if new day
        today = datetime.utcnow().date()
        if today != self.daily_reset_date:
            self.daily_pnl = 0.0
            self.daily_reset_date = today
            # Unhalt if it was a daily halt
            if self.halt_reason == "daily_loss_limit":
                self.is_halted = False
                self.halt_reason = ""

        # Check 1: Is trading halted?
        if self.is_halted:
            return False, f"Trading halted: {self.halt_reason}", 0.0

        # Check 2: Signal is actionable
        if signal.signal == Signal.HOLD:
            return False, "Signal is HOLD", 0.0

        # Check 3: Position limit
        if len(self.positions) >= self.max_positions:
            return False, f"Max positions ({self.max_positions}) reached", 0.0

        # Check 4: Already have a position in this symbol
        if symbol in self.positions:
            return False, f"Already have position in {symbol}", 0.0

        # Check 5: Drawdown check
        current_drawdown = self._calculate_drawdown()
        if current_drawdown >= self.max_drawdown_pct:
            self.is_halted = True
            self.halt_reason = "max_drawdown"
            return False, f"Max drawdown ({current_drawdown:.1%}) exceeded limit ({self.max_drawdown_pct:.1%})", 0.0

        # Check 6: Daily loss limit
        daily_loss_pct = abs(self.daily_pnl) / self.equity if self.daily_pnl < 0 else 0
        if daily_loss_pct >= self.daily_loss_limit_pct:
            self.is_halted = True
            self.halt_reason = "daily_loss_limit"
            return False, f"Daily loss ({daily_loss_pct:.1%}) exceeded limit ({self.daily_loss_limit_pct:.1%})", 0.0

        # Check 7: Minimum trade interval
        if self.last_trade_time:
            elapsed = datetime.utcnow() - self.last_trade_time
            if elapsed < self.min_trade_interval:
                remaining = (self.min_trade_interval - elapsed).total_seconds()
                return False, f"Min trade interval: {remaining:.0f}s remaining", 0.0

        # Calculate position size
        max_notional = self.equity * self.max_position_pct
        position_size = max_notional / signal.entry_price

        logger.info(
            f"Trade APPROVED: {signal.signal.value} {symbol} | "
            f"Size={position_size:.6f} ({max_notional:.2f} notional) | "
            f"Drawdown={current_drawdown:.1%} | Daily PnL={self.daily_pnl:.2f}"
        )

        return True, "Approved", position_size

    def open_position(self, signal: TradeSignal, symbol: str, quantity: float):
        """Record a new open position."""
        side = "long" if signal.signal == Signal.BUY else "short"
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=signal.entry_price,
            quantity=quantity,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            entry_time=datetime.utcnow().isoformat(),
            strategy=signal.strategy,
        )
        self.positions[symbol] = position
        self.last_trade_time = datetime.utcnow()
        logger.info(f"Opened {side} position: {symbol} @ {signal.entry_price:.2f} x {quantity:.6f}")

    def close_position(self, symbol: str, exit_price: float, reason: str = "signal"):
        """Close a position and record the trade."""
        if symbol not in self.positions:
            logger.warning(f"No position to close for {symbol}")
            return

        pos = self.positions.pop(symbol)

        if pos.side == "long":
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity

        self.equity += pnl
        self.daily_pnl += pnl
        self.peak_equity = max(self.peak_equity, self.equity)

        trade_record = {
            "symbol": symbol,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "quantity": pos.quantity,
            "pnl": pnl,
            "pnl_pct": pnl / (pos.entry_price * pos.quantity),
            "strategy": pos.strategy,
            "entry_time": pos.entry_time,
            "exit_time": datetime.utcnow().isoformat(),
            "reason": reason,
        }
        self.closed_trades.append(trade_record)

        logger.info(
            f"Closed {pos.side} {symbol}: entry={pos.entry_price:.2f} exit={exit_price:.2f} "
            f"PnL={pnl:.2f} ({trade_record['pnl_pct']:.2%}) reason={reason}"
        )

    def check_stops(self, symbol: str, current_price: float):
        """Check if any stops have been hit for the given symbol."""
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]

        if pos.side == "long":
            if current_price <= pos.stop_loss:
                self.close_position(symbol, current_price, reason="stop_loss")
            elif current_price >= pos.take_profit:
                self.close_position(symbol, current_price, reason="take_profit")
        else:  # short
            if current_price >= pos.stop_loss:
                self.close_position(symbol, current_price, reason="stop_loss")
            elif current_price <= pos.take_profit:
                self.close_position(symbol, current_price, reason="take_profit")

    def get_metrics(self) -> RiskMetrics:
        """Get current risk metrics."""
        drawdown = self._calculate_drawdown()

        if self.is_halted:
            status = "halted"
        elif drawdown > self.max_drawdown_pct * 0.7:
            status = "caution"
        else:
            status = "normal"

        total_exposure = sum(p.notional_value for p in self.positions.values())

        return RiskMetrics(
            total_equity=self.equity,
            peak_equity=self.peak_equity,
            current_drawdown=drawdown,
            daily_pnl=self.daily_pnl,
            open_positions=len(self.positions),
            total_exposure=total_exposure,
            risk_status=status,
        )

    def get_compliance_report(self) -> dict:
        """
        Generate compliance report for ERC-8004 validation.
        This proves the agent respects its stated risk parameters.
        """
        metrics = self.get_metrics()
        win_trades = [t for t in self.closed_trades if t["pnl"] > 0]
        loss_trades = [t for t in self.closed_trades if t["pnl"] <= 0]

        return {
            "agent": "sentinel",
            "report_time": datetime.utcnow().isoformat(),
            "risk_parameters": {
                "max_position_pct": self.max_position_pct,
                "max_drawdown_pct": self.max_drawdown_pct,
                "daily_loss_limit_pct": self.daily_loss_limit_pct,
                "max_positions": self.max_positions,
            },
            "current_state": {
                "equity": metrics.total_equity,
                "peak_equity": metrics.peak_equity,
                "drawdown": metrics.current_drawdown,
                "daily_pnl": metrics.daily_pnl,
                "status": metrics.risk_status,
                "open_positions": metrics.open_positions,
            },
            "performance": {
                "total_trades": len(self.closed_trades),
                "winning_trades": len(win_trades),
                "losing_trades": len(loss_trades),
                "win_rate": len(win_trades) / max(1, len(self.closed_trades)),
                "total_pnl": sum(t["pnl"] for t in self.closed_trades),
                "avg_win": sum(t["pnl"] for t in win_trades) / max(1, len(win_trades)),
                "avg_loss": sum(t["pnl"] for t in loss_trades) / max(1, len(loss_trades)),
            },
            "recent_trades": self.closed_trades[-10:],
        }

    def _calculate_drawdown(self) -> float:
        """Current drawdown as fraction from peak equity."""
        if self.peak_equity == 0:
            return 0.0
        return (self.peak_equity - self.equity) / self.peak_equity
