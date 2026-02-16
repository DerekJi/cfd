"""
趋势过滤突破策略 V1.0

使用ADX+EMA200过滤掉假突破，只在强趋势中交易
"""

import backtrader as bt
from indicators.range_detector import DonchianRangeDetector
from indicators.atr_buffer import ATRBuffer
from indicators.adx_indicator import ADX
from indicators.trend_filter_fsm import TrendFilterStateMachine


class TrendFilterStrategy(bt.Strategy):
    """
    趋势过滤突破策略
    
    核心逻辑：
    1. 使用Donchian通道检测突破
    2. 使用ADX判断趋势强度（>25为强趋势）
    3. 使用EMA200判断趋势方向
    4. 只在强趋势+正确方向时交易
    5. 等待回踩EMA50入场
    6. EMA50作为移动止损
    """
    
    params = (
        # Donchian通道参数
        ('up_period', 20),
        ('down_period', 20),
        
        # EMA参数
        ('ema50_period', 50),
        ('ema200_period', 200),
        
        # ADX参数
        ('adx_period', 14),
        ('adx_threshold', 25),
        
        # ATR参数
        ('atr_period', 14),
        
        # 状态机参数
        ('analysis_bars', 5),
        ('pullback_wait_bars', 20),
        
        # 风险管理（修复：基于总账户而非分配资金）
        ('total_account_size', 10000.0),  # 总账户规模（用于风险计算）
        ('risk_percent', 1.0),  # 每笔交易风险百分比（基于总账户）
        ('num_symbols', 1),  # 同时交易的品种数量（用于分配风险）
        ('quote_usd_rate', 0.0),  # 报价货币→USD转换率 (0=自动用1/price, 用于交叉货币对)
        ('min_lot', 0.01),
        ('max_lot', 10.0),
        ('max_cash_ratio', 0.95),
        
        # 调试
        ('debug', True),
    )
    
    def __init__(self):
        """初始化策略"""
        # 指标
        self.range_detector = DonchianRangeDetector(
            self.data,
            lookback=self.params.up_period  # 使用lookback参数
        )
        
        self.atr_buffer = ATRBuffer(
            self.data,
            period=self.params.atr_period,
            buffer_multiplier=0.2
        )
        
        self.adx = ADX(
            self.data,
            period=self.params.adx_period
        )
        
        self.ema50 = bt.indicators.EMA(
            self.data.close,
            period=self.params.ema50_period
        )
        
        self.ema200 = bt.indicators.EMA(
            self.data.close,
            period=self.params.ema200_period
        )
        
        # 状态机
        self.fsm = TrendFilterStateMachine(
            up_period=self.params.up_period,
            down_period=self.params.down_period,
            ema50_period=self.params.ema50_period,
            ema200_period=self.params.ema200_period,
            adx_period=self.params.adx_period,
            adx_threshold=self.params.adx_threshold,
            analysis_bars=self.params.analysis_bars,
            pullback_wait_bars=self.params.pullback_wait_bars,
            debug=self.params.debug
        )
        
        # 订单管理
        self.order = None
        self.pending_entry_info = None  # 待确认的开仓信息{'stop_loss', 'side'}
        self.entry_price = None  # 开仓价格
        self.stop_loss_price = None  # 止损价格
        self.position_side = None  # 'long' or 'short'
        
        # 统计
        self.filtered_count = 0  # 被过滤掉的突破数
        self.traded_count = 0    # 实际交易数
        self.blocked_by_session = 0  # 因市场开盘时段被阻止的交易数
        
        # 打印策略信息
        if self.params.debug:
            print(f"\n{'='*80}")
            print(f"                    趋势过滤突破策略 V1.0")
            print(f"{'='*80}")
            print(f"初始资金: ${self.broker.get_value():.2f}")
            print(f"UP/DOWN周期: {self.params.up_period}")
            print(f"EMA周期: {self.params.ema50_period} / {self.params.ema200_period}")
            print(f"ADX周期: {self.params.adx_period} (阈值: {self.params.adx_threshold})")
            print(f"风险管理: {self.params.risk_percent}%")
            print(f"{'='*80}\n")
    
    def _is_market_open_session(self, dt):
        """
        检查当前时间是否在市场开盘高波动时段（禁止交易）
        
        悉尼开盘: 07:00 Sydney = 21:00 UTC (标准时间) 或 20:00 UTC (夏令时)
        东京开盘: 09:00 Tokyo = 00:00 UTC
        
        禁止交易窗口：开盘前后15分钟
        """
        # 获取UTC时间的小时和分钟
        hour = dt.hour
        minute = dt.minute
        time_minutes = hour * 60 + minute  # 转换为分钟数（0-1439）
        
        # 东京开盘时段: 00:00 UTC (23:45-00:15)
        tokyo_open = 0  # 00:00的分钟数
        if (time_minutes >= tokyo_open - 15 and time_minutes <= tokyo_open + 15) or \
           (time_minutes >= 1440 - 15):  # 跨日情况：23:45-23:59
            return True, "东京开盘"
        
        # 悉尼开盘时段: 21:00 UTC 标准时间 (20:45-21:15)
        # 简化处理：全年使用21:00（实际需根据夏令时调整）
        sydney_open = 21 * 60  # 21:00的分钟数 = 1260
        if time_minutes >= sydney_open - 15 and time_minutes <= sydney_open + 15:
            return True, "悉尼开盘"
        
        return False, None
    
    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                if self.params.debug:
                    print(f"  ✓ 买单执行: {order.executed.price:.5f}, 数量 {order.executed.size:.0f}")
                
                # ✅ 买单完成后，如果是开仓，设置止损价格
                if self.pending_entry_info and self.pending_entry_info['side'] == 'long':
                    self.entry_price = order.executed.price
                    self.stop_loss_price = self.pending_entry_info['stop_loss']
                    self.position_side = 'long'
                    self.pending_entry_info = None
                    if self.params.debug:
                        print(f"  ✅ 止损设置: {self.stop_loss_price:.5f}")
                
            elif order.issell():
                if self.params.debug:
                    print(f"  ✓ 卖单执行: {order.executed.price:.5f}, 数量 {order.executed.size:.0f}")
                
                # ✅ 卖单完成后，如果是开仓，设置止损价格
                if self.pending_entry_info and self.pending_entry_info['side'] == 'short':
                    self.entry_price = order.executed.price
                    self.stop_loss_price = self.pending_entry_info['stop_loss']
                    self.position_side = 'short'
                    self.pending_entry_info = None
                    if self.params.debug:
                        print(f"  ✅ 止损设置: {self.stop_loss_price:.5f}")
            
            # 如果是平仓，重置止损价格
            if not self.position:
                self.stop_loss_price = None
                self.position_side = None
                self.entry_price = None
                self.pending_entry_info = None
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            status_msg = {
                order.Canceled: "Canceled",
                order.Margin: "Margin (insufficient funds)",
                order.Rejected: "Rejected"
            }.get(order.status, "Unknown")
            
            if self.params.debug:
                print(f"  ⚠️ 订单{status_msg}")
                print(f"     订单类型: {'Buy' if order.isbuy() else 'Sell'}")
                print(f"     订单价格: {order.created.price if hasattr(order.created, 'price') else 'Market'}")
                print(f"     订单数量: {order.created.size if hasattr(order.created, 'size') else 'N/A'}")
                print(f"     当前资金: ${self.broker.getcash():.2f}")
                print(f"     持仓价值: ${self.broker.getvalue() - self.broker.getcash():.2f}")
            
            self.pending_entry_info = None  # 清除待确认信息
        
        self.order = None
    
    def notify_trade(self, trade):
        """交易完成通知"""
        if trade.isclosed:
            if trade.value != 0:
                pnl_percent = (trade.pnl / abs(trade.value)) * 100
            else:
                pnl_percent = 0
            if self.params.debug:
                print(f"  └─ 交易完成: 盈亏 ${trade.pnl:.2f} ({pnl_percent:+.2f}%)")
    
    def next(self):
        """每根K线调用一次"""
        # ✅ 优先检查硬止损（防止失控）
        # 关键修复：检查K线内部的最高/最低价，而非只检查收盘价
        if self.position and self.stop_loss_price and not self.order:
            if self.position_side == 'long':
                # 做多：检查最低价是否跌破止损
                if self.data.low[0] <= self.stop_loss_price:
                    if self.params.debug:
                        print(f"\n⛔ 【硬止损】多头 @ low:{self.data.low[0]:.5f} (止损:{self.stop_loss_price:.5f})")
                    self.order = self.close()
                    return
            elif self.position_side == 'short':
                # 做空：检查最高价是否涨破止损
                if self.data.high[0] >= self.stop_loss_price:
                    if self.params.debug:
                        print(f"\n⛔ 【硬止损】空头 @ high:{self.data.high[0]:.5f} (止损:{self.stop_loss_price:.5f})")
                    self.order = self.close()
                    return
        
        # 准备数据
        bar_data = {
            'close': self.data.close[0],
            'high': self.data.high[0],
            'low': self.data.low[0],
            'up_line': self.range_detector.up_line[0],
            'down_line': self.range_detector.down_line[0],
            'ema50': self.ema50[0],
            'ema200': self.ema200[0],
            'adx': self.adx.adx[0],
            'atr': self.atr_buffer.atr[0],
            'bar_index': len(self),
            'datetime': self.data.datetime.datetime(0)
        }
        
        # 更新状态机
        action = self.fsm.update(bar_data)
        
        # 执行操作
        if action:
            if action['action'] == 'entry_long':
                self._execute_entry_long(action)
                self.traded_count += 1
            elif action['action'] == 'entry_short':
                self._execute_entry_short(action)
                self.traded_count += 1
            elif action['action'] == 'exit_long':
                self._execute_exit_long(action)
            elif action['action'] == 'exit_short':
                self._execute_exit_short(action)
        
        # 每100根K线输出一次状态
        if self.params.debug and len(self) % 100 == 0:
            state = self.fsm.get_state()
            print(f"[Bar {len(self)}] {self.data.datetime.datetime(0).strftime('%Y-%m-%d %H:%M:%S')} "
                  f"| Price: {self.data.close[0]:.5f} | State: {state['state']} "
                  f"| ADX: {self.adx.adx[0]:.1f} | EMA200: {self.ema200[0]:.5f}")
    
    def _execute_entry_long(self, action):
        """做多入场"""
        if self.position or self.order:
            return
        
        # ✅ 检查市场开盘时段（防止高波动/跳空时段开仓）
        dt = self.data.datetime.datetime(0)
        is_blocked, session_name = self._is_market_open_session(dt)
        if is_blocked:
            self.blocked_by_session += 1
            if self.params.debug:
                print(f"\n⚠️  跳过交易（{session_name}开盘窗口）")
                print(f"   时间: {dt.strftime('%Y-%m-%d %H:%M UTC')}")
                print(f"   原因: {session_name}开盘前后15分钟为高波动时段，禁止开仓\n")
            return
        
        entry_price = action['entry_price']
        stop_loss = action['stop_loss']
        
        # 计算仓位
        size = self._calculate_position_size(entry_price, stop_loss, short=False)
        
        # 开多单
        self.order = self.buy(size=size)
        
        # ✅ 记录待确认的开仓信息（在notify_order中确认后设置）
        self.pending_entry_info = {
            'stop_loss': stop_loss,
            'side': 'long'
        }
        
        if self.params.debug:
            lots = size / 100000
            risk_dollars = size * (entry_price - stop_loss) / entry_price
            print(f"\n{'='*80}")
            print(f"🔺 【趋势做多】入场")
            print(f"{'='*80}")
            print(f"入场价格: {entry_price:.5f}")
            print(f"止损价格: {stop_loss:.5f}")
            print(f"仓位大小: {size:.0f} 单位 ({lots:.2f} 手)")
            print(f"风险金额: ${risk_dollars:.2f} ({self.params.risk_percent:.1f}%)")
            print(f"ADX: {self.adx.adx[0]:.1f} | EMA200: {self.ema200[0]:.5f}")
            print(f"{'='*80}\n")
    
    def _execute_entry_short(self, action):
        """做空入场"""
        if self.position or self.order:
            return
        
        # ✅ 检查市场开盘时段（防止高波动/跳空时段开仓）
        dt = self.data.datetime.datetime(0)
        is_blocked, session_name = self._is_market_open_session(dt)
        if is_blocked:
            self.blocked_by_session += 1
            if self.params.debug:
                print(f"\n⚠️  跳过交易（{session_name}开盘窗口）")
                print(f"   时间: {dt.strftime('%Y-%m-%d %H:%M UTC')}")
                print(f"   原因: {session_name}开盘前后15分钟为高波动时段，禁止开仓\n")
            return
        
        entry_price = action['entry_price']
        stop_loss = action['stop_loss']
        
        # 计算仓位
        size = self._calculate_position_size(entry_price, stop_loss, short=True)
        
        # 开空单
        self.order = self.sell(size=size)
        
        # ✅ 记录待确认的开仓信息（在notify_order中确认后设置）
        self.pending_entry_info = {
           'stop_loss': stop_loss,
            'side': 'short'
        }
        
        if self.params.debug:
            lots = size / 100000
            risk_dollars = abs(size) * (stop_loss - entry_price) / entry_price
            print(f"\n{'='*80}")
            print(f"🔻 【趋势做空】入场")
            print(f"{'='*80}")
            print(f"入场价格: {entry_price:.5f}")
            print(f"止损价格: {stop_loss:.5f}")
            print(f"仓位大小: {size:.0f} 单位 ({lots:.2f} 手)")
            print(f"风险金额: ${risk_dollars:.2f} ({self.params.risk_percent:.1f}%)")
            print(f"ADX: {self.adx.adx[0]:.1f} | EMA200: {self.ema200[0]:.5f}")
            print(f"{'='*80}\n")
    
    def _execute_exit_long(self, action):
        """多头出场"""
        if not self.position or self.position.size <= 0:
            return
        
        self.order = self.close()
        
        if self.params.debug:
            entry_price = self.position.price
            exit_price = action['exit_price']
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100
            
            print(f"\n{'='*80}")
            print(f"⏹️  平仓出场")
            print(f"{'='*80}")
            print(f"入场价格: {entry_price:.5f}")
            print(f"出场价格: {exit_price:.5f}")
            print(f"盈亏: {pnl_percent:+.2f}%")
            print(f"{'='*80}\n")
    
    def _execute_exit_short(self, action):
        """空头出场"""
        if not self.position or self.position.size >= 0:
            return
        
        self.order = self.close()
        
        if self.params.debug:
            entry_price = self.position.price
            exit_price = action['exit_price']
            pnl_percent = ((entry_price - exit_price) / entry_price) * 100
            
            print(f"\n{'='*80}")
            print(f"⏹️  平仓出场")
            print(f"{'='*80}")
            print(f"入场价格: {entry_price:.5f}")
            print(f"出场价格: {exit_price:.5f}")
            print(f"盈亏: {pnl_percent:+.2f}%")
            print(f"{'='*80}\n")
    
    def _calculate_position_size(self, entry_price, stop_loss, short=False):
        """
        计算仓位大小（修复版）
        
        风险计算逻辑：
        1. 基于total_account_size（总账户）而非当前broker.get_value()
        2. 考虑同时交易的品种数量，平均分配风险
        3. 防止多品种风险叠加
        """
        cash_available = self.broker.get_cash()
        
        # ✅ 修复1: 使用固定的总账户规模，而非当前账户价值
        # ✅ 修复2: 除以品种数量，分配风险
        risk_amount = (self.params.total_account_size * self.params.risk_percent / 100) / self.params.num_symbols
        
        # 计算止损距离
        if short:
            stop_distance = stop_loss - entry_price
        else:
            stop_distance = entry_price - stop_loss
        
        # 防止止损距离为0或负数
        if stop_distance <= 0:
            return 0
        
        # ✅ 修复11: 止损距离最小阈值 (防止极小止损导致仓位爆炸)
        # 当止损距离极小时(如0.01 yen vs 正常0.5-2.0 yen)，仓位会被放大到极端值
        # 即使滑点保护3x也无法覆盖，因为实际出场可能偏离10x以上
        # 设置最小止损距离 = ATR的10%，低于此阈值拒绝交易
        MIN_STOP_ATR_RATIO = 0.15  # 止损距离至少为ATR的15%
        current_atr = self.atr_buffer.atr[0]
        min_stop_distance = current_atr * MIN_STOP_ATR_RATIO
        
        if stop_distance < min_stop_distance:
            if self.params.debug:
                print(f"\n⚠️  跳过交易 (止损距离过小):")
                print(f"   止损距离: {stop_distance:.5f} ({stop_distance/entry_price*100:.4f}%)")
                print(f"   ATR: {current_atr:.5f}")
                print(f"   最小要求: {min_stop_distance:.5f} (ATR×{MIN_STOP_ATR_RATIO})")
                print(f"   → 拒绝交易，防止仓位爆炸\n")
            return 0
        
        # ✅ 修复3: 仓位计算公式
        # Forex盈亏公式 (由ForexCommissionInfo实现):
        #   direct  (GBPUSD):  PnL = size × Δprice × 1.0
        #   indirect(USDJPY):  PnL = size × Δprice × (1/price)
        #   cross   (AUDJPY):  PnL = size × Δprice × quote_usd_rate
        #
        # 统一公式: PnL = size × Δprice × pnl_factor
        # 因此:     size = risk_amount / (stop_distance × pnl_factor × SLIPPAGE)
        #
        # ✅ 修复6: 添加滑点保护系数
        SLIPPAGE_PROTECTION = 3.0  # 假设最坏情况3倍滑点
        
        # 确定PnL因子
        if self.params.quote_usd_rate > 0:
            # 交叉货币对: 使用显式指定的 quote_usd_rate
            pnl_factor = self.params.quote_usd_rate
        else:
            # direct/indirect: 使用 1/entry_price (对indirect精确, 对direct偏保守)
            pnl_factor = 1.0 / entry_price
        
        size = risk_amount / (stop_distance * pnl_factor * SLIPPAGE_PROTECTION)
        
        # ✅ 修复12: 基于单笔最大亏损的硬顶仓位限制
        # 问题: 策略使用EMA50趋势跟踪退场，实际退场距离可能远超理论止损距离
        #        当止损距离极小时，仓位极大，即使3x滑点保护也无法覆盖
        # 方案: 设定硬顶 = 单笔最大允许亏损 / (ATR × 安全系数 × pnl_factor)
        #        确保即使价格反向移动 2.5×ATR，亏损仍不超过账户的1%
        MAX_SINGLE_LOSS_PCT = 0.01  # Blue Guardian: 单笔最大亏损 = 账户1%
        ATR_WORST_CASE = 2.5       # 预估最坏退场距离 = 2.5倍ATR (含佣金缓冲)
        max_single_loss = self.params.total_account_size * MAX_SINGLE_LOSS_PCT
        max_safe_size = max_single_loss / (current_atr * ATR_WORST_CASE * pnl_factor)
        
        if size > max_safe_size:
            if self.params.debug:
                print(f"\n⚠️  修复12-单笔亏损限制，缩小仓位:")
                print(f"   原仓位: {size:.0f} -> 新仓位: {max_safe_size:.0f}")
                print(f"   ATR: {current_atr:.5f}")
                print(f"   最大允许亏损: ${max_single_loss:.2f}")
                print(f"   最坏退场距离: {current_atr * ATR_WORST_CASE:.5f} ({ATR_WORST_CASE}x ATR)\n")
            size = max_safe_size
        
        if self.params.debug:
            print(f"\n📐 仓位计算:")
            print(f"   风险金额: ${risk_amount:.2f}")
            print(f"   入场价: {entry_price:.5f}")
            print(f"   止损价: {stop_loss:.5f}")
            print(f"   止损距离: {stop_distance:.5f} ({100*stop_distance/entry_price:.3f}%)")
            print(f"   滑点保护: {SLIPPAGE_PROTECTION}x")
            print(f"   ATR仓位上限: {max_safe_size:.0f} units")
            print(f"   最终仓位: {size:.2f} units ({size/100000:.4f} lots)\n")
        
        # ✅ 修复7: 检查最小手数限制是否会导致过度风险
        # 当理论仓位 < 最小手数时，最终仓位会被强制Round up
        # 这会导致实际风险远超预期，需要跳过这种交易
        min_size = self.params.min_lot * 100000  # 最小0.01手 = 1000 units
        
        if size < min_size:
            # 计算最小仓位下的理论最大亏损（考虑3倍滑点）
            max_loss_with_min_size = min_size * stop_distance * pnl_factor * SLIPPAGE_PROTECTION
            
            # ✅ 加严门槛：如果最小仓位的风险 > 1.5倍理论风险，则跳过
            # Blue Guardian场景下，$20理论 × 1.5 = $30，仍低于$50单笔限制
            if max_loss_with_min_size > risk_amount * 1.5:
                if self.params.debug:
                    print(f"\n⚠️  跳过高风险交易:")
                    print(f"   理论仓位: {size:.0f} units < 最小仓位: {min_size:.0f} units")
                    print(f"   理论风险: ${risk_amount:.2f}")
                    print(f"   最小仓位下风险: ${max_loss_with_min_size:.2f} ({max_loss_with_min_size/risk_amount:.1f}x)")
                    print(f"   → 拒绝交易，保护资金\n")
                return 0  # 不开仓
        
        # ✅ 修复10: 保证金上限检查
        # 确保仓位的保证金不超过可用资金的80%，防止保证金不足导致不可控行为
        MAX_MARGIN_RATIO = 0.80  # 保证金最多用80%的可用资金
        # 间接报价(USDJPY): margin = size / leverage
        # 直接报价(GBPUSD): margin = size * price / leverage
        # 交叉货币对(AUDJPY): margin = size * price * quote_usd_rate / leverage
        LEVERAGE = 30.0
        if self.params.quote_usd_rate > 0:
            margin_needed = size * entry_price * self.params.quote_usd_rate / LEVERAGE
        elif pnl_factor == 1.0 / entry_price:
            # indirect: getvaluesize = abs(size), margin = size / leverage
            margin_needed = size / LEVERAGE
        else:
            margin_needed = size * entry_price / LEVERAGE
        
        max_margin = cash_available * MAX_MARGIN_RATIO
        if margin_needed > max_margin:
            # 缩小仓位到保证金允许范围
            scale = max_margin / margin_needed
            old_size = size
            size = size * scale
            if self.params.debug:
                print(f"\n⚠️  保证金限制，缩小仓位:")
                print(f"   原仓位: {old_size:.0f} -> 新仓位: {size:.0f}")
                print(f"   保证金: ${margin_needed:.2f} -> ${max_margin:.2f} (可用资金{MAX_MARGIN_RATIO*100:.0f}%)\n")
        
        # 转换为手数并限制范围
        lots = size / 100000
        lots = max(self.params.min_lot, min(lots, self.params.max_lot))
        size = lots * 100000
        
        return size
    
    def stop(self):
        """回测结束"""
        if self.params.debug:
            print(f"\n{'='*80}")
            print(f"回测完成")
            print(f"{'='*80}")
            print(f"初始资金: ${10000:.2f}")
            print(f"最终资金: ${self.broker.get_value():.2f}")
            total_return = (self.broker.get_value() - 10000) / 10000 * 100
            print(f"总收益: ${self.broker.get_value() - 10000:.2f} ({total_return:+.2f}%)")
            print(f"实际交易: {self.traded_count} 笔")
            if self.blocked_by_session > 0:
                print(f"市场开盘时段阻止: {self.blocked_by_session} 笔 (悉尼/东京开盘前后15分钟)")
            print(f"{'='*80}\n")
