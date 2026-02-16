"""
简化调试：只测试USDJPY，开启debug模式
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader


def main():
    print("="*80)
    print("    USDJPY Debug 测试（只运行前1000根K线）")
    print("="*80)
    print()
    
    filepath = './data/USD_JPY_M5.csv'
    loader = CSVDataLoader(filepath=filepath)
    df = loader.load_data()
    
    # 只取前1000根K线进行快速测试
    df = df.iloc[:1000]
    
    print(f"数据: {len(df)} 根K线")
    print()
    
    cerebro = bt.Cerebro()
    
    # 手动创建datafeed
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
        TrendFilterStrategy,
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
        risk_percent=1.0,
        num_symbols=1,  # 单品种测试
        debug=True  # 开启debug
    )
    
    cerebro.broker.set_cash(5000.0)
    
    print("运行回测...")
    print()
    results = cerebro.run()
    
    print()
    print("="*80)
    print(f"最终资金: ${cerebro.broker.get_value():,.2f}")
    print("="*80)


if __name__ == '__main__':
    main()
