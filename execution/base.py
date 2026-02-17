"""
TradeExecutor 抽象基类

定义交易执行层的统一接口。Oanda 和 TradeLocker 各实现一套。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class OrderResult:
    """下单结果"""
    success: bool
    order_id: Optional[str] = None
    trade_id: Optional[str] = None       # 成交后的 trade/position ID
    fill_price: Optional[float] = None
    units: Optional[float] = None
    error: Optional[str] = None


@dataclass
class PositionInfo:
    """持仓信息"""
    position_id: str
    symbol: str
    side: str           # 'long' 或 'short'
    units: float        # 头寸大小 (单位数)
    entry_price: float
    unrealized_pnl: float = 0.0
    stop_loss: Optional[float] = None


@dataclass
class AccountInfo:
    """账户信息"""
    balance: float
    equity: float
    unrealized_pnl: float = 0.0
    currency: str = 'USD'
    margin_used: float = 0.0
    margin_available: float = 0.0


class TradeExecutor(ABC):
    """
    交易执行器抽象基类

    两个实现:
      - OandaExecutor:       Oanda REST v20 (模拟 + 可选实盘)
      - TradeLockerExecutor: TradeLocker SDK (Blue Guardian 实盘)

    统一接口确保 live engine 不用关心底层平台差异。
    """

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        units: float,
        stop_loss: float,
    ) -> OrderResult:
        """
        市价下单 + 服务端止损

        Args:
            symbol: 品种名 (平台格式, 如 'GBP_USD' 或 'GBPUSD')
            side: 'buy' 或 'sell'
            units: 头寸大小 (单位数, 非手数)
            stop_loss: 止损价格 (服务端止损)

        Returns:
            OrderResult
        """
        ...

    @abstractmethod
    def close_position(self, trade_id: str) -> OrderResult:
        """
        平仓

        Args:
            trade_id: 交易/持仓 ID

        Returns:
            OrderResult
        """
        ...

    @abstractmethod
    def modify_stop_loss(self, trade_id: str, new_price: float) -> bool:
        """
        修改止损价格 (移动止损)

        Args:
            trade_id: 交易/持仓 ID
            new_price: 新止损价格

        Returns:
            是否成功
        """
        ...

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """
        获取账户信息

        Returns:
            AccountInfo
        """
        ...

    @abstractmethod
    def get_positions(self) -> List[PositionInfo]:
        """
        获取当前持仓列表

        Returns:
            PositionInfo 列表
        """
        ...
