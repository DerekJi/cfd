"""
StateStorage 抽象基类

定义 FSM 状态 / 持仓 / 日内盈亏 / 交易记录 的存取接口。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class StateStorage(ABC):
    """
    状态存储抽象基类

    数据组织:
      - FSM 状态: profile + symbol → FSM snapshot dict
      - 持仓信息: profile + symbol → position dict
      - 日内盈亏: profile → daily PnL dict
      - 交易记录: 追加写入

    实现:
      - AzureTableStorage: Azure Table Storage (生产 + Azurite 本地)
      - LocalJsonStorage:  本地 JSON 文件 (调试用)
    """

    # ---- FSM 状态 ----

    @abstractmethod
    def save_fsm_state(self, profile: str, symbol: str, state: Dict[str, Any]) -> None:
        """保存 FSM 状态快照"""
        ...

    @abstractmethod
    def load_fsm_state(self, profile: str, symbol: str) -> Optional[Dict[str, Any]]:
        """加载 FSM 状态快照，不存在返回 None"""
        ...

    # ---- 持仓信息 ----

    @abstractmethod
    def save_position(self, profile: str, symbol: str, position: Dict[str, Any]) -> None:
        """保存持仓信息"""
        ...

    @abstractmethod
    def load_position(self, profile: str, symbol: str) -> Optional[Dict[str, Any]]:
        """加载持仓信息"""
        ...

    @abstractmethod
    def delete_position(self, profile: str, symbol: str) -> None:
        """删除持仓信息 (平仓后)"""
        ...

    # ---- 日内盈亏 ----

    @abstractmethod
    def save_daily_pnl(self, profile: str, data: Dict[str, Any]) -> None:
        """保存日内盈亏"""
        ...

    @abstractmethod
    def load_daily_pnl(self, profile: str) -> Optional[Dict[str, Any]]:
        """加载日内盈亏"""
        ...

    # ---- 交易记录 ----

    @abstractmethod
    def append_trade_record(self, profile: str, record: Dict[str, Any]) -> None:
        """追加交易记录"""
        ...

    @abstractmethod
    def get_trade_records(
        self, profile: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取最近的交易记录"""
        ...
