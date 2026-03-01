"""
半自动 EMA 趋势跟踪策略 — 状态数据模型

定义策略运行所需的全部持久化状态：
  - WatchlistItem  : 观察列表条目（品种 + 可选震荡区间）
  - TrendPoolItem  : 趋势激活池条目（品种 + 方向 + 绑定 H1 均线周期）
  - PendingSignal  : 待确认信号（开仓前等待用户 /open 确认）
  - DndTimeSlot    : 全局免打扰时段（UTC HH:MM 起止）

每个模型提供 to_dict() / from_dict() 以统一序列化格式，
供 StateStorage 存取时使用，storage 层无需感知具体类型。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class WatchlistItem:
    """
    观察列表条目

    Attributes:
        symbol     : 交易品种，如 "EUR_USD"
        range_high : 震荡区间上限（设置后 H1 扫描将跳过区间内信号）
        range_low  : 震荡区间下限
    """

    symbol: str
    range_high: Optional[float] = None
    range_low: Optional[float] = None

    def __post_init__(self) -> None:
        both_set = self.range_high is not None and self.range_low is not None
        neither_set = self.range_high is None and self.range_low is None
        if not (both_set or neither_set):
            raise ValueError(
                "range_high 和 range_low 必须同时设置或同时为 None，"
                f"收到: range_high={self.range_high!r}, range_low={self.range_low!r}"
            )
        if both_set and self.range_high <= self.range_low:  # type: ignore[operator]
            raise ValueError(
                f"range_high({self.range_high}) 必须大于 range_low({self.range_low})"
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WatchlistItem":
        return cls(
            symbol=d["symbol"],
            range_high=d.get("range_high"),
            range_low=d.get("range_low"),
        )


@dataclass
class TrendPoolItem:
    """
    趋势激活池条目

    Attributes:
        symbol        : 交易品种
        direction     : 趋势方向，"long" 或 "short"
        h1_ema_period : 触发穿越时绑定的 H1 均线周期（如 21、55）
        added_at      : 加入时间（ISO 8601 UTC 字符串）
    """

    symbol: str
    direction: str          # "long" | "short"
    h1_ema_period: int
    added_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if self.direction not in ("long", "short"):
            raise ValueError(f"direction 必须为 'long' 或 'short'，收到: {self.direction!r}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TrendPoolItem":
        return cls(
            symbol=d["symbol"],
            direction=d["direction"],
            h1_ema_period=int(d["h1_ema_period"]),
            added_at=d.get("added_at", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class PendingSignal:
    """
    待确认信号

    5M 扫描触发后保存到此处，等待用户通过 /open 指令确认开仓。
    用户确认后由引擎读取并执行市价单，随后删除此记录。

    Attributes:
        symbol        : 交易品种
        direction     : 方向，"long" 或 "short"
        entry_price   : 建议入场价（触发时的市价快照，最终以实时报价为准）
        stop_loss     : 止损价（基于 10 根 K 线极值 + buffer）
        position_size : 建议手数（单位：units）
        created_at    : 信号生成时间（ISO 8601 UTC 字符串）
    """

    symbol: str
    direction: str          # "long" | "short"
    entry_price: float
    stop_loss: float
    position_size: int
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if self.direction not in ("long", "short"):
            raise ValueError(f"direction 必须为 'long' 或 'short'，收到: {self.direction!r}")
        if self.position_size <= 0:
            raise ValueError(f"position_size 必须为正整数，收到: {self.position_size}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PendingSignal":
        return cls(
            symbol=d["symbol"],
            direction=d["direction"],
            entry_price=float(d["entry_price"]),
            stop_loss=float(d["stop_loss"]),
            position_size=int(d["position_size"]),
            created_at=d.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class DndTimeSlot:
    """
    全局免打扰时段（UTC）

    在此时段内，5M 扫描不向用户推送任何信号（静默运行）。

    Attributes:
        start : 开始时间，格式 "HH:MM"（UTC）
        end   : 结束时间，格式 "HH:MM"（UTC）

    示例：DndTimeSlot(start="21:00", end="22:00") 表示每天 21:00–22:00 UTC 静默
    """

    start: str   # "HH:MM"
    end: str     # "HH:MM"

    def __post_init__(self) -> None:
        for val, name in ((self.start, "start"), (self.end, "end")):
            parts = val.split(":")
            if (
                len(parts) != 2
                or not all(p.isdigit() for p in parts)
                or len(parts[0]) != 2
                or len(parts[1]) != 2
            ):
                raise ValueError(f"DndTimeSlot.{name} 格式应为 'HH:MM'（两位数），收到: {val!r}")

    def is_active(self, utc_now: Optional[datetime] = None) -> bool:
        """
        判断当前 UTC 时间是否处于此免打扰时段内。

        支持跨凌晨时段，如 start="22:00", end="06:00"。

        Args:
            utc_now: 要判断的 UTC 时间（默认 datetime.now(timezone.utc)）

        Returns:
            True — 当前时间在免打扰时段内
        """
        if utc_now is None:
            utc_now = datetime.now(timezone.utc)
        current_hm = utc_now.hour * 60 + utc_now.minute
        sh, sm = (int(x) for x in self.start.split(":"))
        eh, em = (int(x) for x in self.end.split(":"))
        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        if start_min < end_min:
            # 同日时段，如 12:00–13:00
            return start_min <= current_hm < end_min
        elif start_min > end_min:
            # 跨凌晨时段，如 22:00–06:00
            return current_hm >= start_min or current_hm < end_min
        else:
            # start == end：空时段，始终 False
            return False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DndTimeSlot":
        return cls(start=d["start"], end=d["end"])
