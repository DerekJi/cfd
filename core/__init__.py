"""
策略核心模块 — 纯 Python，无 Backtrader 或其他框架依赖

本模块包含：
- indicators: EMA, ADX, ATR, Donchian 纯 Python 实现
- fsm: TrendFilterStateMachine 策略状态机
- position_sizer: 仓位计算
- risk_manager: 风控（市场时段过滤 + Blue Guardian 限额检查）
- forex_utils: 货币对分类、报价转换、PnL 公式
"""

from core.indicators import ema, adx, atr, donchian, calculate_all
from core.fsm import TrendFilterStateMachine, TrendFilterState
from core.position_sizer import calculate_position_size
from core.risk_manager import is_market_open_session, BlueGuardianRiskLimits
from core.forex_utils import (
    get_pair_type,
    get_quote_usd_rate,
    get_pnl_factor,
    calculate_margin,
    normalize_symbol,
)

__all__ = [
    # indicators
    'ema', 'adx', 'atr', 'donchian', 'calculate_all',
    # fsm
    'TrendFilterStateMachine', 'TrendFilterState',
    # position_sizer
    'calculate_position_size',
    # risk_manager
    'is_market_open_session', 'BlueGuardianRiskLimits',
    # forex_utils
    'get_pair_type', 'get_quote_usd_rate', 'get_pnl_factor',
    'calculate_margin', 'normalize_symbol',
]
