"""
纯 Python 技术指标实现

与 Backtrader 内置指标算法完全一致，可通过逐K线对比验证。

Backtrader 关键算法细节：
- EMA: α = 2/(period+1), seed = SMA(前period个值)
- ATR: TrueRange + Wilder's Smoothing (α = 1/period)
- ADX: Wilder's Smoothing 平滑 +DM/-DM/TR → DI → DX → ADX
- Donchian: Highest(high[-1], period), Lowest(low[-1], period)  # 不含当前K线
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple


# ============================================================
# EMA (Exponential Moving Average)
# ============================================================


def ema(series: np.ndarray, period: int) -> np.ndarray:
    """
    指数移动平均线 — 与 Backtrader bt.indicators.EMA 算法一致

    算法:
      1. 前 period 个值中，前 period-1 个输出 NaN
      2. 第 period 个输出 = SMA(前 period 个值) 作为 seed
      3. 之后: EMA_t = α × price_t + (1 - α) × EMA_{t-1}
         其中 α = 2 / (period + 1)

    Args:
        series: 价格序列 (1D numpy array)
        period: EMA 周期

    Returns:
        EMA 序列，前 period-1 个值为 NaN
    """
    n = len(series)
    result = np.full(n, np.nan)

    if n < period:
        return result

    alpha = 2.0 / (period + 1)

    # Seed: SMA of first `period` values
    result[period - 1] = np.mean(series[:period])

    # Recursive EMA
    for i in range(period, n):
        result[i] = alpha * series[i] + (1 - alpha) * result[i - 1]

    return result


# ============================================================
# Wilder's Smoothing (用于 ATR 和 ADX)
# ============================================================


def _wilders_smooth(series: np.ndarray, period: int) -> np.ndarray:
    """
    Wilder's Smoothing — 与 Backtrader SmoothedMovingAverage 一致

    算法:
      1. Seed = SMA(前 period 个有效值)
      2. 之后: SM_t = (SM_{t-1} × (period - 1) + value_t) / period
         等价于 EMA with α = 1/period

    Args:
        series: 输入序列 (可含 NaN 前缀)
        period: 平滑周期

    Returns:
        平滑后的序列
    """
    n = len(series)
    result = np.full(n, np.nan)

    # 找到第一个非 NaN 的位置
    first_valid = 0
    for i in range(n):
        if not np.isnan(series[i]):
            first_valid = i
            break

    if first_valid + period > n:
        return result

    # Seed = SMA of first period valid values
    seed_end = first_valid + period
    result[seed_end - 1] = np.mean(series[first_valid:seed_end])

    # Wilder's recursive smoothing
    for i in range(seed_end, n):
        result[i] = (result[i - 1] * (period - 1) + series[i]) / period

    return result


# ============================================================
# ATR (Average True Range)
# ============================================================


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """
    真实波幅 (True Range)

    TR = max(H - L, |H - prevClose|, |L - prevClose|)
    第一根K线的 TR = NaN (没有前一根收盘价，与 Backtrader 一致)

    Args:
        high: 最高价序列
        low: 最低价序列
        close: 收盘价序列

    Returns:
        True Range 序列，第一个值为 NaN
    """
    n = len(high)
    tr = np.full(n, np.nan)

    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
        period: int = 14) -> np.ndarray:
    """
    平均真实波幅 — 与 Backtrader bt.indicators.ATR 算法一致

    ATR = Wilder's Smoothing(True Range, period)

    Args:
        high: 最高价序列
        low: 最低价序列
        close: 收盘价序列
        period: ATR 周期 (默认 14)

    Returns:
        ATR 序列
    """
    tr = true_range(high, low, close)
    return _wilders_smooth(tr, period)


# ============================================================
# ADX (Average Directional Index)
# ============================================================


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray,
        period: int = 14) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    ADX + Plus DI + Minus DI — 与 Backtrader DirectionalMovementIndex 算法一致

    算法:
      1. +DM = max(H_t - H_{t-1}, 0) if > max(L_{t-1} - L_t, 0), else 0
      2. -DM = max(L_{t-1} - L_t, 0) if > max(H_t - H_{t-1}, 0), else 0
      3. Smooth +DM, -DM, TR with Wilder's method (period)
      4. +DI = 100 × smooth(+DM) / smooth(TR)
      5. -DI = 100 × smooth(-DM) / smooth(TR)
      6. DX = 100 × |+DI - -DI| / (+DI + -DI)
      7. ADX = Wilder's Smoothing(DX, period)

    Args:
        high: 最高价序列
        low: 最低价序列
        close: 收盘价序列
        period: ADX 周期 (默认 14)

    Returns:
        (adx_values, plus_di, minus_di) 三个 numpy 数组
    """
    n = len(high)

    # Step 1-2: Calculate +DM and -DM
    # 注意: bar[0] 没有前一根K线，+DM/-DM 为 NaN (与 Backtrader 一致)
    plus_dm = np.full(n, np.nan)
    minus_dm = np.full(n, np.nan)

    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]

        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        else:
            plus_dm[i] = 0.0

        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move
        else:
            minus_dm[i] = 0.0

    # Step 3: Wilder's smoothing of +DM, -DM, TR
    tr = true_range(high, low, close)
    smooth_plus_dm = _wilders_smooth(plus_dm, period)
    smooth_minus_dm = _wilders_smooth(minus_dm, period)
    smooth_tr = _wilders_smooth(tr, period)

    # Step 4-5: +DI and -DI
    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)

    for i in range(n):
        if not np.isnan(smooth_tr[i]) and smooth_tr[i] != 0:
            plus_di[i] = 100.0 * smooth_plus_dm[i] / smooth_tr[i]
            minus_di[i] = 100.0 * smooth_minus_dm[i] / smooth_tr[i]

    # Step 6: DX
    dx = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(plus_di[i]) and not np.isnan(minus_di[i]):
            di_sum = plus_di[i] + minus_di[i]
            if di_sum != 0:
                dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / di_sum

    # Step 7: ADX = Wilder's smoothing of DX
    adx_values = _wilders_smooth(dx, period)

    return adx_values, plus_di, minus_di


