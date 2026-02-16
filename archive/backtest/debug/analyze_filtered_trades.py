#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查找被过滤的USDJPY交易详情
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from datetime import datetime

class DebugFilterStrategy(bt.Strategy):
    params = (
        ('total_account_size', 5000.0),
        ('risk_percent', 0.8),
        ('num_symbols', 2),
        ('min_lot', 0.01),
        ('target_month', 2),  # 2026年2月
        ('target_year', 2026),
    )
    
    def __init__(self):
        self.filtered_trades = []
        self.ema50 = bt.indicators.EMA(self.data.close, period=50)
        
        from indicators.atr_buffer import ATRBuffer
        self.atr = ATRBuffer(self.data, period=14, buffer_multiplier=0.2)
    
    def _is_market_open_session(self, dt):
        """检查市场开盘时段"""
        hour = dt.hour
        minute = dt.minute
        time_minutes = hour * 60 + minute
        
        # 东京开盘: 23:45-00:15 UTC
        tokyo_open = 0
        if (time_minutes >= tokyo_open - 15 and time_minutes <= tokyo_open + 15) or \
           (time_minutes >= 1440 - 15):
            return True, "东京开盘"
        
        # 悉尼开盘: 20:45-21:15 UTC
        sydney_open = 21 * 60
        if time_minutes >= sydney_open - 15 and time_minutes <= sydney_open + 15:
            return True, "悉尼开盘"
        
        return False, None
    
    def next(self):
        dt = self.data.datetime.datetime(0)
        
        # 只关注目标月份
        if dt.year != self.params.target_year or dt.month != self.params.target_month:
            return
        
        # 模拟一个简单的突破信号（实际策略更复杂）
        # 这里简化：每当价格突破5分钟高点就假设有入场信号
        if len(self) < 20:
            return
        
        # 模拟做空信号（价格在EMA50上方）
        if self.data.close[0] > self.ema50[0]:
            entry_price = self.data.close[0]
            ema50 = self.ema50[0]
            atr = self.atr.atr[0]
            
            # 计算止损（做空：EMA50 + 1*ATR）
            stop_loss = ema50 + atr * 1.0
            stop_distance = stop_loss - entry_price
            
            if stop_distance <= 0:
                return
            
            # 计算仓位
            risk_amount = (self.params.total_account_size * self.params.risk_percent / 100) / self.params.num_symbols
            
            # 3倍滑点保护
            SLIPPAGE_PROTECTION = 3.0
            size = risk_amount / (stop_distance * SLIPPAGE_PROTECTION)
            
            # 检查最小手数限制
            min_size = self.params.min_lot * 100000  # 1000 units
            
            if size < min_size:
                # 计算最小仓位下的风险
                max_loss_with_min_size = min_size * stop_distance * SLIPPAGE_PROTECTION
                
                # 检查是否超过1.5倍风险
                filter_reason = None
                if max_loss_with_min_size > risk_amount * 1.5:
                    filter_reason = f"最小手数风险验证"
                
                # 检查市场开盘时段
                is_blocked, session_name = self._is_market_open_session(dt)
                if is_blocked and filter_reason is None:
                    filter_reason = f"{session_name}开盘时段"
                
                if filter_reason:
                    self.filtered_trades.append({
                        'datetime': dt,
                        'entry_price': entry_price,
                        'stop_loss': stop_loss,
                        'stop_distance': stop_distance,
                        'ema50': ema50,
                        'atr': atr,
                        'theoretical_size': size,
                        'min_size': min_size,
                        'risk_amount': risk_amount,
                        'max_loss_with_min_size': max_loss_with_min_size,
                        'risk_multiplier': max_loss_with_min_size / risk_amount,
                        'reason': filter_reason,
                        'session_blocked': is_blocked,
                    })

print("="*80)
print("查找被过滤的USDJPY交易（2026年2月）")
print("="*80)
print()

# 加载数据
from utils.data_loader import CSVDataLoader
loader = CSVDataLoader(filepath='./data/USD_JPY_M5.csv')
df = loader.load_data()

if not loader.validate_data():
    print("数据验证失败")
    sys.exit(1)

print(f"✓ 数据加载成功: {len(df)} 根K线")
print(f"  时间范围: {df.index[0]} 至 {df.index[-1]}")
print()

# 设置回测
cerebro = bt.Cerebro()
data_feed = loader.to_backtrader_feed()
cerebro.adddata(data_feed, name='USDJPY')

cerebro.addstrategy(DebugFilterStrategy)
cerebro.broker.set_cash(2478.50)

print("运行分析...")
results = cerebro.run()
strat = results[0]

print()
print("="*80)
print(f"找到 {len(strat.filtered_trades)} 笔被过滤的交易")
print("="*80)
print()

if len(strat.filtered_trades) == 0:
    print("没有找到被过滤的交易（可能信号条件太简化）")
    print("建议：运行完整策略的debug模式查看实际过滤情况")
else:
    # 只显示前10笔
    display_count = min(10, len(strat.filtered_trades))
    print(f"显示前 {display_count} 笔被过滤的交易:")
    print()
    
    for i, trade in enumerate(strat.filtered_trades[:display_count], 1):
        print(f"{'='*80}")
        print(f"被过滤交易 #{i}")
        print(f"{'='*80}")
        print(f"时间: {trade['datetime'].strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"过滤原因: {trade['reason']}")
        if trade['session_blocked']:
            print(f"  → 在市场开盘高波动时段（前后15分钟）")
        print()
        print(f"价格信息:")
        print(f"  入场价格: {trade['entry_price']:.5f}")
        print(f"  止损价格: {trade['stop_loss']:.5f}")
        print(f"  止损距离: {trade['stop_distance']:.5f} ({(trade['stop_distance']/trade['entry_price'])*100:.2f}%)")
        print(f"  EMA50: {trade['ema50']:.5f}")
        print(f"  ATR: {trade['atr']:.5f}")
        print()
        print(f"仓位计算:")
        print(f"  风险金额: ${trade['risk_amount']:.2f}")
        print(f"  理论仓位: {trade['theoretical_size']:.2f} units ({trade['theoretical_size']/100000:.6f} 标准手)")
        print(f"  最小仓位: {trade['min_size']:.0f} units ({trade['min_size']/100000:.2f} 标准手)")
        print(f"  最小仓位下风险: ${trade['max_loss_with_min_size']:.2f}")
        print(f"  风险放大倍数: {trade['risk_multiplier']:.2f}x")
        print()
        print(f"判断:")
        print(f"  理论风险 × 1.5 = ${trade['risk_amount'] * 1.5:.2f}")
        print(f"  实际风险 = ${trade['max_loss_with_min_size']:.2f}")
        if trade['max_loss_with_min_size'] > trade['risk_amount'] * 1.5:
            print(f"  → ${trade['max_loss_with_min_size']:.2f} > ${trade['risk_amount'] * 1.5:.2f} (超过1.5倍)")
            print(f"  → 交易被拒绝 ✗")
        print()

print("="*80)
print("说明")
print("="*80)
print("注意：上述分析使用简化的信号逻辑（价格>EMA50即假设有做空信号）")
print("实际策略信号更复杂（需要突破、ADX、EMA200等多重条件）")
print()
print("如需查看实际策略的过滤详情，请运行:")
print("  python test_session_filter_effect.py")
print("  （开启debug=True可看到每笔过滤的详细信息）")
print("="*80)
