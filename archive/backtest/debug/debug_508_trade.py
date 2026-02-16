"""
Debug $508亏损交易 - 追踪实际开仓大小
"""

import backtrader as bt
import sys
import os

# 配置UTF-8输出
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader

class PositionDebugStrategy(TrendFilterStrategy):
    """增强的debug策略 - 记录每笔交易的实际仓位"""
    
    def notify_order(self, order):
        """订单状态通知 - 记录实际执行的仓位"""
        if order.status in [order.Completed]:
            if order.isbuy():
                print(f"\n{'='*60}")
                print(f"✅ 买单成交")
                print(f"{'='*60}")
                print(f"成交时间: {self.data.datetime.datetime()}")
                print(f"成交价格: {order.executed.price:.5f}")
                print(f"订单size: {order.size:.0f} units ({order.size/100000:.6f} 标准手)")
                print(f"实际成交: {order.executed.size:.0f} units ({order.executed.size/100000:.6f} 标准手)")
                print(f"持仓价值: ${order.executed.value:.2f}")
                print(f"{'='*60}\n")
                
            elif order.issell():
                print(f"\n{'='*60}")
                print(f"✅ 卖单成交")
                print(f"{'='*60}")
                print(f"成交时间: {self.data.datetime.datetime()}")
                print(f"成交价格: {order.executed.price:.5f}")
                print(f"订单size: {order.size:.0f} units ({order.size/100000:.6f} 标准手)")
                print(f"实际成交: {order.executed.size:.0f} units ({order.executed.size/100000:.6f} 标准手)")
                print(f"持仓价值: ${abs(order.executed.value):.2f}")
                print(f"盈亏: ${order.executed.pnl:.2f}")
                print(f"{'='*60}\n")
        
        super().notify_order(order)
    
    def _calculate_position_size(self, entry_price, stop_loss, short=False):
        """记录仓位计算过程"""
        size = super()._calculate_position_size(entry_price, stop_loss, short)
        
        if size > 0:
            stop_dist = abs(entry_price - stop_loss)
            print(f"\n📊 仓位计算详情:")
            print(f"   入场价: {entry_price:.5f}")
            print(f"   止损价: {stop_loss:.5f}")
            print(f"   止损距: {stop_dist:.5f} ({stop_dist/entry_price*100:.2f}%)")
            print(f"   理论仓位: {size:.0f} units ({size/100000:.6f} 标准手)")
            
            # 检查是否会被round
            if size < 1000:
                print(f"   ⚠️ 小于最小手数1000 units")
            
        return size


def main():
    """只运行USDJPY，查找$508亏损交易"""
    
    print("\n" + "="*60)
    print("Debug $508亏损交易 - USDJPY")
    print("="*60 + "\n")
    
    # 加载数据
    loader = CSVDataLoader(filepath='./data/USD_JPY_M5.csv')
    df = loader.load_data()
    loader.validate_data()
    
    # 配置回测
    cerebro = bt.Cerebro()
    data_feed = loader.to_backtrader_feed()
    cerebro.adddata(data_feed)
    
    # 添加debug策略
    cerebro.addstrategy(
        PositionDebugStrategy,
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
        debug=False  # 关闭策略内部debug，只看Position debug
    )
    
    # 设置资金
    cerebro.broker.set_cash(2478.50)  # 双品种各一半
    
    print(f"初始资金: ${cerebro.broker.get_value():.2f}")
    print(f"开始回测...\n")
    
    # 运行
    cerebro.run()
    
    print(f"\n最终资金: ${cerebro.broker.get_value():.2f}")


if __name__ == '__main__':
    main()
