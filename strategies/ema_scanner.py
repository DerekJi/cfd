"""
EMA 扫描器 — 检测有效穿越信号与止损位计算

SRP: 本模块只负责 EMA 穿越检测与止损位计算，不涉及仓位管理或交易执行。

依赖:
  - core/indicators.py: EMA / ATR 计算
  - DataFrame 格式: columns = [datetime, open, high, low, close, volume]
"""

import numpy as np
import pandas as pd
from typing import List, Optional

from core.indicators import ema as _calc_ema

# 有效穿越阈值（相对 ATR 的倍数）
CROSSOVER_ATR_MULTIPLIER = 0.5

# 止损位计算回看的 K 线数
STOP_LOSS_LOOKBACK = 10

# 3根K线突破过滤的前向回看数量
BREAKOUT_LOOKBACK_BARS = 3


def check_ema_crossover(
    df: pd.DataFrame,
    ema_periods: List[int],
    atr_val: float,
    direction: str,
) -> bool:
    """
    检测最新 K 线是否形成有效 EMA 穿越信号。

    有效穿越判定（全部满足才返回 True）：
      1. 当前收盘价已越过所有指定 EMA（同侧）
      2. 前一根收盘价位于参考 EMA（最大周期）的反方向（确认为新鲜穿越）
      3. 当前收盘价与参考 EMA 距离 >= 0.5 × ATR（过滤噪声）

    Args:
        df: K 线数据，至少需要 max(ema_periods) + 1 根
            columns = [datetime, open, high, low, close, volume]
        ema_periods: 需要全部穿越的 EMA 周期列表，例如 [10, 20, 50]
        atr_val: 当前 ATR 值（传入已计算好的最新值）
        direction: 穿越方向，'long' 或 'short'

    Returns:
        True — 有效穿越；False — 无新鲜信号或穿越幅度不足
    """
    if direction not in ('long', 'short'):
        raise ValueError(f"direction 必须为 'long' 或 'short'，收到: {direction!r}")
    if not ema_periods:
        raise ValueError("ema_periods 不能为空")

    closes = df['close'].to_numpy(dtype=float)
    if len(closes) < 2:
        return False

    current_close = closes[-1]
    prev_close = closes[-2]

    # ── 条件 1：当前收盘价已越过所有指定 EMA ──────────────────────────
    for period in ema_periods:
        ema_vals = _calc_ema(closes, period)
        ema_current = ema_vals[-1]
        if np.isnan(ema_current):
            return False
        if direction == 'long' and current_close <= ema_current:
            return False
        if direction == 'short' and current_close >= ema_current:
            return False

    # ── 条件 2：前一根收盘价位于参考 EMA 反方向（新鲜穿越） ─────────────
    # 使用 ref_ema_prev（前一根K线时的EMA值）做比较，避免与当前价格的循环逻辑
    ref_period = max(ema_periods)
    ref_ema_vals = _calc_ema(closes, ref_period)
    ref_ema_prev = ref_ema_vals[-2] if len(ref_ema_vals) >= 2 else np.nan
    ref_ema_curr = ref_ema_vals[-1]

    if np.isnan(ref_ema_prev) or np.isnan(ref_ema_curr):
        return False

    if direction == 'long' and prev_close >= ref_ema_prev:
        return False  # 前一根已在均线上方，不是新鲜穿越
    if direction == 'short' and prev_close <= ref_ema_prev:
        return False  # 前一根已在均线下方，不是新鲜穿越

    # ── 条件 3：穿越幅度 >= 0.5 × ATR（过滤噪声） ───────────────────────
    if np.isnan(atr_val) or atr_val <= 0:
        return False

    distance = abs(current_close - ref_ema_curr)
    return distance >= CROSSOVER_ATR_MULTIPLIER * atr_val


def check_3bar_breakout(
    df: pd.DataFrame,
    direction: str,
) -> bool:
    """
    3 根 K 线高/低点突破过滤。

    做多信号：当前收盘价 > 前 3 根 K 线（不含当前）的最高价
    做空信号：当前收盘价 < 前 3 根 K 线（不含当前）的最低价

    此过滤用于排除在震荡区间内的虚假穿越，确保价格已完成有效突破。

    Args:
        df: K 线数据，至少需要 BREAKOUT_LOOKBACK_BARS + 1 根
            columns = [datetime, open, high, low, close, volume]
        direction: 'long' 或 'short'

    Returns:
        True — 通过突破过滤；False — 未突破前高/低点
    """
    if direction not in ('long', 'short'):
        raise ValueError(f"direction 必须为 'long' 或 'short'，收到: {direction!r}")

    min_bars = BREAKOUT_LOOKBACK_BARS + 1
    if len(df) < min_bars:
        return False

    current_close = df['close'].iloc[-1]
    prior_bars = df.iloc[-(BREAKOUT_LOOKBACK_BARS + 1):-1]

    if direction == 'long':
        return float(current_close) > float(prior_bars['high'].max())
    else:  # short
        return float(current_close) < float(prior_bars['low'].min())


def calculate_stop_loss(
    df: pd.DataFrame,
    direction: str,
    buffer_pips: float = 5.0,
) -> Optional[float]:
    """
    基于最近 10 根 K 线的止损位计算。

    做多：止损 = 最近 10 根 K 线最低价 - buffer_pips
    做空：止损 = 最近 10 根 K 线最高价 + buffer_pips

    Args:
        df: K 线数据，至少需要 1 根
            columns = [datetime, open, high, low, close, volume]
        direction: 'long' 或 'short'
        buffer_pips: 额外缓冲（以价格单位计，调用方负责换算 pip 值）
                     例如 EUR/USD 1 pip = 0.0001，传入 0.0005 表示 5 pips

    Returns:
        止损价格（float）；数据为空时返回 None
    """
    if direction not in ('long', 'short'):
        raise ValueError(f"direction 必须为 'long' 或 'short'，收到: {direction!r}")

    if len(df) == 0:
        return None

    lookback = min(STOP_LOSS_LOOKBACK, len(df))
    recent = df.iloc[-lookback:]

    if direction == 'long':
        return float(recent['low'].min()) - buffer_pips
    else:  # short
        return float(recent['high'].max()) + buffer_pips
