"""
趋势过滤突破策略 V1.1 - Blue Guardian版本

专为严格资金管理规则优化：
- 风险计算基于固定初始资金（而非当前账户价值）
- 防止复利导致的仓位失控
"""

import backtrader as bt
from strategies.range_detector import DonchianRangeDetector
from indicators.atr_buffer import ATRBuffer
from indicators.adx_indicator import ADX
from indicators.trend_filter_fsm import TrendFilterStateMachine


class TrendFilterStrategyBlueGuardian(bt.Strategy):
    """
    趋势过滤突破策略 - Blue Guardian专用版
    
    关键改进：
    - 风险计算基于initial_capital（固定），而非current_value（浮动）
    - 确保单笔亏损永远 ≤ initial_capital × risk_percent
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
        
        # 风险管理 - Blue Guardian专用
        ('initial_capital', 2478.5),  # 固定初始资金（每个品种分配）
        ('risk_percent', 0.8),        # 风险百分比（基于初始资金）
        ('max_single_loss', 50.0),    # 单笔最大亏损限制（$）
        ('min_lot', 0.01),
        ('max_lot', 10.0),
        
        # 调试
        ('debug', True),
    )
    
    def __init__(self):
        """初始化策略"""
        # 指标
        self.range_detector = DonchianRangeDetector(
            self.data,
            lookback=self.params.up_period
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
        self.position_entry_bar = None
        self.current_entry_price = None
        self.current_stop_loss = None
        self.stop_order = None
        
        # 统计
        self.traded_count = 0
        
        if self.params.debug:
            print(f"\n{'='*80}")
            print(f"策略初始化 - Blue Guardian版本")
            print(f"{'='*80}")
            print(f"固定初始资金: ${self.params.initial_capital:.2f}")
            print(f"风险管理: {self.params.risk_percent}% (基于初始资金)")
            print(f"单笔最大风险: ${self.params.initial_capital * self.params.risk_percent / 100:.2f}")
            print(f"硬性止损限制: ${self.params.max_single_loss:.2f}")
            print(f"ADX阈值: {self.params.adx_threshold}")
            print(f"{'='*80}\n")
    
    def next(self):
        """每根K线执行"""
        # 更新状态机
        current_state = self.fsm.update(
            close=self.data.close[0],
            high=self.data.high[0],
            low=self.data.low[0],
            ema50=self.ema50[0],
            ema200=self.ema200[0],
            adx=self.adx.adx[0],
            donchian_up=self.range_detector.up_line[0],
            donchian_down=self.range_detector.down_line[0],
        )
        
        # 跳过等待订单执行的情况
        if self.order:
            return
        
        # 已有持仓时的止损管理
        if self.position:
            self._update_trailing_stop()
            return
        
        # 更新状态机
        entry_signal = self.fsm.get_entry_signal()
        
        if entry_signal == 'LONG':
            self._enter_long()
        elif entry_signal == 'SHORT':
            self._enter_short()
    
    def _enter_long(self):
        """开多单"""
        entry_price = self.data.close[0]
        
        # 使用EMA50作为初始止损
        stop_loss = self.ema50[0]
        
        # 确保止损合理
        stop_distance_pct = (entry_price - stop_loss) / entry_price
        if stop_distance_pct < 0.002 or stop_distance_pct > 0.05:
            if self.params.debug:
                print(f"[{self.data.datetime.datetime()}] ⚠️  止损距离不合理: {stop_distance_pct*100:.2f}%, 取消开仓")
            return
        
        # 计算仓位
        size = self._calculate_position_size(entry_price, stop_loss, short=False)
        
        if size > 0:
            # 下单
            self.order = self.buy(size=size, exectype=bt.Order.Market)
            self.current_entry_price = entry_price
            self.current_stop_loss = stop_loss
            self.traded_count += 1
            
            if self.params.debug:
                risk_dollars = self.params.initial_capital * (self.params.risk_percent / 100)
                print(f"\n[{self.data.datetime.datetime()}] 📈 开多单")
                print(f"入场价: {entry_price:.5f}")
                print(f"止损价: {stop_loss:.5f}")
                print(f"止损距离: {(entry_price - stop_loss):.5f} ({stop_distance_pct*100:.2f}%)")
                print(f"仓位: {size:.0f}")
                print(f"风险金额: ${risk_dollars:.2f} ({self.params.risk_percent:.1f}% of ${self.params.initial_capital:.2f})")
    
    def _enter_short(self):
        """开空单"""
        entry_price = self.data.close[0]
        
        # 使用EMA50作为初始止损
        stop_loss = self.ema50[0]
        
        # 确保止损合理
        stop_distance_pct = (stop_loss - entry_price) / entry_price
        if stop_distance_pct < 0.002 or stop_distance_pct > 0.05:
            if self.params.debug:
                print(f"[{self.data.datetime.datetime()}] ⚠️  止损距离不合理: {stop_distance_pct*100:.2f}%, 取消开仓")
            return
        
        # 计算仓位
        size = self._calculate_position_size(entry_price, stop_loss, short=True)
        
        if size > 0:
            # 下单
            self.order = self.sell(size=size, exectype=bt.Order.Market)
            self.current_entry_price = entry_price
            self.current_stop_loss = stop_loss
            self.traded_count += 1
            
            if self.params.debug:
                risk_dollars = self.params.initial_capital * (self.params.risk_percent / 100)
                print(f"\n[{self.data.datetime.datetime()}] 📉 开空单")
                print(f"入场价: {entry_price:.5f}")
                print(f"止损价: {stop_loss:.5f}")
                print(f"止损距离: {(stop_loss - entry_price):.5f} ({stop_distance_pct*100:.2f}%)")
                print(f"仓位: {size:.0f}")
                print(f"风险金额: ${risk_dollars:.2f} ({self.params.risk_percent:.1f}% of ${self.params.initial_capital:.2f})")
    
    def _update_trailing_stop(self):
        """更新移动止损"""
        if not self.position:
            return
        
        # 使用EMA50作为移动止损
        new_stop = self.ema50[0]
        
        if self.position.size > 0:  # 多头
            # 只向有利方向移动止损
            if new_stop > self.current_stop_loss:
                self.current_stop_loss = new_stop
            
            # 检查是否触发止损
            if self.data.close[0] < self.current_stop_loss:
                if self.params.debug:
                    print(f"\n[{self.data.datetime.datetime()}] ⛔ 多头止损")
                    print(f"当前价: {self.data.close[0]:.5f}")
                    print(f"止损价: {self.current_stop_loss:.5f}")
                self.order = self.close()
        
        elif self.position.size < 0:  # 空头
            # 只向有利方向移动止损
            if new_stop < self.current_stop_loss:
                self.current_stop_loss = new_stop
            
            # 检查是否触发止损
            if self.data.close[0] > self.current_stop_loss:
                if self.params.debug:
                    print(f"\n[{self.data.datetime.datetime()}] ⛔ 空头止损")
                    print(f"当前价: {self.data.close[0]:.5f}")
                    print(f"止损价: {self.current_stop_loss:.5f}")
                self.order = self.close()
    
    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status == order.Completed:
            if order.isbuy():
                self.position_entry_bar = len(self)
                if self.params.debug:
                    print(f"执行价: {order.executed.price:.5f}")
            elif order.issell():
                self.position_entry_bar = len(self)
                if self.params.debug:
                    print(f"执行价: {order.executed.price:.5f}")
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.params.debug:
                print(f"订单失败: {order.status}")
        
        self.order = None
    
    def notify_trade(self, trade):
        """交易通知"""
        if trade.isclosed:
            if self.params.debug:
                print(f"\n{'='*60}")
                print(f"交易关闭:")
                print(f"  盈亏: ${trade.pnl:+.2f} ({trade.pnlcomm:+.2f} 含手续费)")
                print(f"  基于初始资金${ self.params.initial_capital:.2f}的百分比: {trade.pnl/self.params.initial_capital*100:+.2f}%")
                print(f"  当前账户: ${self.broker.get_value():.2f}")
                print(f"{'='*60}\n")
            
            # 重置持仓相关变量
            self.current_entry_price = None
            self.current_stop_loss = None
            self.position_entry_bar = None
    
    def _calculate_position_size(self, entry_price, stop_loss, short=False):
        """
        计算仓位大小 - Blue Guardian版本
        
        关键改进：使用fixed initial_capital而非current account value
        """
        # 🔴 关键修复：使用固定初始资金，而非当前账户价值
        risk_amount = self.params.initial_capital * (self.params.risk_percent / 100)
        
        # 硬性限制：不超过max_single_loss
        risk_amount = min(risk_amount, self.params.max_single_loss)
        
        # 计算止损距离
        if short:
            stop_distance = stop_loss - entry_price
        else:
            stop_distance = entry_price - stop_loss
        
        # 防止止损距离为0或负数
        if stop_distance <= 0:
            return 0
        
        # 基于风险计算仓位
        size = risk_amount / stop_distance
        
        # 检查实际可用资金
        cash_available = self.broker.get_cash()
        required_margin = size * entry_price
        
        if required_margin > cash_available:
            # 资金不足，按可用资金计算
            size = (cash_available * 0.95) / entry_price
        
        # 转换为手数并限制范围
        lots = size / 100000
        lots = max(self.params.min_lot, min(lots, self.params.max_lot))
        size = lots * 100000
        
        return size
    
    def stop(self):
        """回测结束"""
        if self.params.debug:
            print(f"\n{'='*80}")
            print(f"回测完成 - Blue Guardian版本")
            print(f"{'='*80}")
            print(f"初始资金: ${self.params.initial_capital:.2f}")
            print(f"最终资金: ${self.broker.get_value():.2f}")
            total_return = (self.broker.get_value() - self.params.initial_capital) / self.params.initial_capital * 100
            print(f"总收益: ${self.broker.get_value() - self.params.initial_capital:.2f} ({total_return:+.2f}%)")
            print(f"实际交易: {self.traded_count} 笔")
            print(f"{'='*80}\n")
