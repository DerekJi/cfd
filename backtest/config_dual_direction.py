"""\n双向趋势追踪策略配置文件\n"""

import os
from dataclasses import dataclass, field

_BACKTEST_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class DualDirectionConfig:
    """双向趋势追踪策略配置"""

    # EMA 参数
    ema_fast_len: int = 5
    ema_slow_len: int = 20
    ema_base_len: int = 200

    # ATR 参数
    atr_len: int = 14

    # ADX 趋势强度过滤（默认启用，0 = 关闭）
    adx_len: int = 0
    adx_threshold: float = 20.0   # ADX >= 20 才允许入场

    # 成交量过滤（默认关闭，与 Pine Script 默认一致）
    check_volume: bool = False
    vol_sma_len: int = 10
    vol_mult: float = 1.1

    # 分形回看（与 Pine Script 一致，左右各 2 根）
    fractal_period: int = 2

    # 止损参数
    sl_initial_atr_mult: float = 0.5    # 初始止损偏移 = 0.5×ATR
    sl_breakeven_atr_mult: float = 0.1  # 保本偏移 = 0.1×ATR
    sl_trailing_atr_mult: float = 0.5   # 追踪偏移 = 0.5×ATR
    min_trailing_dist_atr: float = 1.5  # 最小追踪距离 = 1.5×ATR（过滤质量低的信号）
    cooldown_bars: int = 24             # 平仓后冷却期(K线数)，防止震荡市谴反复入场（24丽=2小时）

    # 风险管理
    risk_percent: float = 1.0
    initial_cash: float = 100000.0      # 测试资金 10万
    min_lot: float = 0.01
    max_lot: float = 10.0

    # 数据路径（默认 GBP_USD）
    data_path: str = field(
        default_factory=lambda: os.path.join(_BACKTEST_DIR, "data", "GBP_USD_M5.csv")
    )

    # 调试
    debug: bool = True

    # 开仓报告
    enable_trade_report: bool = False
    report_dir: str = ''      # 为空时由回测脚本自动推断
    max_reports: int = 0      # 0 = 不限制；>0 = 最多生成 N 份报告


def get_default_config() -> DualDirectionConfig:
    return DualDirectionConfig()
