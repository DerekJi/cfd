"""
风控管理器 — 纯 Python 版本

职责:
1. 市场开盘时段过滤 (从 trend_filter_strategy_v1.py 提取)
2. Blue Guardian 风控限制
3. 每日 / 总回撤检查
"""

from datetime import datetime
from typing import Tuple, Optional


# ============================================================
# 市场开盘时段过滤
# ============================================================


def is_market_open_session(dt: datetime) -> Tuple[bool, Optional[str]]:
    """
    检查当前时间是否在市场开盘高波动时段（禁止交易）

    禁止交易窗口：开盘前后 15 分钟

    Args:
        dt: UTC 时间

    Returns:
        (is_blocked, session_name)
        - (True, "东京开盘") — 不允许交易
        - (False, None)      — 允许交易
    """
    hour = dt.hour
    minute = dt.minute
    time_minutes = hour * 60 + minute

    # 东京开盘: 00:00 UTC → 窗口 23:45 – 00:15
    tokyo_open = 0
    if (time_minutes >= tokyo_open - 15 and time_minutes <= tokyo_open + 15) or \
       (time_minutes >= 1440 - 15):  # 23:45–23:59 跨日
        return True, "东京开盘"

    # 悉尼开盘: 21:00 UTC → 窗口 20:45 – 21:15
    sydney_open = 21 * 60
    if time_minutes >= sydney_open - 15 and time_minutes <= sydney_open + 15:
        return True, "悉尼开盘"

    return False, None


# ============================================================
# Blue Guardian 风控限制
# ============================================================

class BlueGuardianRiskLimits:
    """
    Blue Guardian 挑战赛风控限制

    账户大小 $5,000 (最低挑战) 的限制:
      - 单笔最大亏损: $50  (1%)
      - 每日最大亏损: $150 (3%)
      - 总最大回撤:   $300 (6%)
      - 利润目标:     $400 (8%) Phase 1 / $250 (5%) Phase 2

    这些限制通过构造参数传入，可适配不同账户大小。
    """

    def __init__(self,
                 account_size: float = 5000.0,
                 max_single_loss_pct: float = 0.01,
                 max_daily_loss_pct: float = 0.03,
                 max_total_drawdown_pct: float = 0.06):
        self.account_size = account_size
        self.max_single_loss = account_size * max_single_loss_pct
        self.max_daily_loss = account_size * max_daily_loss_pct
        self.max_total_drawdown = account_size * max_total_drawdown_pct

        # 运行时追踪
        self.daily_pnl = 0.0
        self.daily_date: Optional[str] = None
        self.peak_equity = account_size
        self.current_equity = account_size

    def update_equity(self, equity: float) -> None:
        """更新当前权益"""
        self.current_equity = equity
        if equity > self.peak_equity:
            self.peak_equity = equity

    def reset_daily(self, date_str: str) -> None:
        """重置每日统计 (每天第一根K线调用)"""
        if self.daily_date != date_str:
            self.daily_pnl = 0.0
            self.daily_date = date_str

    def record_trade_pnl(self, pnl: float) -> None:
        """记录一笔交易的盈亏"""
        self.daily_pnl += pnl

    def can_open_trade(self, estimated_max_loss: float) -> Tuple[bool, Optional[str]]:
        """
        检查是否允许开仓

        Args:
            estimated_max_loss: 估计的最大亏损 (正数)

        Returns:
            (allowed, reason)
        """
        # 单笔限制
        if estimated_max_loss > self.max_single_loss:
            return False, f"单笔亏损 ${estimated_max_loss:.2f} > 限制 ${self.max_single_loss:.2f}"

        # 每日限制: 检查已用 + 新开仓风险是否超限
        if abs(self.daily_pnl) + estimated_max_loss > self.max_daily_loss:
            return False, f"每日亏损将达 ${abs(self.daily_pnl) + estimated_max_loss:.2f} > 限制 ${self.max_daily_loss:.2f}"

        # 总回撤
        current_drawdown = self.peak_equity - self.current_equity
        if current_drawdown + estimated_max_loss > self.max_total_drawdown:
            return False, f"总回撤将达 ${current_drawdown + estimated_max_loss:.2f} > 限制 ${self.max_total_drawdown:.2f}"

        return True, None

    def get_status(self) -> dict:
        """获取当前风控状态"""
        return {
            'equity': self.current_equity,
            'peak_equity': self.peak_equity,
            'drawdown': self.peak_equity - self.current_equity,
            'drawdown_pct': (self.peak_equity - self.current_equity) / self.peak_equity * 100,
            'daily_pnl': self.daily_pnl,
            'daily_limit_remaining': self.max_daily_loss - abs(self.daily_pnl),
            'total_drawdown_remaining': self.max_total_drawdown - (self.peak_equity - self.current_equity),
        }
