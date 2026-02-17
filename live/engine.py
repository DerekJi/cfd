"""
实盘策略引擎

核心循环 (每 5 分钟 Timer Trigger 调用一次):
  1. 拉取 Oanda K线数据 (1000 根 M5)
  2. 计算全部指标 (EMA50/200, ADX, ATR, Donchian)
  3. 从 Storage 恢复 FSM 状态
  4. 检查硬止损 → 运行 FSM → 获取 action
  5. 执行交易 (开仓 / 平仓 / 移动止损)
  6. 保存 FSM 状态 + 持仓 + 日内盈亏
  7. 发送 Telegram 通知

设计原则:
  - 引擎本身不依赖具体 Executor / Storage 实现 (依赖注入)
  - 所有策略逻辑在 core/ 中，引擎只做编排
  - 状态幂等: 重复调用不会产生重复交易
  - dry_run 模式: 不执行实际交易，仅日志
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List

import numpy as np

from config.profiles import ProfileConfig, SymbolConfig
from core.fsm import TrendFilterStateMachine
from core.indicators import calculate_all
from core.position_sizer import calculate_position_size
from core.risk_manager import is_market_open_session, BlueGuardianRiskLimits
from core.forex_utils import get_pnl_factor, normalize_symbol
from data.oanda_candles import OandaDataProvider
from execution.base import TradeExecutor, OrderResult
from storage.base import StateStorage

logger = logging.getLogger(__name__)


class LiveEngine:
    """
    实盘策略引擎

    用法:
        engine = LiveEngine(config, executor, storage, notifier)
        engine.tick()   # 每 5 分钟调用一次
    """

    def __init__(
        self,
        config: ProfileConfig,
        executor: TradeExecutor,
        storage: StateStorage,
        notifier=None,        # Optional[TelegramNotifier]
    ):
        self.config = config
        self.executor = executor
        self.storage = storage
        self.notifier = notifier

        # Oanda 数据源 (两个 Profile 共用)
        self.data_provider = OandaDataProvider(
            api_key=config.oanda_api_key,
            environment=config.oanda_environment,
        )

        # 每品种一个 FSM 实例
        self.fsm_map: Dict[str, TrendFilterStateMachine] = {}
        for sym in config.symbols:
            self.fsm_map[sym.oanda_name] = TrendFilterStateMachine()

        # Blue Guardian 风控 (仅 blue_guardian profile)
        self.risk_limits: Optional[BlueGuardianRiskLimits] = None
        if config.enable_bg_risk_limits:
            self.risk_limits = BlueGuardianRiskLimits(
                account_size=config.account_size,
                max_single_loss_pct=config.bg_max_single_loss_pct,
                max_daily_loss_pct=config.bg_max_daily_loss_pct,
                max_total_drawdown_pct=config.bg_max_total_drawdown_pct,
            )

    # ================================================================
    # 主入口 — 每 5 分钟调用一次
    # ================================================================

    def tick(self) -> Dict[str, Any]:
        """
        主循环：处理所有品种

        Returns:
            dict: {
                'timestamp': ISO 时间戳,
                'actions': { symbol: action_summary },
                'errors': [error_msg, ...],
            }
        """
        result = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'profile': self.config.profile_name,
            'actions': {},
            'errors': [],
        }

        # 恢复/重置每日盈亏
        self._restore_daily_pnl()

        # 恢复 BG 风控状态
        if self.risk_limits:
            self._restore_risk_limits()

        for sym_config in self.config.symbols:
            symbol = sym_config.oanda_name
            try:
                action_summary = self._process_symbol(sym_config)
                if action_summary:
                    result['actions'][symbol] = action_summary
            except Exception as e:
                err_msg = f"{symbol}: {type(e).__name__}: {e}"
                logger.exception(err_msg)
                result['errors'].append(err_msg)
                if self.notifier and self.config.enable_telegram:
                    self.notifier.notify_error(err_msg, self.config.profile_name)

        return result

    # ================================================================
    # 单品种处理
    # ================================================================

    def _process_symbol(self, sym_config: SymbolConfig) -> Optional[Dict[str, Any]]:
        """处理一个品种的完整流程"""
        symbol = sym_config.oanda_name
        profile = self.config.profile_name
        fsm = self.fsm_map[symbol]

        # 1. 拉取 K 线数据
        df = self.data_provider.get_candles(symbol, count=1000)
        if df.empty or len(df) < 200:
            logger.warning(f"{symbol}: 数据不足 ({len(df)} bars), 跳过")
            return None

        # 2. 计算指标
        indicators = calculate_all(df)
        last_idx = len(df) - 1
        bar_data = self._make_bar_data(df, indicators, last_idx)

        logger.info(
            f"{symbol} bar={bar_data['datetime']} "
            f"close={bar_data['close']:.5f} "
            f"ADX={bar_data['adx']:.1f} ATR={bar_data['atr']:.5f}"
        )

        # 3. 时段过滤 (只影响开仓，不影响平仓/移动止损)
        blocked, session = is_market_open_session(bar_data['datetime'])

        # 4. 恢复 FSM 状态
        saved_state = self.storage.load_fsm_state(profile, symbol)
        if saved_state:
            fsm.restore(saved_state)

        # 5. 硬止损检查 (实盘: 服务端止损已挂，这里做二次确认)
        hard_stop_action = fsm.check_hard_stop(bar_data)
        if hard_stop_action:
            return self._handle_exit(sym_config, fsm, hard_stop_action, bar_data)

        # 6. FSM 主逻辑
        action = fsm.update(bar_data)

        # 7. 处理 action
        if action:
            action_type = action.get('action', '')

            if action_type in ('entry_long', 'entry_short'):
                if blocked:
                    logger.info(f"{symbol}: {session}时段，跳过开仓信号")
                    # FSM 已经进入 POSITION 状态但实际不开仓，需要回退
                    fsm._reset()
                    self._save_fsm_state(symbol, fsm)
                    return {'action': 'blocked', 'reason': session}

                return self._handle_entry(sym_config, fsm, action, bar_data)

            elif action_type in ('exit_long', 'exit_short'):
                return self._handle_exit(sym_config, fsm, action, bar_data)

        # 8. 持仓中 — 检查移动止损更新
        pos = self.storage.load_position(profile, symbol)
        if pos and fsm.stop_loss is not None:
            saved_sl = pos.get('stop_loss')
            if saved_sl is not None and fsm.stop_loss != saved_sl:
                self._handle_trailing_stop(sym_config, pos, fsm.stop_loss)
                pos['stop_loss'] = fsm.stop_loss
                self.storage.save_position(profile, symbol, pos)

        # 9. 保存 FSM 状态
        self._save_fsm_state(symbol, fsm)

        return None

    # ================================================================
    # 开仓处理
    # ================================================================

    def _handle_entry(
        self,
        sym_config: SymbolConfig,
        fsm: TrendFilterStateMachine,
        action: Dict[str, Any],
        bar_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """处理开仓信号"""
        symbol = sym_config.oanda_name
        profile = self.config.profile_name
        is_short = action['action'] == 'entry_short'
        side = 'sell' if is_short else 'buy'

        entry_price = action['entry_price']
        stop_loss = action['stop_loss']

        # 获取账户信息
        account = self.executor.get_account_info()

        # 仓位计算
        units = calculate_position_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            short=is_short,
            total_account_size=account.balance,
            risk_percent=self.config.risk_percent,
            num_symbols=self.config.num_symbols,
            current_atr=bar_data['atr'],
            cash_available=account.margin_available,
            min_lot=self.config.min_lot,
            max_lot=self.config.max_lot,
            leverage=self.config.leverage,
        )

        if units <= 0:
            logger.info(f"{symbol}: 仓位计算 = 0, 跳过")
            fsm._reset()
            self._save_fsm_state(symbol, fsm)
            return {'action': 'skip', 'reason': 'position_size_zero'}

        # 最小单位数检查
        if units < self.config.min_units:
            logger.info(f"{symbol}: units {units:.0f} < min {self.config.min_units}, 跳过")
            fsm._reset()
            self._save_fsm_state(symbol, fsm)
            return {'action': 'skip', 'reason': 'below_min_units'}

        # Blue Guardian 风控检查
        if self.risk_limits:
            pnl_factor = get_pnl_factor(symbol, entry_price)
            estimated_loss = abs(entry_price - stop_loss) * units * pnl_factor
            allowed, reason = self.risk_limits.can_open_trade(estimated_loss)
            if not allowed:
                logger.warning(f"{symbol}: BG 风控拒绝 — {reason}")
                fsm._reset()
                self._save_fsm_state(symbol, fsm)
                if self.notifier and self.config.enable_telegram:
                    self.notifier.notify_risk_alert('开仓拒绝', f"{symbol}: {reason}", profile)
                return {'action': 'blocked', 'reason': reason}

        # 执行下单
        exec_symbol = self.config.get_symbol_name(sym_config)
        risk_amount = self.config.risk_percent / 100 * account.balance / self.config.num_symbols

        if self.config.dry_run:
            logger.info(f"[DRY_RUN] {symbol}: {side} {units:.0f} units @ {entry_price:.5f}, SL={stop_loss:.5f}")
            order_result = OrderResult(
                success=True, order_id='dry_run', trade_id='dry_run',
                fill_price=entry_price, units=units,
            )
        else:
            order_result = self.executor.place_order(exec_symbol, side, units, stop_loss)

        if not order_result.success:
            logger.error(f"{symbol}: 下单失败 — {order_result.error}")
            fsm._reset()
            self._save_fsm_state(symbol, fsm)
            if self.notifier and self.config.enable_telegram:
                self.notifier.notify_error(f"下单失败 {symbol}: {order_result.error}", profile)
            return {'action': 'error', 'error': order_result.error}

        # 保存持仓
        pos_data = {
            'symbol': symbol,
            'side': 'short' if is_short else 'long',
            'units': units,
            'entry_price': order_result.fill_price or entry_price,
            'stop_loss': stop_loss,
            'trade_id': order_result.trade_id,
            'entry_time': datetime.now(timezone.utc).isoformat(),
        }
        self.storage.save_position(profile, symbol, pos_data)
        self._save_fsm_state(symbol, fsm)

        logger.info(
            f"{symbol}: {'做空' if is_short else '做多'} {units:.0f} units "
            f"@ {pos_data['entry_price']:.5f}, SL={stop_loss:.5f}, "
            f"trade_id={order_result.trade_id}"
        )

        # Telegram 通知
        if self.notifier and self.config.enable_telegram:
            self.notifier.notify_entry(
                symbol=symbol,
                side=pos_data['side'],
                entry_price=pos_data['entry_price'],
                stop_loss=stop_loss,
                units=units,
                risk_amount=risk_amount,
                adx=bar_data['adx'],
                ema200=bar_data['ema200'],
                profile=profile,
            )

        return {'action': action['action'], 'units': units, 'trade_id': order_result.trade_id}

    # ================================================================
    # 平仓处理
    # ================================================================

    def _handle_exit(
        self,
        sym_config: SymbolConfig,
        fsm: TrendFilterStateMachine,
        action: Dict[str, Any],
        bar_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """处理平仓信号"""
        symbol = sym_config.oanda_name
        profile = self.config.profile_name

        pos = self.storage.load_position(profile, symbol)
        if not pos:
            logger.warning(f"{symbol}: 收到平仓信号但无持仓记录")
            self._save_fsm_state(symbol, fsm)
            return {'action': 'no_position'}

        trade_id = pos.get('trade_id')
        exit_price = action.get('exit_price', bar_data['close'])
        entry_price = pos.get('entry_price', 0)
        units = pos.get('units', 0)
        side = pos.get('side', 'long')

        # 执行平仓
        if self.config.dry_run:
            logger.info(f"[DRY_RUN] {symbol}: 平仓 trade_id={trade_id}")
            close_result = OrderResult(success=True, order_id='dry_run', fill_price=exit_price)
        else:
            if trade_id:
                close_result = self.executor.close_position(trade_id)
            else:
                logger.error(f"{symbol}: 无 trade_id，跳过平仓")
                return {'action': 'error', 'error': 'no_trade_id'}

        if not close_result.success:
            logger.error(f"{symbol}: 平仓失败 — {close_result.error}")
            if self.notifier and self.config.enable_telegram:
                self.notifier.notify_error(f"平仓失败 {symbol}: {close_result.error}", profile)
            return {'action': 'error', 'error': close_result.error}

        # 计算盈亏
        actual_exit = close_result.fill_price or exit_price
        pnl_factor = get_pnl_factor(symbol, actual_exit)
        if side == 'long':
            raw_pnl = (actual_exit - entry_price) * units
        else:
            raw_pnl = (entry_price - actual_exit) * units
        pnl_usd = raw_pnl * pnl_factor
        pnl_pct = (pnl_usd / self.config.account_size) * 100 if self.config.account_size > 0 else 0

        # 计算持仓时间
        entry_time_str = pos.get('entry_time', '')
        hold_time = self._calc_hold_time(entry_time_str)

        # 更新 BG 风控
        if self.risk_limits:
            self.risk_limits.record_trade_pnl(pnl_usd)

        # 记录交易
        trade_record = {
            'symbol': symbol,
            'side': side,
            'units': units,
            'entry_price': entry_price,
            'exit_price': actual_exit,
            'pnl': pnl_usd,
            'pnl_pct': pnl_pct,
            'reason': action.get('reason', 'unknown'),
            'entry_time': entry_time_str,
            'exit_time': datetime.now(timezone.utc).isoformat(),
        }
        self.storage.append_trade_record(profile, trade_record)

        # 删除持仓
        self.storage.delete_position(profile, symbol)

        # 更新日内盈亏
        self._update_daily_pnl(pnl_usd)

        # 保存 FSM (已 reset)
        self._save_fsm_state(symbol, fsm)

        logger.info(
            f"{symbol}: 平仓 @ {actual_exit:.5f}, "
            f"PnL={'+'if pnl_usd>=0 else ''}{pnl_usd:.2f} ({pnl_pct:+.2f}%), "
            f"原因={action.get('reason')}"
        )

        # Telegram 通知
        if self.notifier and self.config.enable_telegram:
            self.notifier.notify_exit(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                exit_price=actual_exit,
                pnl=pnl_usd,
                pnl_pct=pnl_pct,
                hold_time=hold_time,
                reason=action.get('reason', 'unknown'),
                profile=profile,
            )

        return {
            'action': action['action'],
            'pnl': pnl_usd,
            'pnl_pct': pnl_pct,
            'reason': action.get('reason'),
        }

    # ================================================================
    # 移动止损
    # ================================================================

    def _handle_trailing_stop(
        self,
        sym_config: SymbolConfig,
        pos: Dict[str, Any],
        new_stop_loss: float,
    ) -> None:
        """更新服务端移动止损"""
        symbol = sym_config.oanda_name
        trade_id = pos.get('trade_id')
        old_sl = pos.get('stop_loss', 0)

        if not trade_id:
            return

        logger.info(f"{symbol}: 移动止损 {old_sl:.5f} → {new_stop_loss:.5f}")

        if self.config.dry_run:
            logger.info(f"[DRY_RUN] {symbol}: modify_stop_loss trade_id={trade_id}")
            return

        try:
            success = self.executor.modify_stop_loss(trade_id, new_stop_loss)
            if not success:
                logger.warning(f"{symbol}: 移动止损修改失败")
        except Exception as e:
            logger.error(f"{symbol}: 移动止损异常 — {e}")

    # ================================================================
    # 辅助方法
    # ================================================================

    def _make_bar_data(
        self,
        df,
        indicators: Dict[str, np.ndarray],
        idx: int,
    ) -> Dict[str, Any]:
        """从 DataFrame + indicators 构造 FSM 需要的 bar_data dict"""
        row = df.iloc[idx]
        dt = row['datetime']
        if hasattr(dt, 'to_pydatetime'):
            dt = dt.to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return {
            'close': float(row['close']),
            'high': float(row['high']),
            'low': float(row['low']),
            'open': float(row['open']),
            'up_line': float(indicators['up_line'][idx]),
            'down_line': float(indicators['down_line'][idx]),
            'ema50': float(indicators['ema50'][idx]),
            'ema200': float(indicators['ema200'][idx]),
            'adx': float(indicators['adx'][idx]),
            'atr': float(indicators['atr'][idx]),
            'bar_index': idx,
            'datetime': dt,
        }

    def _save_fsm_state(self, symbol: str, fsm: TrendFilterStateMachine) -> None:
        """保存 FSM 状态到 Storage"""
        snapshot = fsm.get_state_snapshot()
        self.storage.save_fsm_state(self.config.profile_name, symbol, snapshot)

    def _restore_daily_pnl(self) -> None:
        """恢复每日盈亏"""
        profile = self.config.profile_name
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        saved = self.storage.load_daily_pnl(profile)
        if saved and saved.get('date') == today:
            self._daily_pnl = saved.get('pnl', 0.0)
            self._daily_trades = saved.get('trades', 0)
        else:
            self._daily_pnl = 0.0
            self._daily_trades = 0

        # 同步到 BG 风控
        if self.risk_limits:
            self.risk_limits.daily_pnl = self._daily_pnl
            self.risk_limits.daily_date = today

    def _restore_risk_limits(self) -> None:
        """从账户信息恢复 BG 风控状态"""
        if not self.risk_limits:
            return
        try:
            account = self.executor.get_account_info()
            self.risk_limits.update_equity(account.equity)
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")

    def _update_daily_pnl(self, pnl: float) -> None:
        """更新并保存每日盈亏"""
        profile = self.config.profile_name
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        self._daily_pnl += pnl
        self._daily_trades += 1

        self.storage.save_daily_pnl(profile, {
            'date': today,
            'pnl': self._daily_pnl,
            'trades': self._daily_trades,
        })

    @staticmethod
    def _calc_hold_time(entry_time_str: str) -> str:
        """计算持仓时间的可读字符串"""
        if not entry_time_str:
            return 'N/A'
        try:
            entry_dt = datetime.fromisoformat(entry_time_str)
            now = datetime.now(timezone.utc)
            delta = now - entry_dt
            total_minutes = int(delta.total_seconds() / 60)
            hours = total_minutes // 60
            minutes = total_minutes % 60
            if hours > 0:
                return f"{hours}h{minutes}m"
            return f"{minutes}m"
        except (ValueError, TypeError):
            return 'N/A'

    def close(self):
        """关闭资源"""
        self.data_provider.close()
        if self.notifier:
            self.notifier.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
