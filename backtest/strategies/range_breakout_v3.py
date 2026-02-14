"""
半自动交易策略 V3.0 - 主策略类
Range Breakout Strategy with 5-State Machine
"""

import backtrader as bt
import sys
import os

# 添加路径以导入自定义模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators.state_machine import StateMachine, TradingState
from indicators.atr_buffer import ATRBuffer
from strategies.range_detector import DonchianRangeDetector


class RangeBreakoutStrategy(bt.Strategy):
    """
    趋势回调突破策略 V3.0
    
    基于5状态机的震荡区间突破策略
    """
    
    params = (
        # UP/DOWN线检测参数
        ('lookback_period', 20),
        ('update_frequency', 5),
        
        # ATR和Buffer参数
        ('atr_period', 14),
        ('buffer_multiplier', 0.2),
        
        # 状态机参数
        ('confirm_bars', 1),  # 突破确认K线数
        ('max_wait_bars', 6),  # 最大等待K线数（30分钟）
        ('trailing_stop', True),  # 是否启用移动止损
        
        # 风险管理参数
        ('position_size', 100000),  # 仓位大小（1标准手）
        ('spread_pips', 1.0),  # 点差
        
        # 调试参数
        ('debug', True),  # 是否打印调试信息
    )
    
    def __init__(self):
        """初始化策略"""
        # 1. 初始化指标
        self.range_detector = DonchianRangeDetector(
            self.data,
            lookback=self.params.lookback_period,
            update_freq=self.params.update_frequency
        )
        
        self.atr_buffer = ATRBuffer(
            self.data,
            period=self.params.atr_period,
            buffer_multiplier=self.params.buffer_multiplier
        )
        
        # 2. 初始化状态机
        self.state_machine = StateMachine(
            confirm_bars=self.params.confirm_bars,
            max_wait_bars=self.params.max_wait_bars,
            trailing_stop=self.params.trailing_stop
        )
        
        # 3. 交易记录
        self.order = None
        self.bar_counter = 0
        self.trades_log = []
        
        # 4. 性能指标
        self.start_cash = self.broker.get_cash()
        self.peak_value = self.start_cash
        self.max_drawdown = 0
        
        if self.params.debug:
            print("\n" + "="*60)
            print("策略初始化完成")
            print("="*60)
            print(f"初始资金: ${self.start_cash:,.2f}")
            print(f"UP/DOWN检测周期: {self.params.lookback_period} 根K线")
            print(f"ATR周期: {self.params.atr_period}")
            print(f"Buffer系数: {self.params.buffer_multiplier}")
            print(f"突破确认: {self.params.confirm_bars} 根K线")
            print(f"最大等待: {self.params.max_wait_bars} 根K线")
            print("="*60 + "\n")
    
    def next(self):
        """每根K线调用一次"""
        self.bar_counter += 1
        
        # 获取当前数据
        current_time = self.data.datetime.datetime(0)
        high = self.data.high[0]
        low = self.data.low[0]
        close = self.data.close[0]
        
        # 获取UP/DOWN线和ATR
        up_line = self.range_detector.up_line[0]
        down_line = self.range_detector.down_line[0]
        buffer = self.atr_buffer.buffer[0]
        atr = self.atr_buffer.atr[0]
        
        # 更新状态机的区间数据
        self.state_machine.update_range_data(up_line, down_line, buffer, atr)
        
        # 处理状态机
        action = self.state_machine.process(
            current_time, self.bar_counter, high, low, close
        )
        
        # 调试输出
        if self.params.debug and self.bar_counter % 100 == 0:
            state_info = self.state_machine.get_current_state()
            print(f"[Bar {self.bar_counter}] {current_time} | "
                  f"Price: {close:.5f} | State: {state_info['state']} | "
                  f"UP: {up_line:.5f} | DOWN: {down_line:.5f}")
        
        # 执行动作
        if action['action'] == 'entry':
            self._execute_entry(action)
        
        elif action['action'] == 'exit':
            self._execute_exit(action)
        
        elif action['action'] == 'update_stop':
            if self.params.debug:
                print(f"  └─ {action.get('message', '')}")
        
        # 打印状态转换信息
        if action.get('state_changed') and self.params.debug:
            print(f"\n[Bar {self.bar_counter}] {current_time}")
            print(f"  Price: {close:.5f}")
            print(f"  {action.get('message', '状态转换')}")
    
    def _execute_entry(self, action):
        """执行入场"""
        if self.position:
            # 已有持仓，不重复开仓
            return
        
        # 开多单
        size = self.params.position_size / self.data.close[0]
        self.order = self.buy(size=size)
        
        if self.params.debug:
            print(f"\n{'='*60}")
            print(f"🔺 做多入场")
            print(f"{'='*60}")
            print(f"入场价格: {action['entry_price']:.5f}")
            print(f"止损价格: {action['stop_loss']:.5f}")
            print(f"仓位大小: {size:.2f}")
            print(f"风险: {(action['entry_price'] - action['stop_loss']) / action['entry_price'] * 100:.2f}%")
            print(f"{'='*60}\n")
    
    def _execute_exit(self, action):
        """执行出场"""
        if not self.position:
            return
        
        # 平仓
        self.order = self.close()
        
        if self.params.debug:
            entry_price = self.state_machine.state_data.entry_price
            exit_price = action['exit_price']
            pnl = (exit_price - entry_price) / entry_price * 100
            
            print(f"\n{'='*60}")
            print(f"🔻 平仓出场")
            print(f"{'='*60}")
            print(f"入场价格: {entry_price:.5f}")
            print(f"出场价格: {exit_price:.5f}")
            print(f"盈亏: {pnl:+.2f}%")
            print(f"{'='*60}\n")
    
    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                if self.params.debug:
                    print(f"  ✓ 买单执行: 价格 {order.executed.price:.5f}, "
                          f"数量 {order.executed.size:.2f}, "
                          f"手续费 {order.executed.comm:.2f}")
            
            elif order.issell():
                if self.params.debug:
                    print(f"  ✓ 卖单执行: 价格 {order.executed.price:.5f}, "
                          f"数量 {order.executed.size:.2f}, "
                          f"手续费 {order.executed.comm:.2f}")
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.params.debug:
                print(f"  ✗ 订单失败: {order.status}")
        
        self.order = None
    
    def notify_trade(self, trade):
        """交易完成通知"""
        if not trade.isclosed:
            return
        
        # 记录交易
        pnl_percent = (trade.pnl / self.start_cash) * 100
        self.trades_log.append({
            'bar': self.bar_counter,
            'time': self.data.datetime.datetime(0),
            'pnl': trade.pnl,
            'pnl_net': trade.pnlcomm,
            'pnl_percent': pnl_percent
        })
        
        if self.params.debug:
            print(f"  └─ 交易完成: 盈亏 ${trade.pnlcomm:+.2f} ({pnl_percent:+.2f}%)")
        
        # 更新最大回撤
        current_value = self.broker.get_value()
        if current_value > self.peak_value:
            self.peak_value = current_value
        drawdown = (self.peak_value - current_value) / self.peak_value
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
    
    def stop(self):
        """策略结束时调用"""
        final_value = self.broker.get_value()
        total_return = (final_value - self.start_cash) / self.start_cash * 100
        
        print("\n" + "="*60)
        print("回测完成")
        print("="*60)
        print(f"初始资金: ${self.start_cash:,.2f}")
        print(f"最终资金: ${final_value:,.2f}")
        print(f"总收益: ${final_value - self.start_cash:+,.2f} ({total_return:+.2f}%)")
        print(f"总交易: {len(self.trades_log)} 笔")
        
        if self.trades_log:
            winning_trades = [t for t in self.trades_log if t['pnl'] > 0]
            losing_trades = [t for t in self.trades_log if t['pnl'] <= 0]
            
            win_rate = len(winning_trades) / len(self.trades_log) * 100
            
            avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
            profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            
            print(f"胜率: {win_rate:.1f}% ({len(winning_trades)}/{len(self.trades_log)})")
            print(f"平均盈利: ${avg_win:+.2f}")
            print(f"平均亏损: ${avg_loss:+.2f}")
            print(f"盈亏比: {profit_factor:.2f}")
        
        print(f"最大回撤: {self.max_drawdown * 100:.2f}%")
        print("="*60 + "\n")


if __name__ == '__main__':
    print("Range Breakout Strategy - Ready")
    print("使用方法: 在 run_backtest.py 中调用此策略")
