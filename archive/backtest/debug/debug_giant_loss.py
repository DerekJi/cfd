"""
详细调试：分析$4768巨额亏损
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


class DetailedDebugAnalyzer(bt.Analyzer):
    """详细记录每笔交易和订单"""
    
    def __init__(self):
        self.orders = []
        self.trades = []
        self.positions_history = []
        
    def prenext(self):
        self._record_position()
    
    def next(self):
        self._record_position()
    
    def _record_position(self):
        """记录持仓历史"""
        if self.strategy.position:
            self.positions_history.append({
                'datetime': self.strategy.datetime.datetime(),
                'size': self.strategy.position.size,
                'price': self.strategy.position.price,
                'value': self.strategy.broker.get_value(),
            })
    
    def notify_order(self, order):
        """记录所有订单"""
        self.orders.append({
            'ref': order.ref,
            'created_dt': bt.num2date(order.created.dt) if order.created.dt else None,
            'executed_dt': bt.num2date(order.executed.dt) if order.executed.dt else None,
            'is_buy': order.isbuy(),
            'exectype': order.exectype,
            'price': order.price if hasattr(order, 'price') else None,
            'executed_price': order.executed.price if order.executed and order.executed.price else None,
            'size': order.size if hasattr(order, 'size') else None,
            'executed_size': order.executed.size if order.executed and order.executed.size else None,
            'status': order.getstatusname(),
        })
        
    def notify_trade(self, trade):
        """记录交易"""
        if trade.isclosed:
            self.trades.append({
                'ref': trade.ref,
                'open_dt': bt.num2date(trade.dtopen),
                'close_dt': bt.num2date(trade.dtclose),
                'pnl': trade.pnl,
                'pnlcomm': trade.pnlcomm,
            })
    
    def get_analysis(self):
        return {
            'orders': self.orders,
            'trades': self.trades,
            'positions': self.positions_history,
        }


def main():
    print("="*80)
    print("     USDJPY 巨额亏损调试")
    print("="*80)
    print()
    
    filepath = './data/USD_JPY_M5.csv'
    if not os.path.exists(filepath):
        print(f"数据文件不存在: {filepath}")
        return
    
    loader = CSVDataLoader(filepath=filepath)
    df = loader.load_data()
    
    print(f"数据: {len(df)} 根K线")
    print(f"范围: {df.index[0]} 至 {df.index[-1]}")
    print()
    
    # 运行回测
    cerebro = bt.Cerebro()
    data_feed = loader.to_backtrader_feed()
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
        risk_percent=0.8,
        num_symbols=2,
        debug=False  # 关闭策略debug，用analyzer
    )
    
    cerebro.broker.set_cash(2478.5)
    cerebro.addanalyzer(DetailedDebugAnalyzer, _name='debug')
    
    print("运行回测...")
    results = cerebro.run()
    strat = results[0]
    
    analysis = strat.analyzers.debug.get_analysis()
    orders = analysis['orders']
    trades = analysis['trades']
    positions = analysis['positions']
    
    print(f"完成! {len(orders)} 个订单, {len(trades)} 笔交易")
    print()
    
    # 找出巨额亏损
    print("="*80)
    print("巨额亏损的交易")
    print("="*80)
    print()
    
    giant_losses = [t for t in trades if t['pnlcomm'] < -1000]
    giant_losses_sorted = sorted(giant_losses, key=lambda x: x['pnlcomm'])
    
    for i, trade in enumerate(giant_losses_sorted[:5], 1):
        print(f"\n#{i} 交易 {trade['ref']}")
        print(f"   开仓: {trade['open_dt']}")
        print(f"   平仓: {trade['close_dt']}")
        print(f"   亏损: ${trade['pnlcomm']:,.2f}")
        print(f"   占比: {(trade['pnlcomm'] / 5000) * 100:.2f}%")
        
        # 找相关订单（在开仓到平仓时间内的所有订单）
        related_orders = [
            o for o in orders 
            if o['executed_dt'] and 
               trade['open_dt'] <= o['executed_dt'] <= trade['close_dt'] + pd.Timedelta(hours=1)
        ]
        
        print(f"\n   相关订单: {len(related_orders)} 个")
        for j, order in enumerate(related_orders, 1):
            action = "买入" if order['is_buy'] else "卖出"
            exec_type = {
                0: "Market",
                1: "Limit", 
                2: "Stop",
                3: "StopLimit",
            }.get(order['exectype'], f"Unknown({order['exectype']})")
            
            print(f"      {j}. [{order['status']}] {order['executed_dt']} "
                  f"{action} {exec_type} "
                  f"@ {order['executed_price']:.5f}, "
                  f"Size: {order['executed_size']:,.0f} ({order['executed_size']/100000:.2f} lots)")
        
        # 找相关持仓变化
        position_changes = [
            p for p in positions
            if trade['open_dt'] <= p['datetime'] <= trade['close_dt']
        ]
        
        if position_changes:
            print(f"\n   持仓变化: {len(position_changes)} 次")
            print(f"      开仓时: Size={position_changes[0]['size']:,.0f}, "
                  f"Price={position_changes[0]['price']:.5f}, "
                  f"Value=${position_changes[0]['value']:,.2f}")
            if len(position_changes) > 1:
                print(f"      平仓前: Size={position_changes[-1]['size']:,.0f}, "
                      f"Price={position_changes[-1]['price']:.5f}, "
                      f"Value=${position_changes[-1]['value']:,.2f}")
            
            # 检查是否有异常的仓位大小变化
            max_size = max(abs(p['size']) for p in position_changes)
            print(f"      最大仓位: {max_size:,.0f} ({max_size/100000:.2f} lots)")
            
            if max_size > 100000:  # 超过1标准手
                print(f"      ⚠️ 异常！仓位超过1标准手")


if __name__ == '__main__':
    import pandas as pd
    main()
