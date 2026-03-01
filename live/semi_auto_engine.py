"""
半自动 EMA 趋势跟踪引擎

SRP: 本模块只负责两级扫描逻辑和交易执行；
     命令解析由 SemiAutoBot 负责，状态读写委托给 StateStorage。

两级扫描
--------
tick_h1()  — 每小时触发，遍历 Watchlist 检测 H1 EMA 穿越
tick_5m()  — 每 5 分钟触发，遍历趋势激活池检测 5M 顺势信号

交易执行
--------
execute_open(symbol)         — 响应 /open，开市价单
execute_close_all()          — 响应 /close all
execute_move_sl(symbol, sl)  — 响应 /move
get_open_positions()         — 响应 /order list
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.indicators import ema as calc_ema, atr as calc_atr
from core.position_sizer import calculate_position_size
from data.oanda_candles import OandaDataProvider
from execution.base import TradeExecutor
from notification.telegram import TelegramNotifier
from storage.base import StateStorage
from strategies.ema_scanner import (
    check_3bar_breakout,
    check_ema_crossover,
    calculate_stop_loss,
)
from strategies.semi_auto.state import (
    DndTimeSlot,
    PendingSignal,
    TrendPoolItem,
    WatchlistItem,
)
from utils.chart_generator import generate_ema_chart

logger = logging.getLogger(__name__)

# ─── 策略常量 ────────────────────────────────────────────────────────────────
RISK_PERCENT = 0.8          # 单笔风险 %（相对账户规模）
ATR_PERIOD = 14             # ATR 周期
SL_BUFFER_PIPS = 5          # 止损缓冲 pips
CHART_CANDLES = 100         # 图表显示 K 线数

# EMA 颜色（Catppuccin Mocha，与 Phase 4 保持一致）
_EMA_COLORS = ['#89b4fa', '#fab387', '#cba6f7', '#94e2d5', '#f9e2af']

# 默认扫描周期（若 bot settings 未设置则使用这些）
DEFAULT_EMA_H1 = [21, 55, 200]
DEFAULT_EMA_5M = [10, 20, 50]


def _pip_value(symbol: str) -> float:
    """返回 1 pip 的价格单位。"""
    sym = symbol.upper().replace('_', '')
    if 'JPY' in sym:
        return 0.01
    if sym in ('XAUUSD', 'XAGUSD'):
        return 0.01
    return 0.0001


# ─────────────────────────────────────────────────────────────────────────────
# SemiAutoEngine
# ─────────────────────────────────────────────────────────────────────────────

class SemiAutoEngine:
    """
    半自动引擎

    Parameters
    ----------
    data_provider : OandaDataProvider
        行情数据来源（H1 + M5 K线）。
    executor : TradeExecutor
        交易执行器（下单、平仓、改止损）。
    storage : StateStorage
        状态存储（watchlist、trend pool、pending signal 等）。
    notifier : TelegramNotifier
        Telegram 推送（发图、发消息）。
    profile : str
        Profile 名称，用于区分存储 key。
    account_size : float
        账户规模（AUD/USD），用于仓位计算。
    ema_h1_periods : list[int], optional
        H1 扫描使用的 EMA 周期列表（可在运行时由 /set 修改）。
    ema_5m_periods : list[int], optional
        5M 扫描使用的 EMA 周期列表。
    """

    def __init__(
        self,
        *,
        data_provider: OandaDataProvider,
        executor: TradeExecutor,
        storage: StateStorage,
        notifier: TelegramNotifier,
        profile: str,
        account_size: float = 10_000.0,
        ema_h1_periods: Optional[List[int]] = None,
        ema_5m_periods: Optional[List[int]] = None,
    ):
        self._dp = data_provider
        self._executor = executor
        self._storage = storage
        self._notifier = notifier
        self._profile = profile
        self._account_size = account_size

        # 可由 /set 动态修改
        self.ema_h1_periods: List[int] = ema_h1_periods or DEFAULT_EMA_H1
        self.ema_5m_periods: List[int] = ema_5m_periods or DEFAULT_EMA_5M

    # ─────────────────────────────────────────────────────────────────────────
    # H1 扫描（每小时触发）
    # ─────────────────────────────────────────────────────────────────────────

    def tick_h1(self) -> Dict[str, Any]:
        """
        遍历 Watchlist，对每个品种执行 H1 EMA 穿越检测。

        流程:
          1. 从 storage 读取 watchlist
          2. 拉取 H1 × 200 K 线
          3. 计算最新 ATR
          4. 若价格在震荡区间内 → 跳过
          5. 多空各方向检测 EMA 穿越
          6. 穿越触发 → 生成图表 + 推送 Telegram 通知

        Returns
        -------
        dict  扫描结果摘要：{'triggered': [...], 'skipped': [...], 'errors': [...]}
        """
        watchlist = [
            WatchlistItem.from_dict(d)
            for d in self._storage.load_watchlist(self._profile)
        ]
        if not watchlist:
            logger.info("[H1 scan] watchlist empty, skip")
            return {'triggered': [], 'skipped': [], 'errors': []}

        triggered, skipped, errors = [], [], []

        for item in watchlist:
            symbol = item.symbol
            try:
                df = self._dp.get_candles(symbol, granularity='H1', count=250)
                if df.empty or len(df) < max(self.ema_h1_periods) + 5:
                    skipped.append(symbol)
                    continue

                closes = df['close'].to_numpy(dtype=float)
                highs  = df['high'].to_numpy(dtype=float)
                lows   = df['low'].to_numpy(dtype=float)

                atr_vals = calc_atr(highs, lows, closes, period=ATR_PERIOD)
                latest_atr = float(atr_vals[-1])
                if latest_atr == 0:
                    skipped.append(symbol)
                    continue

                current_price = float(closes[-1])

                # ── 震荡区间过滤 ────────────────────────────────────────
                if (
                    item.range_high is not None
                    and item.range_low is not None
                    and item.range_low < current_price < item.range_high
                ):
                    logger.debug(
                        f"[H1 scan] {symbol} price {current_price} in range "
                        f"[{item.range_low}–{item.range_high}], skip"
                    )
                    skipped.append(f"{symbol}(range)")
                    continue

                # ── 多空两个方向检测 ─────────────────────────────────────
                for direction in ('long', 'short'):
                    signal = check_ema_crossover(
                        df, self.ema_h1_periods, latest_atr, direction
                    )
                    if signal:
                        logger.info(
                            f"[H1 scan] {symbol} {direction} crossover detected"
                        )
                        self._notify_h1_signal(
                            symbol, direction, df, latest_atr
                        )
                        triggered.append(f"{symbol}:{direction}")

            except Exception as e:
                logger.error(f"[H1 scan] {symbol} error: {e}")
                errors.append(f"{symbol}: {e}")

        logger.info(
            f"[H1 scan] done. triggered={triggered}, "
            f"skipped={len(skipped)}, errors={len(errors)}"
        )
        return {'triggered': triggered, 'skipped': skipped, 'errors': errors}

    def _notify_h1_signal(
        self,
        symbol: str,
        direction: str,
        df,
        atr_val: float,
    ) -> None:
        """生成 H1 图表并推送穿越信号通知。"""
        try:
            closes = df['close'].to_numpy(dtype=float)
            highs  = df['high'].to_numpy(dtype=float)
            lows   = df['low'].to_numpy(dtype=float)

            ema_dict = {}
            for i, period in enumerate(self.ema_h1_periods):
                color = _EMA_COLORS[i % len(_EMA_COLORS)]
                ema_dict[f'EMA{period}'] = (calc_ema(closes, period), color)

            arrow = '🔺' if direction == 'long' else '🔻'
            image_bytes = generate_ema_chart(
                df=df,
                ema_dict=ema_dict,
                title=f'{symbol}',
                direction=direction,
                current_price=float(closes[-1]),
                timeframe='H1',
                n_candles=CHART_CANDLES,
            )
            caption = (
                f"{arrow} <b>H1 EMA 穿越</b>  {symbol}\n"
                f"方向: <b>{'多' if direction == 'long' else '空'}</b>\n"
                f"ATR: {atr_val:.5f}\n"
                f"收盘: {float(closes[-1]):.5f}\n\n"
                f"发送 /trend {'long' if direction == 'long' else 'short'} "
                f"{symbol} EMA周期 将其加入趋势池"
            )
            self._notifier.send_photo(image_bytes, caption=caption)
        except Exception as e:
            logger.error(f"[H1 notify] {symbol} chart/send error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 5M 扫描（每 5 分钟触发）
    # ─────────────────────────────────────────────────────────────────────────

    def tick_5m(self) -> Dict[str, Any]:
        """
        遍历趋势激活池，对每个品种执行 5M 顺势信号检测。

        流程:
          1. 全局 DND 检查（静默则直接返回）
          2. 遍历 trend pool
          3. 单品种 DND 检查
          4. 拉取 M5 × 200 + H1 × 200
          5. 检查 5M EMA 穿越（任意一条）+ 绑定 H1 EMA 穿越
          6. 3-bar breakout 过滤
          7. 计算 SL、仓位、风控校验
          8. 通过 → 保存 PendingSignal + 发图通知

        Returns
        -------
        dict  扫描结果摘要
        """
        now = datetime.now(timezone.utc)

        # ── 全局 DND ────────────────────────────────────────────────────────
        global_dnd = [
            DndTimeSlot(**d)
            for d in self._storage.load_global_dnd(self._profile)
        ]
        for slot in global_dnd:
            if slot.is_active(now):
                logger.info(
                    f"[5M scan] global DND active ({slot.start}-{slot.end} UTC), skip"
                )
                return {
                    'triggered': [], 'skipped': ['global_dnd'], 'errors': []
                }

        trend_pool = [
            TrendPoolItem.from_dict(d)
            for d in self._storage.load_trend_pool(self._profile)
        ]
        if not trend_pool:
            logger.info("[5M scan] trend pool empty, skip")
            return {'triggered': [], 'skipped': [], 'errors': []}

        triggered, skipped, errors = [], [], []

        for item in trend_pool:
            symbol = item.symbol
            direction = item.direction
            h1_period = item.h1_ema_period

            try:
                # ── 单品种 DND ──────────────────────────────────────────────
                dnd_expiry = self._storage.load_symbol_dnd(self._profile, symbol)
                if dnd_expiry:
                    skipped.append(f"{symbol}(dnd)")
                    continue

                # ── 已有待确认信号则跳过（避免重复推送）──────────────────────
                existing = self._storage.load_pending_signal(self._profile, symbol)
                if existing:
                    skipped.append(f"{symbol}(pending)")
                    continue

                # ── 拉取数据 ────────────────────────────────────────────────
                mtf = self._dp.get_multi_timeframe(
                    symbol, ['M5', 'H1'], count=250
                )
                df_5m = mtf.get('M5')
                df_h1 = mtf.get('H1')

                if df_5m is None or df_5m.empty or len(df_5m) < max(self.ema_5m_periods) + 5:
                    skipped.append(f"{symbol}(no_data)")
                    continue

                closes_5m = df_5m['close'].to_numpy(dtype=float)
                highs_5m  = df_5m['high'].to_numpy(dtype=float)
                lows_5m   = df_5m['low'].to_numpy(dtype=float)

                atr_5m = float(
                    calc_atr(highs_5m, lows_5m, closes_5m, ATR_PERIOD)[-1]
                )
                if atr_5m == 0:
                    skipped.append(f"{symbol}(atr0)")
                    continue

                # ── 5M EMA 穿越（任意一条通过即可） ─────────────────────────
                crossover_5m = any(
                    check_ema_crossover(df_5m, [p], atr_5m, direction)
                    for p in self.ema_5m_periods
                )

                # ── H1 绑定均线穿越（可选加分项，不是必须）──────────────────
                h1_cross = False
                if df_h1 is not None and not df_h1.empty:
                    closes_h1 = df_h1['close'].to_numpy(dtype=float)
                    highs_h1  = df_h1['high'].to_numpy(dtype=float)
                    lows_h1   = df_h1['low'].to_numpy(dtype=float)
                    atr_h1 = float(
                        calc_atr(highs_h1, lows_h1, closes_h1, ATR_PERIOD)[-1]
                    )
                    if atr_h1 > 0:
                        h1_cross = check_ema_crossover(
                            df_h1, [h1_period], atr_h1, direction
                        )

                # 5M 穿越或 H1 绑定均线穿越，任意一个触发即可进入 3-bar 过滤
                if not (crossover_5m or h1_cross):
                    skipped.append(f"{symbol}(no_cross)")
                    continue

                # ── 3-bar breakout 过滤 ─────────────────────────────────────
                if not check_3bar_breakout(df_5m, direction):
                    skipped.append(f"{symbol}(3bar)")
                    continue

                # ── 止损位 ──────────────────────────────────────────────────
                buffer = SL_BUFFER_PIPS * _pip_value(symbol)
                sl_price = calculate_stop_loss(df_5m, direction, buffer_pips=buffer)
                if sl_price is None:
                    skipped.append(f"{symbol}(no_sl)")
                    continue

                entry_price = float(closes_5m[-1])

                # ── 仓位计算 ─────────────────────────────────────────────────
                try:
                    account_info = self._executor.get_account_info()
                    balance = account_info.balance
                    cash_available = account_info.margin_available
                except Exception:
                    balance = self._account_size
                    cash_available = self._account_size

                units = calculate_position_size(
                    symbol=symbol,
                    entry_price=entry_price,
                    stop_loss=sl_price,
                    short=(direction == 'short'),
                    total_account_size=balance,
                    risk_percent=RISK_PERCENT,
                    num_symbols=1,
                    current_atr=atr_5m,
                    cash_available=cash_available,
                )

                if units <= 0:
                    logger.info(
                        f"[5M scan] {symbol} position size=0, risk check failed"
                    )
                    skipped.append(f"{symbol}(risk_check)")
                    continue

                units_int = max(1000, int(round(units / 1000) * 1000))  # 整千

                # ── 保存 PendingSignal ─────────────────────────────────────
                signal = PendingSignal(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    stop_loss=sl_price,
                    position_size=units_int,
                )
                self._storage.save_pending_signal(
                    self._profile, symbol, signal.to_dict()
                )
                logger.info(
                    f"[5M scan] {symbol} signal saved: {direction} "
                    f"entry={entry_price:.5f} sl={sl_price:.5f} units={units_int}"
                )

                # ── 推送通知 ─────────────────────────────────────────────────
                self._notify_5m_signal(
                    symbol, direction, df_5m,
                    entry_price, sl_price, units_int, atr_5m
                )
                triggered.append(symbol)

            except Exception as e:
                logger.error(f"[5M scan] {symbol} error: {e}", exc_info=True)
                errors.append(f"{symbol}: {e}")

        logger.info(
            f"[5M scan] done. triggered={triggered}, "
            f"skipped={len(skipped)}, errors={len(errors)}"
        )
        return {'triggered': triggered, 'skipped': skipped, 'errors': errors}

    def _notify_5m_signal(
        self,
        symbol: str,
        direction: str,
        df,
        entry_price: float,
        sl_price: float,
        units: int,
        atr_val: float,
    ) -> None:
        """生成 5M 图表并推送待确认信号通知。"""
        try:
            closes = df['close'].to_numpy(dtype=float)
            highs  = df['high'].to_numpy(dtype=float)
            lows   = df['low'].to_numpy(dtype=float)

            ema_dict = {}
            for i, period in enumerate(self.ema_5m_periods):
                color = _EMA_COLORS[i % len(_EMA_COLORS)]
                ema_dict[f'EMA{period}'] = (calc_ema(closes, period), color)

            sl_dist = abs(entry_price - sl_price)
            lots = units / 100_000
            arrow = '🔺' if direction == 'long' else '🔻'

            image_bytes = generate_ema_chart(
                df=df,
                ema_dict=ema_dict,
                title=f'{symbol}',
                entry_price=entry_price,
                stop_loss=sl_price,
                direction=direction,
                timeframe='M5',
                n_candles=CHART_CANDLES,
            )
            caption = (
                f"{arrow} <b>5M 信号 — {symbol}</b>\n"
                f"方向: <b>{'多' if direction == 'long' else '空'}</b>\n"
                f"入场≈ {entry_price:.5f}\n"
                f"止损:  {sl_price:.5f}  (距离 {sl_dist:.5f})\n"
                f"仓位:  {lots:.2f} 手 ({units} units)\n"
                f"ATR:   {atr_val:.5f}\n\n"
                f"✅ 发送 /open {symbol} 确认开仓\n"
                f"🔕 发送 /dnd 15 {symbol} 推迟 15 分钟\n"
                f"❌ 发送 /cancel {symbol} 取消"
            )
            self._notifier.send_photo(image_bytes, caption=caption)
        except Exception as e:
            logger.error(f"[5M notify] {symbol} chart/send error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 开仓执行（由 /open 触发）
    # ─────────────────────────────────────────────────────────────────────────

    def execute_open(self, symbol: str) -> Dict[str, Any]:
        """
        根据已保存的 PendingSignal 执行市价开仓。

        Parameters
        ----------
        symbol : str
            要开仓的品种（Oanda 格式，如 'EUR_USD'）。

        Returns
        -------
        dict
            {'success': bool, 'fill_price': float, 'units': int,
             'side': str, 'stop_loss': float, 'error': str}
        """
        sig_dict = self._storage.load_pending_signal(self._profile, symbol)
        if not sig_dict:
            return {'success': False, 'error': f'no pending signal for {symbol}'}

        signal = PendingSignal.from_dict(sig_dict)
        side = 'buy' if signal.direction == 'long' else 'sell'

        try:
            result = self._executor.place_order(
                symbol=symbol,
                side=side,
                units=float(signal.position_size),
                stop_loss=signal.stop_loss,
            )
        except Exception as e:
            logger.error(f"execute_open {symbol} place_order error: {e}")
            return {'success': False, 'error': str(e)}

        if result.success:
            # 清除已执行的信号
            self._storage.delete_pending_signal(self._profile, symbol)
            logger.info(
                f"execute_open {symbol} success: fill={result.fill_price} "
                f"units={result.units} trade_id={result.trade_id}"
            )
            # 顺手发送确认通知
            try:
                self._notifier._send(
                    f"✅ <b>开仓成功</b>  {symbol}\n"
                    f"方向: {'多' if signal.direction == 'long' else '空'}\n"
                    f"成交价: {result.fill_price:.5f}\n"
                    f"仓位: {int(abs(result.units))} units\n"
                    f"止损: {signal.stop_loss:.5f}\n"
                    f"Trade ID: {result.trade_id}"
                )
            except Exception:
                pass
            return {
                'success': True,
                'fill_price': result.fill_price,
                'units': int(abs(result.units)),
                'side': signal.direction,
                'stop_loss': signal.stop_loss,
                'trade_id': result.trade_id,
            }
        else:
            logger.error(f"execute_open {symbol} failed: {result.error}")
            return {'success': False, 'error': result.error or 'place_order failed'}

    # ─────────────────────────────────────────────────────────────────────────
    # 平仓所有持仓（由 /close all 触发）
    # ─────────────────────────────────────────────────────────────────────────

    def execute_close_all(self) -> Dict[str, Any]:
        """
        平掉所有当前开仓。

        Returns
        -------
        dict  {'closed': [symbol...], 'errors': [msg...]}
        """
        closed, errors = [], []
        try:
            positions = self._executor.get_positions()
        except Exception as e:
            return {'closed': [], 'errors': [str(e)]}

        for pos in positions:
            try:
                result = self._executor.close_position(pos.position_id)
                if result.success:
                    closed.append(pos.symbol)
                    logger.info(
                        f"execute_close_all: closed {pos.symbol} "
                        f"trade_id={pos.position_id}"
                    )
                else:
                    errors.append(f"{pos.symbol}: {result.error}")
            except Exception as e:
                errors.append(f"{pos.symbol}: {e}")

        return {'closed': closed, 'errors': errors}

    # ─────────────────────────────────────────────────────────────────────────
    # 移动止损（由 /move 触发）
    # ─────────────────────────────────────────────────────────────────────────

    def execute_move_sl(self, symbol: str, new_sl: float) -> Dict[str, Any]:
        """
        将 symbol 仓位的止损移动到 new_sl。

        Returns
        -------
        dict  {'success': bool, 'error': str}
        """
        try:
            positions = self._executor.get_positions()
        except Exception as e:
            return {'success': False, 'error': str(e)}

        target = [p for p in positions if p.symbol == symbol]
        if not target:
            return {'success': False, 'error': f'no open position for {symbol}'}

        pos = target[0]
        try:
            ok = self._executor.modify_stop_loss(pos.position_id, new_sl)
            if ok:
                logger.info(
                    f"execute_move_sl {symbol} trade_id={pos.position_id} "
                    f"new_sl={new_sl}"
                )
                return {'success': True}
            else:
                return {'success': False, 'error': 'modify_stop_loss returned False'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ─────────────────────────────────────────────────────────────────────────
    # 查询持仓（由 /order list 触发）
    # ─────────────────────────────────────────────────────────────────────────

    def get_open_positions(self) -> Dict[str, Any]:
        """
        返回当前所有开仓。

        Returns
        -------
        dict  {'positions': [{'symbol', 'side', 'units', 'avg_price', 'unrealized_pnl', 'stop_loss'}]}
        """
        try:
            positions = self._executor.get_positions()
        except Exception as e:
            return {'positions': [], 'error': str(e)}

        result = []
        for p in positions:
            result.append({
                'symbol': p.symbol,
                'side': p.side,
                'units': int(abs(p.units)),
                'avg_price': p.entry_price,
                'unrealized_pnl': p.unrealized_pnl,
                'stop_loss': p.stop_loss,
            })
        return {'positions': result}

    # ─── 资源清理 ────────────────────────────────────────────────────────────

    def close(self) -> None:
        """释放 HTTP 客户端。"""
        try:
            self._dp.close()
        except Exception:
            pass
        try:
            self._executor.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
