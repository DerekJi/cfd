"""
专门追踪2025-04-16那笔$508亏损的交易
看止损价是否正确设置
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader


class StopLossTracker(bt.Strategy):
    """继承原策略，添加stop loss追踪"""
    
    params = TrendFilterStrategy.params
    
    def __init__(self):
        # 调用父类初始化
        TrendFilterStrategy.__init__(self)
        self.tracking = False
        
    def next(self):
        # 检测目标时间
        dt = self.data.datetime.datetime()
        
        if dt >= datetime(2025, 4, 16, 22, 50) and dt <= datetime(2025, 4, 17, 1, 0):
            if not self.tracking:
                self.tracking = True
                print(f"\n{'='*80}")
                print(f"开始追踪目标交易区间")
                print(f"{'='*80}\n")
            
            # 显示详细信息
            print(f"{dt} | Price: {self.data.close[0]:.5f} "
                  f"(H:{self.data.high[0]:.5f}, L:{self.data.low[0]:.5f})")
            
            # 显示持仓和止损状态
            if self.position:
                print(f"  持仓: {self.position.size} @ {self.position.price:.5f}")
                if self.stop_loss_price:
                    print(f"  止损价: {self.stop_loss_price:.5f}")
                    print(f"  止损距离: {abs(self.data.close[0] - self.stop_loss_price):.5f}")
                    
                    # 检查是否应该触发
                    if self.position_side == 'short':
                        if self.data.high[0] >= self.stop_loss_price:
                            print(f"  ⚠️ HIGH触及止损！ high={self.data.high[0]:.5f} >= stop={self.stop_loss_price:.5f}")
                        if self.data.close[0] >= self.stop_loss_price:
                            print(f"  ⚠️ CLOSE触及止损！ close={self.data.close[0]:.5f} >= stop={self.stop_loss_price:.5f}")
                else:
                    print(f"  ⚠️⚠️⚠️ 止损价未设置！")
                print()
        
        # 调用父类的next
        TrendFilterStrategy.next(self)


def main():
    print("="*80)
    print("    专门追踪 2025-04-16 $508 亏损交易")
    print("="*80)
    print()
    
    filepath = './data/USD_JPY_M5.csv'
    loader = CSVDataLoader(filepath=filepath)
    df = loader.load_data()
    
    # 只取相关时间段的数据（加快测试）
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
    
    cerebro.addstrategy(
        StopLossTracker,
        up_period=20,
        down_period=20,
        ema50_period=50,
        ema200_period=200,
        adx_period=14,
        adx_threshold=35,
        atr_period=14,
        analysis_bars=5,
        pullback_wait_bars=20,
        total_account_size=5000.0,
        risk_percent=0.8,
        num_symbols=2,
        debug=False  # 关闭常规debug
    )
    
    cerebro.broker.set_cash(2478.5)
    
    print("运行回测...")
    results = cerebro.run()
    
    print()
    print("="*80)
    print(f"最终资金: ${cerebro.broker.get_value():,.2f}")
    print("="*80)


if __name__ == '__main__':
    main()
