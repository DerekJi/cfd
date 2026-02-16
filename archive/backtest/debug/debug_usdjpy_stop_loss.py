"""
深度调试：追踪USDJPY的止损价计算和触发

目标：找出2025-04-16那笔$508亏损为何发生
关键疑问：
1. 止损价是如何计算的？
2. 是否正确设置？
3. 为何没有触发？
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from utils.data_loader import CSVDataLoader


# 创建简化的debug策略
class DebugStrategy(bt.Strategy):
    params = (
        ('total_account_size', 5000.0),
        ('risk_percent', 0.8),
        ('num_symbols', 2),
    )
    
    def __init__(self):
        self.order = None
        self.pending_entry_info = None
        self.stop_loss_price = None
        self.position_side = None
        self.entry_price = None
        
        # 简化指标
        self.ema50 = bt.indicators.EMA(self.data.close, period=50)
        self.ema200 = bt.indicators.EMA(self.data.close, period=200)
        
        from indicators.adx_indicator import ADX
        self.adx = ADX(self.data, period=14)
        
        from indicators.atr_buffer import ATRBuffer
        self.atr = ATRBuffer(self.data, period=14, buffer_multiplier=0.2)
        
        self.target_entry_time = datetime(2025, 4, 16, 22, 55)
        self.in_target_zone = False
        
    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                print(f"  ✓ 买单执行: {order.executed.price:.5f}, size: {order.executed.size:.0f}")
                if self.pending_entry_info and self.pending_entry_info['side'] == 'long':
                    self.entry_price = order.executed.price
                    self.stop_loss_price = self.pending_entry_info['stop_loss']
                    self.position_side = 'long'
                    print(f"  ✅ 多头止损设置: {self.stop_loss_price:.5f}")
                    self.pending_entry_info = None
                    
            elif order.issell():
                print(f"  ✓ 卖单执行: {order.executed.price:.5f}, size: {order.executed.size:.0f}")
                if self.pending_entry_info and self.pending_entry_info['side'] == 'short':
                    self.entry_price = order.executed.price
                    self.stop_loss_price = self.pending_entry_info['stop_loss']
                    self.position_side = 'short'
                    print(f"  ✅ 空头止损设置: {self.stop_loss_price:.5f} (entry={self.entry_price:.5f})")
                    print(f"     止损距离: {abs(self.stop_loss_price - self.entry_price):.5f}")
                    self.pending_entry_info = None
            
            if not self.position:
                self.stop_loss_price = None
                self.position_side = None
                self.entry_price = None
        
        self.order = None
    
    def notify_trade(self, trade):
        if trade.isclosed:
            pnl_pct = (trade.pnlcomm / 5000) * 100
            print(f"  💰 交易完成: ${trade.pnlcomm:+,.2f} ({pnl_pct:+.2f}%)")
    
    def next(self):
        dt = self.data.datetime.datetime()
        
        # 进入目标时间区域
        if dt >= datetime(2025, 4, 16, 22, 50) and dt <= datetime(2025, 4, 17, 0, 30):
            if not self.in_target_zone:
                self.in_target_zone = True
                print(f"\n{'='*80}")
                print(f"进入目标时间区域")
                print(f"{'='*80}\n")
            
            # 显示每根K线的详细信息
            print(f"{dt} | C:{self.data.close[0]:.5f} H:{self.data.high[0]:.5f} L:{self.data.low[0]:.5f}")
            print(f"   EMA50:{self.ema50[0]:.5f} EMA200:{self.ema200[0]:.5f} ADX:{self.adx.adx[0]:.2f} ATR:{self.atr.atr[0]:.5f}")
            
            if self.position:
                print(f"   持仓: {self.position.size} @ {self.position.price:.5f}")
                if self.stop_loss_price:
                    distance_from_stop = self.data.close[0] - self.stop_loss_price if self.position_side == 'short' else self.stop_loss_price - self.data.close[0]
                    print(f"   止损价: {self.stop_loss_price:.5f} (距离: {distance_from_stop:.5f})")
                    
                    # 检查是否应该触发
                    if self.position_side == 'short':
                        if self.data.high[0] >= self.stop_loss_price:
                            print(f"   🚨 应该触发止损！ high={self.data.high[0]:.5f} >= stop={self.stop_loss_price:.5f}")
            print()
        
        # 止损检查
        if self.position and self.stop_loss_price and not self.order:
            if self.position_side == 'short' and self.data.high[0] >= self.stop_loss_price:
                print(f"⛔ 触发硬止损！ high:{self.data.high[0]:.5f} >= stop:{self.stop_loss_price:.5f}")
                self.order = self.close()
                return
        
        # 简单的入场逻辑（模拟突破）
        if not self.position and not self.order:
            # 只在目标时间附近交易
            if dt == self.target_entry_time:
                # 模拟卖空入场
                entry_price = self.data.close[0]
                
                # 计算止损价（基于ATR）
                atr = self.atr.atr[0]
                ema50 = self.ema50[0]
                
                # FSM的止损逻辑：EMA50 + 1*ATR
                stop_loss = ema50 + atr * 1.0
                
                print(f"\n{'='*80}")
                print(f"🔻 模拟卖空入场")
                print(f"{'='*80}")
                print(f"入场价: {entry_price:.5f}")
                print(f"EMA50: {ema50:.5f}")
                print(f"ATR: {atr:.5f}")
                print(f"计算止损价: EMA50 + 1*ATR = {ema50:.5f} + {atr:.5f} = {stop_loss:.5f}")
                print(f"止损距离: {stop_loss - entry_price:.5f} ({((stop_loss - entry_price)/entry_price)*100:.2f}%)")
                print(f"{'='*80}\n")
                
                # 计算仓位
                risk_amount = (self.params.total_account_size * self.params.risk_percent / 100) / self.params.num_symbols
                stop_distance = stop_loss - entry_price
                
                if stop_distance > 0:
                    size = risk_amount / stop_distance
                    lots = size / 100000
                    lots = max(0.01, min(lots, 10.0))
                    size = lots * 100000
                    
                    print(f"风险金额: ${risk_amount:.2f}")
                    print(f"止损距离: {stop_distance:.5f}")
                    print(f"理论仓位: {size:.0f} ({lots:.2f} lots)")
                    print(f"理论最大亏损: ${size * stop_distance:.2f}")
                    print()
                    
                    self.order = self.sell(size=size)
                    self.pending_entry_info = {
                        'stop_loss': stop_loss,
                        'side': 'short'
                    }


def main():
    print("="*80)
    print("    USDJPY 止损价计算追踪")
    print("="*80)
    print()
    
    filepath = './data/USD_JPY_M5.csv'
    loader = CSVDataLoader(filepath=filepath)
    df = loader.load_data()
    
    # 只取相关时间段
    df = df.loc['2025-02-01':'2025-04-20']
    
    print(f"数据: {len(df)} 根K线")
    print()
    
    cerebro = bt.Cerebro()
    
    from backtrader.feeds import PandasData
    data_feed = PandasData(
        dataname=df,
        datetime=None,
        open='open',
        high='high',
        low='low',
        close='close',
        volume='volume',
        openinterest=-1
    )
    
    cerebro.adddata(data_feed)
    cerebro.addstrategy(DebugStrategy)
    cerebro.broker.set_cash(2478.5)
    
    print("运行回测...")
    print()
    results = cerebro.run()
    
    print()
    print("="*80)
    print(f"最终资金: ${cerebro.broker.get_value():,.2f}")
    print("="*80)


if __name__ == '__main__':
    main()
