#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试市场开盘时段过滤功能的实际效果
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置编码
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader

print("="*80)
print("市场开盘时段过滤 - 实际回测测试")
print("="*80)
print()

# 加载USDJPY数据
loader = CSVDataLoader(filepath='./data/USD_JPY_M5.csv')
df = loader.load_data()

if not loader.validate_data():
    print("数据验证失败")
    sys.exit(1)

print(f"✓ 数据加载成功: {len(df)} 根K线")
print(f"  时间范围: {df.index[0]} 至 {df.index[-1]}")
print()

# 配置回测
cerebro = bt.Cerebro()
data_feed = loader.to_backtrader_feed()
cerebro.adddata(data_feed, name='USDJPY')

# 添加策略（开启debug模式）
cerebro.addstrategy(
    TrendFilterStrategy,
    total_account_size=5000.0,
    risk_percent=0.8,
    num_symbols=2,
    debug=True  # 开启debug查看详细信息
)

cerebro.broker.set_cash(2478.50)

print("运行回测...")
print()
results = cerebro.run()

final_value = cerebro.broker.get_value()
strat = results[0]

print()
print("="*80)
print("统计结果")
print("="*80)
print(f"初始资金: $2,478.50")
print(f"最终资金: ${final_value:.2f}")
print(f"盈亏: ${final_value - 2478.50:.2f}")
print()
print(f"实际交易: {strat.traded_count} 笔")
print(f"市场开盘时段阻止: {strat.blocked_by_session} 笔")
print()
print("过滤效果:")
if strat.blocked_by_session > 0:
    print(f"  ✅ 成功阻止了 {strat.blocked_by_session} 笔可能在高波动时段开仓的交易")
    print(f"  ✅ 这些交易可能面临类似USDJPY $614的跳空风险")
else:
    print(f"  ℹ️  本次回测期间没有在市场开盘时段的入场信号")
print("="*80)