# ============================================================
# Donchian Channel
# ============================================================


def donchian(high: np.ndarray, low: np.ndarray,
             period: int = 20) -> Tuple[np.ndarray, np.ndarray]:
    """
    Donchian 通道 — 与 Backtrader DonchianRangeDetector 算法一致

    重要: 使用前一根K线及之前的数据 (不含当前K线)
      up_line = Highest(high[-1], period)
      down_line = Lowest(low[-1], period)

    Args:
        high: 最高价序列
        low: 最低价序列
        period: 回看周期 (默认 20)

    Returns:
        (up_line, down_line) — 两个 numpy 数组
    """
    n = len(high)
    up_line = np.full(n, np.nan)
    down_line = np.full(n, np.nan)

    # 需要至少 period+1 根K线（period根历史 + 当前1根）
    for i in range(period, n):
        # 从 i-period 到 i-1（不含 i，即不含当前K线）
        up_line[i] = np.max(high[i - period:i])
        down_line[i] = np.min(low[i - period:i])

    return up_line, down_line


# ============================================================
# 一次性计算所有指标
# ============================================================


def calculate_all(candles_df: pd.DataFrame, config: dict = None) -> Dict[str, np.ndarray]:
    """
    一次性计算所有策略所需指标

    Args:
        candles_df: K线数据 DataFrame，需包含 columns: open, high, low, close
        config: 可选配置 dict，包含各指标周期参数
                默认: ema50_period=50, ema200_period=200, adx_period=14,
                      atr_period=14, donchian_period=20

    Returns:
        dict: {
            'ema50': np.ndarray,
            'ema200': np.ndarray,
            'adx': np.ndarray,
            'plus_di': np.ndarray,
            'minus_di': np.ndarray,
            'atr': np.ndarray,
            'up_line': np.ndarray,
            'down_line': np.ndarray,
        }
    """
    if config is None:
        config = {}

    ema50_period = config.get('ema50_period', 50)
    ema200_period = config.get('ema200_period', 200)
    adx_period = config.get('adx_period', 14)
    atr_period = config.get('atr_period', 14)
    donchian_period = config.get('donchian_period', 20)

    h = candles_df['high'].values.astype(float)
    l = candles_df['low'].values.astype(float)
    c = candles_df['close'].values.astype(float)

    ema50_vals = ema(c, ema50_period)
    ema200_vals = ema(c, ema200_period)
    adx_vals, plus_di_vals, minus_di_vals = adx(h, l, c, adx_period)
    atr_vals = atr(h, l, c, atr_period)
    up_vals, down_vals = donchian(h, l, donchian_period)

    return {
        'ema50': ema50_vals,
        'ema200': ema200_vals,
        'adx': adx_vals,
        'plus_di': plus_di_vals,
        'minus_di': minus_di_vals,
        'atr': atr_vals,
        'up_line': up_vals,
        'down_line': down_vals,
    }
