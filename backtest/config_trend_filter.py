"""
趋势过滤策略配置文件
"""

import os
from dataclasses import dataclass, field

# backtest/ 目录的绝对路径，确保无论从哪个目录运行都能找到数据文件
_BACKTEST_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class TrendFilterConfig:
    """趋势过滤策略配置"""
    
    # Donchian通道参数
    up_period: int = 20
    down_period: int = 20
    
    # EMA参数
    ema50_period: int = 50
    ema200_period: int = 200
    
    # ADX参数
    adx_period: int = 14
    adx_threshold: float = 35.0  # ADX阈值（经过优化：GBPUSD最优配置）
    
    # ATR参数
    atr_period: int = 14
    
    # 状态机参数
    analysis_bars: int = 5
    pullback_wait_bars: int = 20
    
    # 风险管理
    risk_percent: float = 1.0  # 每笔交易风险百分比
    min_lot: float = 0.01
    max_lot: float = 10.0
    max_cash_ratio: float = 0.95
    
    # 回测参数
    initial_cash: float = 10000.0
    commission: float = 0.0  # 佣金（每笔交易）
    
    # 数据参数（默认使用 backtest/data/ 下的文件，支持绝对路径覆盖）
    data_path: str = field(default_factory=lambda: os.path.join(_BACKTEST_DIR, "data", "GBP_USD_M5.csv"))
    
    # 调试
    debug: bool = True


def get_default_config() -> TrendFilterConfig:
    """获取默认配置"""
    return TrendFilterConfig()
