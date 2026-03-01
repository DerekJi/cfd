"""
StateStorage 抽象基类

定义 FSM 状态 / 持仓 / 日内盈亏 / 交易记录 / 半自动策略状态 的存取接口。
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

    # ---- 半自动策略：观察列表 ----

    @abstractmethod
    def save_watchlist(self, profile: str, items: List[Dict[str, Any]]) -> None:
        """保存观察列表（全量覆盖写）"""
        ...

    @abstractmethod
    def load_watchlist(self, profile: str) -> List[Dict[str, Any]]:
        """加载观察列表，不存在返回空列表"""
        ...

    # ---- 半自动策略：趋势激活池 ----

    @abstractmethod
    def save_trend_pool(self, profile: str, items: List[Dict[str, Any]]) -> None:
        """保存趋势激活池（全量覆盖写）"""
        ...

    @abstractmethod
    def load_trend_pool(self, profile: str) -> List[Dict[str, Any]]:
        """加载趋势激活池，不存在返回空列表"""
        ...

    # ---- 半自动策略：待确认信号 ----

    @abstractmethod
    def save_pending_signal(
        self, profile: str, symbol: str, signal: Dict[str, Any]
    ) -> None:
        """保存单品种待确认信号"""
        ...

    @abstractmethod
    def load_pending_signal(
        self, profile: str, symbol: str
    ) -> Optional[Dict[str, Any]]:
        """加载单品种待确认信号，不存在返回 None"""
        ...

    @abstractmethod
    def delete_pending_signal(self, profile: str, symbol: str) -> None:
        """删除单品种待确认信号（开仓或取消后调用）"""
        ...

    # ---- 半自动策略：免打扰状态 ----

    @abstractmethod
    def save_symbol_dnd(self, profile: str, symbol: str, expiry_iso: str) -> None:
        """设置单品种免打扰到期时间（ISO 8601 UTC 字符串）"""
        ...

    @abstractmethod
    def load_symbol_dnd(self, profile: str, symbol: str) -> Optional[str]:
        """读取单品种免打扰到期时间，不存在或已过期则返回 None"""
        ...

    @abstractmethod
    def clear_symbol_dnd(self, profile: str, symbol: str) -> None:
        """清除单品种免打扰"""
        ...

    @abstractmethod
    def save_global_dnd(self, profile: str, slots: List[Dict[str, Any]]) -> None:
        """保存全局免打扰时段列表（全量覆盖写，元素为 DndTimeSlot.to_dict()）"""
        ...

    @abstractmethod
    def load_global_dnd(self, profile: str) -> List[Dict[str, Any]]:
        """加载全局免打扰时段列表，不存在返回空列表"""
        ...
