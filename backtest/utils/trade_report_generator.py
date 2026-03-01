"""
开仓报告生成器

每次开仓时生成一份 Markdown 报告（含 K 线图），用于后续 AI 分析。
报告统一保存到 report_dir 目录下，文件名格式：
    {symbol}_{datetime}_{side}_{trade_id:04d}.md
    {symbol}_{datetime}_{side}_{trade_id:04d}.png
"""

from __future__ import annotations
import os
import textwrap
from datetime import datetime
from typing import Sequence

import matplotlib
matplotlib.use('Agg')  # 无头模式，不弹窗
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
import numpy as np


# ── 统一止盈策略说明 (写死，所有报告共用) ─────────────────────────
_TAKE_PROFIT_POLICY = textwrap.dedent("""\
    **阶段一 — 保本止损**
    浮盈达到 1×ATR 后，将止损移动到入场价 ± 0.1×ATR（多/空），
    锁定保本，消除亏损风险。

    **阶段二 — 动态追踪止损**
    保本后启动追踪：
    - 多头：SL = max(EMA20 − 0.5×ATR,  close − trailingDist)
    - 空头：SL = min(EMA20 + 0.5×ATR,  close + trailingDist)

    trailingDist 固定为开仓时的初始止损距离，只升不降，随价格移动。
    没有固定止盈位，由止损追踪自然退出。
""")


def generate_entry_report(
    *,
    report_dir: str,
    symbol: str,
    timeframe: str,
    trade_id: int,
    side: str,               # 'long' | 'short'
    dt: datetime,            # 信号 K 线时间
    entry_price: float,
    stop_loss: float,
    atr: float,
    account_balance: float,
    reason: str,
    # --- K 线数据 (200 根，含当前 bar，时间顺序从旧到新) ---
    bar_datetimes: Sequence[datetime],
    bar_opens: Sequence[float],
    bar_highs: Sequence[float],
    bar_lows: Sequence[float],
    bar_closes: Sequence[float],
    bar_volumes: Sequence[float],
    # --- EMA 数据 (与 bar 等长) ---
    ema_fast: Sequence[float],
    ema_slow: Sequence[float],
    ema_base: Sequence[float],
    ema_fast_len: int = 5,
    ema_slow_len: int = 20,
    ema_base_len: int = 200,
) -> str:
    """
    生成开仓报告，返回报告文件路径。

    报告内容：
      1. 品种 / 周期 / 资金
      2. 开仓理由
      3. 入场 / 止损 / ATR / 当前 OHLCV
      4. 止盈策略（统一说明）
      5. 内嵌 K 线图
    """
    os.makedirs(report_dir, exist_ok=True)

    tag = dt.strftime('%Y%m%d_%H%M%S')
    base_name = f"{symbol}_{tag}_{side}_{trade_id:04d}"
    png_path = os.path.join(report_dir, base_name + '.png')
    md_path  = os.path.join(report_dir, base_name + '.md')

    # ── 1. 画 K 线图 ─────────────────────────────────────────────
    _draw_chart(
        png_path=png_path,
        symbol=symbol,
        dt=dt,
        side=side,
        entry_price=entry_price,
        stop_loss=stop_loss,
        bar_datetimes=bar_datetimes,
        bar_opens=bar_opens,
        bar_highs=bar_highs,
        bar_lows=bar_lows,
        bar_closes=bar_closes,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        ema_base=ema_base,
        ema_fast_len=ema_fast_len,
        ema_slow_len=ema_slow_len,
        ema_base_len=ema_base_len,
    )

    # ── 2. 当前 K 线数据 ────────────────────────────────────────
    cur_o = bar_opens[-1]
    cur_h = bar_highs[-1]
    cur_l = bar_lows[-1]
    cur_c = bar_closes[-1]
    cur_v = bar_volumes[-1]
    trailing_dist = abs(entry_price - stop_loss)
    risk_reward_note = "无固定 TP，由追踪止损自然出场"
    dir_label = "多 (LONG)" if side == 'long' else "空 (SHORT)"
    sl_distance = abs(entry_price - stop_loss)

    # ── 3. 写 Markdown ───────────────────────────────────────────
    relative_png = os.path.basename(png_path)  # 同目录下引用

    md_content = f"""\
# 开仓报告 #{trade_id:04d}

| 字段 | 值 |
|------|-----|
| 品种 | `{symbol}` |
| 周期 | {timeframe} |
| 方向 | {dir_label} |
| 信号时间 | {dt.strftime('%Y-%m-%d %H:%M UTC')} |
| 当前账户资金 | ${account_balance:,.2f} |

---

## 开仓理由

{reason}

---

## 入场参数

| 字段 | 值 |
|------|-----|
| 入场价 | `{entry_price:.5f}` |
| 止损位 | `{stop_loss:.5f}` |
| 止损距离 | `{sl_distance:.5f}` ({sl_distance/atr:.2f}×ATR) |
| 当前 ATR ({ema_fast_len}p) | `{atr:.5f}` |
| **当前 K 线** | |
| Open  | `{cur_o:.5f}` |
| High  | `{cur_h:.5f}` |
| Low   | `{cur_l:.5f}` |
| Close | `{cur_c:.5f}` |
| Volume | `{cur_v:.0f}` |

---

## 止盈策略

{_TAKE_PROFIT_POLICY}

---

## K 线图（含当前 K 线在内的 200 根，5 分钟周期）

![K线图]({relative_png})

> EMA{ema_fast_len}（蓝）、EMA{ema_slow_len}（橙）、EMA{ema_base_len}（紫）
> 绿色水平线 = 入场价，红色水平线 = 止损位
"""

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    return md_path


