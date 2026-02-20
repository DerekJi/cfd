"""
双向趋势追踪策略 (Dual-Direction Trend Trailing System)

策略逻辑来源:
  - docs/双向趋势追踪交易系统.md
  - pine-scripts/dual-direction-trending-trade.pine

核心逻辑:
  1. 入场条件: 基于 EMA5/EMA20/EMA200 组合K线穿越 + 分形止损
  2. 止损阶段一 (保本): 浮盈 >= 1×ATR 时，SL 移至入场价 + 0.1×ATR（多）
  3. 止损阶段二 (追踪): 保本后，SL = max(EMA20 - 0.5×ATR, close - trailingDist)（多）
"""

import backtrader as bt


class DualDirectionTrendStrategy(bt.Strategy):
    """
    双向趋势追踪策略

    入场:
      - 多头: lowerEma > EMA200, 组合K线收盘 > upperEma, 最低 < lowerEma, 阳线
      - 空头: upperEma < EMA200, 组合K线收盘 < lowerEma, 最高 > upperEma, 阴线

    止损:
      - 初始止损: 分形低/高点 ± 0.5×ATR
      - 保本: 浮盈 >= 1×ATR → SL = 入场价 ± 0.1×ATR
      - 追踪: SL = max/min(EMA20 ± 0.5×ATR, close ∓ trailingDist)
    """

    params = (
        # EMA 参数
        ('ema_fast_len', 5),
        ('ema_slow_len', 20),
        ('ema_base_len', 200),

        # ATR 参数
        ('atr_len', 14),

        # 成交量过滤
        ('check_volume', False),
        ('vol_sma_len', 10),
        ('vol_mult', 1.1),

        # 分形回看 (左右各 N 根, Pine Script 中为 2)
        ('fractal_period', 2),

        # 止损参数
        ('sl_initial_atr_mult', 0.5),       # 初始止损 = fractal ± N×ATR
        ('sl_breakeven_atr_mult', 0.1),     # 保本偏移 = entry ± N×ATR
        ('sl_trailing_atr_mult', 0.5),      # 追踪止损 = EMA20 ± N×ATR
        # 最小追踪距离：确保止损不过于贴近入场价（过滤低质量信号）
        # trailing_dist = entry - SL，必须 >= N×ATR
        ('min_trailing_dist_atr', 1.0),

        # 冷却期：止损/止盈后禁止入场的 K 线数（0 = 不限制）
        # 防止 EMA 震荡时反复入场
        ('cooldown_bars', 12),
        ('total_account_size', 10000.0),
        ('risk_percent', 1.0),
        ('num_symbols', 1),
        ('pair_type', 'direct'),   # 'direct' | 'indirect' | 'cross'
        ('quote_usd_rate', 0.0),   # 仅 cross 对使用
        ('contract_size', 100000),  # 每手单位数: forex=100000, XAUUSD=100, XAGUSD=5000
        ('min_lot', 0.01),
        ('max_lot', 10.0),

        # 调试
        ('debug', True),
    )

    def __init__(self):
        # ---- 指标 ----
        self.ema_fast = bt.indicators.EMA(self.data.close, period=self.params.ema_fast_len)
        self.ema_slow = bt.indicators.EMA(self.data.close, period=self.params.ema_slow_len)
        self.ema_base = bt.indicators.EMA(self.data.close, period=self.params.ema_base_len)
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_len)

        # ADX 指标（复用 backtest/indicators 模块）
        self._adx_ind = None

        if self.params.check_volume:
            self.vol_sma = bt.indicators.SMA(self.data.volume, period=self.params.vol_sma_len)
        else:
            self.vol_sma = None

        # ---- 分形高低点 (滚动更新) ----
        self._latest_fractal_low = None
        self._latest_fractal_high = None

        # ---- 持仓状态 ----
        self.order = None
        self.entry_price = None
        self.stop_loss_price = None
        self.trailing_dist = None
        self.atr_at_entry = None
        self.position_side = None   # 'long' | 'short'
        self.pending_entry_info = None
        self._last_close_bar = -9999  # 上次平仓的 bar 序号（用于冷却期）

        # ---- 统计 ----
        self.traded_count = 0
        self.blocked_by_session = 0

        if self.params.debug:
            print(f"\n{'='*80}")
            print(f"         双向趋势追踪策略 (Dual-Direction Trend Trailing)")
            print(f"{'='*80}")
            print(f"初始资金: ${self.broker.get_value():.2f}")
            print(f"EMA: {self.params.ema_fast_len} / {self.params.ema_slow_len} / {self.params.ema_base_len}")
            print(f"ATR 周期: {self.params.atr_len}")
            print(f"冷却期: {self.params.cooldown_bars} 根K线  |  最小追踪距离: {self.params.min_trailing_dist_atr}×ATR")
            print(f"风险: {self.params.risk_percent}%")
            print(f"{'='*80}\n")

    # ================================================================
    # 分形计算 (对照 Pine Script isFractalDown/isFractalUp)
    # ================================================================

    def _update_fractals(self):
        """更新最新分形高低点 (需要当前 bar 往前至少 fractal_period+1 根)"""
        n = self.params.fractal_period
        # 检查数据是否足够
        if len(self.data) < 2 * n + 1:
            return

        # 分形计算基于 bar[n]（即 n 根前的那根 K 线）
        # Pine: low[2] < low[0] and low[2] < low[1] and low[2] < low[3] and low[2] < low[4]
        # 即 center = n=2 时，比较 low[-n] vs low[-n+1..0] 和 low[-n-1..-2n]
        center_low = self.data.low[-n]
        center_high = self.data.high[-n]

        is_fractal_low = all(center_low < self.data.low[-i] for i in range(0, n)) and \
                         all(center_low < self.data.low[-(n + i + 1)] for i in range(0, n))

        is_fractal_high = all(center_high > self.data.high[-i] for i in range(0, n)) and \
                          all(center_high > self.data.high[-(n + i + 1)] for i in range(0, n))

        if is_fractal_low:
            self._latest_fractal_low = center_low
        if is_fractal_high:
            self._latest_fractal_high = center_high

    # ================================================================
    # 信号检测 (对照 Pine Script isLongSignal / isShortSignal)
    # ================================================================

    def _check_signals(self):
        """
        基于组合 K 线逻辑检测入场信号.
        mergedLow  = min(low[0], low[1])
        mergedHigh = max(high[0], high[1])
        mergedOpen = open[1]
        mergedClose= close[0]
        lowerEma   = min(ema5[0], ema20[0], ema5[1], ema20[1])
        upperEma   = max(ema5[0], ema20[0], ema5[1], ema20[1])
        """
        if len(self.data) < 2:
            return False, False

        merged_low = min(self.data.low[0], self.data.low[-1])
        merged_high = max(self.data.high[0], self.data.high[-1])
        merged_open = self.data.open[-1]
        merged_close = self.data.close[0]

        ema_f0 = self.ema_fast[0]
        ema_s0 = self.ema_slow[0]
        ema_f1 = self.ema_fast[-1]
        ema_s1 = self.ema_slow[-1]
        ema200 = self.ema_base[0]

        lower_ema = min(ema_f0, ema_s0, ema_f1, ema_s1)
        upper_ema = max(ema_f0, ema_s0, ema_f1, ema_s1)

        if self.params.check_volume and self.vol_sma:
            vol_cond = self.data.volume[0] > self.vol_sma[0] * self.params.vol_mult
        else:
            vol_cond = True

        # ADX 趋势强度过滤
        if self._adx_ind is not None and self.params.adx_threshold > 0:
            adx_cond = self._adx_ind.adx[0] >= self.params.adx_threshold
        else:
            adx_cond = True

        is_long = (
            lower_ema > ema200 and
            merged_close > upper_ema and
            merged_low < lower_ema and
            merged_close > merged_open and
            vol_cond and adx_cond and
            self.data.close[0] >= max(self.data.high.get(ago=-1, size=20))
        )

        is_short = (
            upper_ema < ema200 and
            merged_close < lower_ema and
            merged_high > upper_ema and
            merged_close < merged_open and
            vol_cond and adx_cond and
            self.data.close[0] <= min(self.data.low.get(ago=-1, size=20))
        )

        return is_long, is_short

    # ================================================================
    # 止损追踪 (对照 Pine Script UpdateTrailingStop)
    # ================================================================

    def _update_trailing_stop(self):
        """更新移动止损，返回是否需要平仓"""
        if not self.position or self.stop_loss_price is None:
            return False

        close = self.data.close[0]
        ema20 = self.ema_slow[0]
        atr = self.atr[0]

        if self.position_side == 'long':
            # ── 触发止损 ──
            if self.data.low[0] <= self.stop_loss_price:
                return True

            is_safe = self.stop_loss_price >= self.entry_price

            if not is_safe:
                # 阶段一：保本
                if (close - self.entry_price) >= self.atr_at_entry:
                    new_sl = self.entry_price + self.params.sl_breakeven_atr_mult * self.atr_at_entry
                    if new_sl > self.stop_loss_price:
                        self.stop_loss_price = new_sl
                        if self.params.debug:
                            print(f"  📌 保本止损 → {new_sl:.5f}")
            else:
                # 阶段二：追踪
                target_sl = max(
                    ema20 - self.params.sl_trailing_atr_mult * atr,
                    close - self.trailing_dist
                )
                if target_sl > self.stop_loss_price:
                    self.stop_loss_price = target_sl
                    if self.params.debug:
                        print(f"  📌 追踪止损 → {target_sl:.5f}")

        elif self.position_side == 'short':
            # ── 触发止损 ──
            if self.data.high[0] >= self.stop_loss_price:
                return True

            is_safe = self.stop_loss_price <= self.entry_price

            if not is_safe:
                # 阶段一：保本
                if (self.entry_price - close) >= self.atr_at_entry:
                    new_sl = self.entry_price - self.params.sl_breakeven_atr_mult * self.atr_at_entry
                    if new_sl < self.stop_loss_price:
                        self.stop_loss_price = new_sl
                        if self.params.debug:
                            print(f"  📌 保本止损 → {new_sl:.5f}")
            else:
                # 阶段二：追踪
                target_sl = min(
                    ema20 + self.params.sl_trailing_atr_mult * atr,
                    close + self.trailing_dist
                )
                if target_sl < self.stop_loss_price:
                    self.stop_loss_price = target_sl
                    if self.params.debug:
                        print(f"  📌 追踪止损 → {target_sl:.5f}")

        return False

    # ================================================================
    # 仓位计算（复用 TrendFilter 的精确公式）
    # ================================================================

    def _calculate_position_size(self, entry_price, stop_loss, short=False):
        cash_available = self.broker.get_cash()
        risk_amount = (self.params.total_account_size * self.params.risk_percent / 100) / self.params.num_symbols

        stop_distance = (stop_loss - entry_price) if short else (entry_price - stop_loss)
        if stop_distance <= 0:
            return 0

        # 最小止损距离保护
        current_atr = self.atr[0]
        min_stop_distance = current_atr * 0.15
        if stop_distance < min_stop_distance:
            if self.params.debug:
                print(f"\n⚠️  跳过 (止损距离过小: {stop_distance:.5f} < {min_stop_distance:.5f})\n")
            return 0

        SLIPPAGE_PROTECTION = 3.0

        # 正确的 pnl_factor 按品种类型划分:
        #   direct  (GBPUSD, EURUSD, XAUUSD, XAGUSD): PnL = size × Δprice × 1.0
        #   indirect(USDJPY):                          PnL = size × Δprice × (1/price)
        #   cross   (AUDJPY):                          PnL = size × Δprice × quote_usd_rate
        pair_type = self.params.pair_type
        if pair_type == 'cross' and self.params.quote_usd_rate > 0:
            pnl_factor = self.params.quote_usd_rate
        elif pair_type == 'indirect':
            pnl_factor = 1.0 / entry_price
        else:  # direct (含 XAUUSD/XAGUSD)
            pnl_factor = 1.0

        size = risk_amount / (stop_distance * pnl_factor * SLIPPAGE_PROTECTION)

        # ATR 硬顶
        max_single_loss = self.params.total_account_size * 0.01
        max_safe_size = max_single_loss / (current_atr * 2.5 * pnl_factor)
        if size > max_safe_size:
            size = max_safe_size

        # 保证金检查 (按 pair_type 正确计算)
        LEVERAGE = 30.0
        if pair_type == 'cross' and self.params.quote_usd_rate > 0:
            margin_needed = size * entry_price * self.params.quote_usd_rate / LEVERAGE
        elif pair_type == 'indirect':
            margin_needed = size / LEVERAGE
        else:  # direct
            margin_needed = size * entry_price / LEVERAGE
        max_margin = cash_available * 0.80
        if margin_needed > max_margin:
            size = size * (max_margin / margin_needed)

        # 最小手数检查
        min_size = self.params.min_lot * self.params.contract_size
        if size < min_size:
            max_loss_min = min_size * stop_distance * pnl_factor * SLIPPAGE_PROTECTION
            if max_loss_min > risk_amount * 1.5:
                return 0

        lots = max(self.params.min_lot, min(size / self.params.contract_size, self.params.max_lot))
        return lots * self.params.contract_size

    # ================================================================
    # Order / Trade 通知
    # ================================================================

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy() and self.pending_entry_info and self.pending_entry_info['side'] == 'long':
                self.entry_price = order.executed.price
                self.stop_loss_price = self.pending_entry_info['stop_loss']
                self.trailing_dist = self.pending_entry_info['trailing_dist']
                self.atr_at_entry = self.pending_entry_info['atr_at_entry']
                self.position_side = 'long'
                self.pending_entry_info = None
                if self.params.debug:
                    print(f"  ✅ 多单开仓 @ {self.entry_price:.5f}  SL={self.stop_loss_price:.5f}")

            elif order.issell():
                if self.pending_entry_info and self.pending_entry_info['side'] == 'short':
                    self.entry_price = order.executed.price
                    self.stop_loss_price = self.pending_entry_info['stop_loss']
                    self.trailing_dist = self.pending_entry_info['trailing_dist']
                    self.atr_at_entry = self.pending_entry_info['atr_at_entry']
                    self.position_side = 'short'
                    self.pending_entry_info = None
                    if self.params.debug:
                        print(f"  ✅ 空单开仓 @ {self.entry_price:.5f}  SL={self.stop_loss_price:.5f}")

            if not self.position:
                self.entry_price = None
                self.stop_loss_price = None
                self.trailing_dist = None
                self.atr_at_entry = None
                self.position_side = None
                self.pending_entry_info = None
                self._last_close_bar = len(self)  # 记录平仓 bar

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.params.debug:
                print(f"  ⚠️ 订单失败: {order.status}")
            self.pending_entry_info = None

        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed and self.params.debug:
            pnl_pct = (trade.pnl / abs(trade.value) * 100) if trade.value != 0 else 0
            label = "止盈" if trade.pnl > 0 else "止损"
            print(f"  └─ {label} 盈亏 ${trade.pnl:.2f} ({pnl_pct:+.2f}%)")

    # ================================================================
    # 主逻辑
    # ================================================================

    def next(self):
        # 1. 更新分形
        self._update_fractals()

        # 2. 持仓中：更新追踪止损
        if self.position and not self.order:
            should_close = self._update_trailing_stop()
            if should_close:
                if self.params.debug:
                    side_label = "多头" if self.position_side == 'long' else "空头"
                    sl_label = "止盈" if (
                        (self.position_side == 'long' and self.stop_loss_price > self.entry_price) or
                        (self.position_side == 'short' and self.stop_loss_price < self.entry_price)
                    ) else "止损"
                    print(f"\n⛔ 【{side_label}{sl_label}】SL={self.stop_loss_price:.5f}")
                self.order = self.close()
            return

        # 3. 空仓：检查入场信号
        if self.position or self.order:
            return

        is_long, is_short = self._check_signals()

        # 冷却期检查
        cooldown = self.params.cooldown_bars
        if cooldown > 0 and (len(self) - self._last_close_bar) < cooldown:
            return

        if is_long and self._latest_fractal_low is not None:
            self._enter_long()
        elif is_short and self._latest_fractal_high is not None:
            self._enter_short()

        # 进度日志
        if self.params.debug and len(self) % 5000 == 0:
            print(f"[Bar {len(self)}] {self.data.datetime.datetime(0).strftime('%Y-%m-%d %H:%M')} "
                  f"close={self.data.close[0]:.5f} EMA200={self.ema_base[0]:.5f}")

    def _enter_long(self):
        from core.risk_manager import is_market_open_session
        dt = self.data.datetime.datetime(0)
        is_blocked, session_name = is_market_open_session(dt)
        if is_blocked:
            self.blocked_by_session += 1
            return

        entry_price = self.data.close[0]
        stop_loss = self._latest_fractal_low - self.params.sl_initial_atr_mult * self.atr[0]
        trailing_dist = entry_price - stop_loss

        # 最小追踪距离保护：止损距离过小说明入场质量低
        min_trail = self.params.min_trailing_dist_atr * self.atr[0]
        if trailing_dist < min_trail:
            if self.params.debug:
                print(f"  ⚠️ 跳过多入 (trailing_dist={trailing_dist:.5f} < {min_trail:.5f} = {self.params.min_trailing_dist_atr}×ATR)")
            return

        size = self._calculate_position_size(entry_price, stop_loss, short=False)
        if size <= 0:
            return

        self.order = self.buy(size=size)
        self.pending_entry_info = {
            'side': 'long',
            'stop_loss': stop_loss,
            'trailing_dist': trailing_dist,
            'atr_at_entry': self.atr[0],
        }
        self.traded_count += 1

        if self.params.debug:
            print(f"\n{'='*60}")
            print(f"🔺 多入  entry={entry_price:.5f}  SL={stop_loss:.5f}  "
                  f"dist={trailing_dist:.5f}  size={size:.0f}")
            print(f"   fractal_low={self._latest_fractal_low:.5f}  ATR={self.atr[0]:.5f}")
            print(f"{'='*60}")

    def _enter_short(self):
        from core.risk_manager import is_market_open_session
        dt = self.data.datetime.datetime(0)
        is_blocked, session_name = is_market_open_session(dt)
        if is_blocked:
            self.blocked_by_session += 1
            return

        entry_price = self.data.close[0]
        stop_loss = self._latest_fractal_high + self.params.sl_initial_atr_mult * self.atr[0]
        trailing_dist = stop_loss - entry_price

        # 最小追踪距离保护
        min_trail = self.params.min_trailing_dist_atr * self.atr[0]
        if trailing_dist < min_trail:
            if self.params.debug:
                print(f"  ⚠️ 跳过空入 (trailing_dist={trailing_dist:.5f} < {min_trail:.5f} = {self.params.min_trailing_dist_atr}×ATR)")
            return

        size = self._calculate_position_size(entry_price, stop_loss, short=True)
        if size <= 0:
            return

        self.order = self.sell(size=size)
        self.pending_entry_info = {
            'side': 'short',
            'stop_loss': stop_loss,
            'trailing_dist': trailing_dist,
            'atr_at_entry': self.atr[0],
        }
        self.traded_count += 1

        if self.params.debug:
            print(f"\n{'='*60}")
            print(f"🔻 空入  entry={entry_price:.5f}  SL={stop_loss:.5f}  "
                  f"dist={trailing_dist:.5f}  size={size:.0f}")
            print(f"   fractal_high={self._latest_fractal_high:.5f}  ATR={self.atr[0]:.5f}")
            print(f"{'='*60}")

    def stop(self):
        if self.params.debug:
            initial = self.params.total_account_size
            final = self.broker.get_value()
            total_return = (final - initial) / initial * 100
            print(f"\n{'='*80}")
            print(f"回测完成")
            print(f"{'='*80}")
            print(f"初始资金: ${initial:.2f}")
            print(f"最终资金: ${final:.2f}")
            print(f"总收益: ${final - initial:.2f} ({total_return:+.2f}%)")
            print(f"实际交易: {self.traded_count} 笔")
            if self.blocked_by_session > 0:
                print(f"开盘时段阻止: {self.blocked_by_session} 笔")
            print(f"{'='*80}\n")
