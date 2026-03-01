"""
K 线图 + EMA 叠加图生成器

SRP: 本模块只负责将 OHLC DataFrame 渲染为 PNG 字节流，不涉及交易逻辑。

核心函数
--------
generate_ema_chart(df, ema_dict, title, ...) -> bytes
    将 OHLC K 线数据与指定的 EMA 曲线叠加，返回 PNG 格式的 bytes。

设计说明
--------
- 使用 matplotlib Agg 后端（无头模式，适合服务器环境）
- 风格沿用 backtest/utils/trade_report_generator.py 的 Catppuccin 主题
- 返回 bytes，调用方可直接通过 Telegram sendPhoto 接口发送，无需落盘
"""

from __future__ import annotations

import io
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import matplotlib
matplotlib.use('Agg')  # 无头模式，不弹窗
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ─── 中文字体自动发现（优先顺序：Windows > macOS > Linux）────────────────────
def _find_cjk_font() -> str | None:
    """返回系统中可用的 CJK 字体名称，找不到返回 None。"""
    candidates = [
        'Microsoft YaHei', 'SimHei', 'SimSun', 'STHeiti',   # Windows / macOS
        'WenQuanYi Micro Hei', 'Noto Sans CJK SC',           # Linux
        'Arial Unicode MS',
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    return None

_CJK_FONT = _find_cjk_font()
if _CJK_FONT:
    matplotlib.rcParams['font.family'] = [_CJK_FONT, 'DejaVu Sans']

# ─── 默认颜色循环（Catppuccin Mocha 调色板）───────────────────────────────
_DEFAULT_COLORS = [
    '#89b4fa',  # 蓝
    '#fab387',  # 橙
    '#cba6f7',  # 紫
    '#94e2d5',  # 青
    '#f9e2af',  # 黄
    '#a6e3a1',  # 绿
]

# EmaSpec: (values, color) 二元组，或仅 values（使用默认颜色）
EmaSpec = Union[
    Tuple[Sequence[float], str],   # (values, '#hex_color')
    Sequence[float],               # 仅 values，颜色自动分配
]


def generate_ema_chart(
    df: pd.DataFrame,
    ema_dict: Dict[str, EmaSpec],
    title: str,
    *,
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    direction: Optional[str] = None,
    current_price: Optional[float] = None,
    timeframe: str = '',
    n_candles: Optional[int] = None,
    figsize: Tuple[int, int] = (16, 9),
    dpi: int = 120,
) -> bytes:
    """
    生成 K 线图 + EMA 叠加图，返回 PNG 字节流。

    Parameters
    ----------
    df : pd.DataFrame
        K 线数据，要求列：open / high / low / close。
        索引可以是 DatetimeIndex 或含 datetime 的普通列（同时接受 'time' / 'datetime' 列名）。
    ema_dict : dict
        EMA 曲线字典，键为图例标签，值为：
          - ``(values, '#hex_color')`` 二元组
          - 仅 ``values``（自动分配颜色）
        values 长度须与 df 行数一致。
    title : str
        图表主标题。
    entry_price : float, optional
        入场价水平线（绿色虚线）。
    stop_loss : float, optional
        止损位水平线（红色虚线）。
    direction : str, optional
        信号方向 ``'long'`` 或 ``'short'``，用于在最后一根 K 线处标注箭头。
    current_price : float, optional
        当前价格水平线（白色实线），优先级低于 entry_price。
    timeframe : str, optional
        周期标注，例如 ``'H1'``、``'M5'``，显示在标题副标题中。
    n_candles : int, optional
        只显示最后 N 根 K 线；默认显示全部。
    figsize : tuple, optional
        matplotlib 图像尺寸，默认 (16, 9)。
    dpi : int, optional
        输出分辨率，默认 120。

    Returns
    -------
    bytes
        PNG 格式的图像字节流，可直接通过 Telegram sendPhoto 发送。
    """
    # ── 1. 数据准备 ───────────────────────────────────────────────────────
    df = _normalize_df(df)
    if n_candles is not None and n_candles < len(df):
        df = df.iloc[-n_candles:].reset_index(drop=True)
        ema_dict = {
            label: _slice_ema_spec(spec, -n_candles)
            for label, spec in ema_dict.items()
        }

    n = len(df)
    x = np.arange(n)

    bar_datetimes = df['_dt'].tolist()  # _normalize_df 保证此列存在
    bar_opens  = df['open'].to_numpy(dtype=float)
    bar_highs  = df['high'].to_numpy(dtype=float)
    bar_lows   = df['low'].to_numpy(dtype=float)
    bar_closes = df['close'].to_numpy(dtype=float)

    # ── 2. 创建 Figure ────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=figsize, facecolor='#1e1e2e')
    ax.set_facecolor('#1e1e2e')
    ax.tick_params(colors='#cdd6f4')
    for spine in ax.spines.values():
        spine.set_edgecolor('#45475a')

    # ── 3. 蜡烛图 ─────────────────────────────────────────────────────────
    candle_w = 0.6
    for i in range(n):
        o, h, l, c = bar_opens[i], bar_highs[i], bar_lows[i], bar_closes[i]
        color = '#a6e3a1' if c >= o else '#f38ba8'
        body_bot = min(o, c)
        body_h   = max(abs(c - o), 1e-10)
        rect = mpatches.Rectangle(
            (i - candle_w / 2, body_bot), candle_w, body_h,
            facecolor=color, edgecolor=color, zorder=3,
        )
        ax.add_patch(rect)
        ax.plot([i, i], [l, body_bot], color=color, linewidth=0.8, zorder=2)
        ax.plot([i, i], [body_bot + body_h, h], color=color, linewidth=0.8, zorder=2)

    # ── 4. EMA 曲线 ───────────────────────────────────────────────────────
    color_cycle = iter(_DEFAULT_COLORS)
    for label, spec in ema_dict.items():
        values, color = _unpack_ema_spec(spec, color_cycle)
        arr = np.array([float(v) for v in values], dtype=float)
        arr[arr == 0.0] = np.nan
        # 若 spec 提供的长度长于当前 df，取尾部对齐
        if len(arr) > n:
            arr = arr[-n:]
        ax.plot(x[:len(arr)], arr, color=color, linewidth=1.2, label=label, zorder=4)

    # ── 5. 水平标注线 ─────────────────────────────────────────────────────
    if entry_price is not None:
        ax.axhline(entry_price, color='#a6e3a1', linewidth=1.0, linestyle='--',
                   label=f'Entry {entry_price:.5f}', zorder=5)
    if stop_loss is not None:
        ax.axhline(stop_loss, color='#f38ba8', linewidth=1.0, linestyle='--',
                   label=f'SL {stop_loss:.5f}', zorder=5)
    if current_price is not None and entry_price is None:
        ax.axhline(current_price, color='#cdd6f4', linewidth=0.8, linestyle='-',
                   label=f'Now {current_price:.5f}', zorder=5)

    # ── 6. 方向箭头标注（最后一根 K 线） ──────────────────────────────────
    if direction in ('long', 'short') and entry_price is not None:
        arrow_up   = direction == 'long'
        arrow_color = '#a6e3a1' if arrow_up else '#f38ba8'
        bar_range   = float(bar_highs[-1]) - float(bar_lows[-1]) or 1e-5
        arrow_dir   = 1 if arrow_up else -1
        ax.annotate(
            '▲ LONG' if arrow_up else '▼ SHORT',
            xy=(n - 1, entry_price),
            xytext=(n - 1, entry_price - arrow_dir * bar_range * 2),
            color=arrow_color, fontsize=9, fontweight='bold', ha='center',
            arrowprops=dict(arrowstyle='->', color=arrow_color, lw=1.2),
            zorder=6,
        )

    # ── 7. X 轴时间标签 ───────────────────────────────────────────────────
    step = max(1, n // 10)
    tick_idx  = list(range(0, n, step))
    tick_lbls = [bar_datetimes[i].strftime('%m-%d %H:%M') for i in tick_idx]
    ax.set_xticks(tick_idx)
    ax.set_xticklabels(tick_lbls, rotation=30, ha='right', fontsize=7, color='#cdd6f4')

    ax.set_xlim(-1, n)
    all_prices = np.concatenate([bar_lows, bar_highs])
    pad = (all_prices.max() - all_prices.min()) * 0.05
    ax.set_ylim(all_prices.min() - pad, all_prices.max() + pad)

    ax.yaxis.tick_right()
    ax.yaxis.set_label_position('right')
    ax.set_ylabel('Price', color='#cdd6f4', fontsize=9)

    ax.grid(axis='y', color='#45475a', linewidth=0.5, linestyle=':')
    ax.legend(loc='upper left', fontsize=8, facecolor='#313244',
              edgecolor='#45475a', labelcolor='#cdd6f4')

    tf_str = f' · {timeframe}' if timeframe else ''
    ax.set_title(f"{title}{tf_str}", color='#cdd6f4', fontsize=11, pad=10)

    fig.tight_layout()

    # ── 8. 渲染为字节流 ───────────────────────────────────────────────────
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', facecolor='#1e1e2e')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    标准化 DataFrame：
    - 列名统一转小写
    - 将时间信息提取到 ``_dt`` 列（datetime 对象列表）
    - 确保 open / high / low / close 列存在
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    # 提取时间列为 _dt
    if isinstance(df.index, pd.DatetimeIndex):
        df['_dt'] = df.index.to_pydatetime().tolist()
        df = df.reset_index(drop=True)
    elif 'datetime' in df.columns:
        df['_dt'] = pd.to_datetime(df['datetime']).dt.to_pydatetime().tolist()
    elif 'time' in df.columns:
        df['_dt'] = pd.to_datetime(df['time']).dt.to_pydatetime().tolist()
    else:
        # 无时间列时用序号占位
        from datetime import datetime, timedelta
        df['_dt'] = [datetime(2000, 1, 1) + timedelta(minutes=i) for i in range(len(df))]

    for col in ('open', 'high', 'low', 'close'):
        if col not in df.columns:
            raise ValueError(f"DataFrame 缺少必要列: {col!r}")

    return df


def _slice_ema_spec(spec: EmaSpec, n: int) -> EmaSpec:
    """取 EmaSpec 的最后 n 个元素。"""
    if isinstance(spec, (list, np.ndarray, pd.Series)):
        return list(spec)[n:]
    if isinstance(spec, tuple) and len(spec) == 2:
        values, color = spec
        return (list(values)[n:], color)
    return spec


def _unpack_ema_spec(
    spec: EmaSpec,
    color_cycle,
) -> Tuple[Sequence[float], str]:
    """将 EmaSpec 解包为 (values, color)。"""
    if isinstance(spec, tuple) and len(spec) == 2 and isinstance(spec[1], str):
        return spec[0], spec[1]
    # 仅 values，从颜色循环中取下一个
    try:
        color = next(color_cycle)
    except StopIteration:
        color = '#cdd6f4'
    return spec, color