# ─────────────────────────────────────────────────────────────────
# 内部函数：画 K 线图
# ─────────────────────────────────────────────────────────────────

def _draw_chart(
    *,
    png_path: str,
    symbol: str,
    dt: datetime,
    side: str,
    entry_price: float,
    stop_loss: float,
    bar_datetimes,
    bar_opens,
    bar_highs,
    bar_lows,
    bar_closes,
    ema_fast,
    ema_slow,
    ema_base,
    ema_fast_len: int,
    ema_slow_len: int,
    ema_base_len: int,
):
    n = len(bar_datetimes)
    x = np.arange(n)

    fig, (ax_price, ax_vol_dummy) = plt.subplots(
        nrows=2, ncols=1,
        figsize=(16, 9),
        gridspec_kw={'height_ratios': [4, 1]},
        facecolor='#1e1e2e',
    )
    # 隐藏成交量子图（暂时用空白分隔），K线主图用大块空间
    ax_vol_dummy.set_visible(False)

    ax = ax_price
    ax.set_facecolor('#1e1e2e')
    ax.tick_params(colors='#cdd6f4')
    for spine in ax.spines.values():
        spine.set_edgecolor('#45475a')

    # ── 画蜡烛 ────────────────────────────────────────────────────
    candle_w = 0.6
    for i in range(n):
        o, h, l, c = float(bar_opens[i]), float(bar_highs[i]), float(bar_lows[i]), float(bar_closes[i])
        color = '#a6e3a1' if c >= o else '#f38ba8'  # Catppuccin green/red
        # body
        body_bot = min(o, c)
        body_h   = max(abs(c - o), 1e-10)
        rect = mpatches.Rectangle(
            (i - candle_w / 2, body_bot), candle_w, body_h,
            facecolor=color, edgecolor=color, zorder=3,
        )
        ax.add_patch(rect)
        # wick
        ax.plot([i, i], [l, body_bot], color=color, linewidth=0.8, zorder=2)
        ax.plot([i, i], [body_bot + body_h, h], color=color, linewidth=0.8, zorder=2)

    # ── EMA 线 ───────────────────────────────────────────────────
    def _safe_series(arr):
        a = np.array([float(v) for v in arr], dtype=float)
        a[a == 0.0] = np.nan
        return a

    ax.plot(x, _safe_series(ema_fast), color='#89b4fa', linewidth=1.2,
            label=f'EMA{ema_fast_len}', zorder=4)
    ax.plot(x, _safe_series(ema_slow), color='#fab387', linewidth=1.2,
            label=f'EMA{ema_slow_len}', zorder=4)
    ax.plot(x, _safe_series(ema_base), color='#cba6f7', linewidth=1.2,
            label=f'EMA{ema_base_len}', zorder=4)

    # ── 入场 / 止损 水平线 ────────────────────────────────────────
    ax.axhline(entry_price, color='#a6e3a1', linewidth=1.0, linestyle='--',
               label=f'Entry {entry_price:.5f}', zorder=5)
    ax.axhline(stop_loss,   color='#f38ba8', linewidth=1.0, linestyle='--',
               label=f'SL {stop_loss:.5f}', zorder=5)

    # ── 最后一根 K 线（信号 bar）标记 ───────────────────────────
    arrow_dir = 1 if side == 'long' else -1
    arrow_color = '#a6e3a1' if side == 'long' else '#f38ba8'
    ax.annotate(
        '▲ LONG' if side == 'long' else '▼ SHORT',
        xy=(n - 1, entry_price),
        xytext=(n - 1, entry_price - arrow_dir * (float(bar_highs[-1]) - float(bar_lows[-1])) * 2),
        color=arrow_color, fontsize=9, fontweight='bold',
        ha='center',
        arrowprops=dict(arrowstyle='->', color=arrow_color, lw=1.2),
        zorder=6,
    )

    # ── X 轴：每 20 根显示一个时间标签 ────────────────────────────
    step = max(1, n // 10)
    tick_idx  = list(range(0, n, step))
    tick_lbls = [bar_datetimes[i].strftime('%m-%d %H:%M') for i in tick_idx]
    ax.set_xticks(tick_idx)
    ax.set_xticklabels(tick_lbls, rotation=30, ha='right', fontsize=7, color='#cdd6f4')

    ax.set_xlim(-1, n)
    vals = [float(v) for v in list(bar_lows) + list(bar_highs)]
    pad = (max(vals) - min(vals)) * 0.05
    ax.set_ylim(min(vals) - pad, max(vals) + pad)

    ax.yaxis.tick_right()
    ax.yaxis.set_label_position('right')
    ax.set_ylabel('Price', color='#cdd6f4', fontsize=9)

    ax.grid(axis='y', color='#45475a', linewidth=0.5, linestyle=':')
    ax.legend(loc='upper left', fontsize=8, facecolor='#313244',
              edgecolor='#45475a', labelcolor='#cdd6f4')

    dir_str = 'LONG' if side == 'long' else 'SHORT'
    ax.set_title(
        f"{symbol} · 5M · {dir_str} · {dt.strftime('%Y-%m-%d %H:%M UTC')}",
        color='#cdd6f4', fontsize=11, pad=10,
    )

    fig.tight_layout()
    fig.savefig(png_path, dpi=120, bbox_inches='tight', facecolor='#1e1e2e')
    plt.close(fig)
