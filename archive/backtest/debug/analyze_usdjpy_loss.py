"""
深度调试：分析USDJPY的$508亏损是如何产生的
"""

import sys
import os
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader


class TradeDetailAnalyzer(bt.Analyzer):
    """详细记录每笔交易的细节"""
    
    def __init__(self):
        self.trades = []
        self.positions_log = []  # 记录每个订单
        
    def notify_order(self, order):
        """记录订单执行"""
        if order.status in [order.Completed]:
            self.positions_log.append({
                'ref': order.ref,
                'is_buy': order.isbuy(),
                'executed_price': order.executed.price,
                'executed_size': order.executed.size,
                'executed_value': order.executed.value,
                'datetime': bt.num2date(order.executed.dt),
            })
        
    def notify_trade(self, trade):
        if trade.isclosed:
            # 从订单日志中查找开仓和平仓信息
            related_orders = [o for o in self.positions_log if o['ref'] <= trade.ref]
            
            # 简单记录
            self.trades.append({
                'ref': trade.ref,
                'data_name': trade.data._name,
                'open_datetime': bt.num2date(trade.dtopen),
                'close_datetime': bt.num2date(trade.dtclose),
                'pnl': trade.pnl,
                'pnlcomm': trade.pnlcomm,
                'commission': trade.commission,
                'bars_held': trade.barlen,
                'history_orders': len(related_orders),  # 相关订单数量
            })
    
    def get_analysis(self):
        return {
            'trades': sorted(self.trades, key=lambda x: x['pnlcomm']),
            'orders': self.positions_log
        }


class PositionSizeLogger(bt.Strategy):
    """记录每次开仓时的详细计算"""
    
    params = (
        ('up_period', 20),
        ('down_period', 20),
        ('ema50_period', 50),
        ('ema200_period', 200),
        ('adx_period', 14),
        ('adx_threshold', 35),
        ('atr_period', 14),
        ('analysis_bars', 5),
        ('pullback_wait_bars', 20),
        ('total_account_size', 10000.0),
        ('risk_percent', 1.0),
        ('num_symbols', 1),
        ('min_lot', 0.01),
        ('max_lot', 10.0),
        ('max_cash_ratio', 0.95),
        ('debug', True)
    )
    
    def __init__(self):
        self.order = None
        self.entry_price = None
        self.stop_loss = None
        self.size_log = []
        
    def _calculate_position_size(self, entry_price, stop_loss, short=False):
        """计算仓位（带日志）"""
        cash_available = self.broker.get_cash()
        account_value = self.broker.get_value()
        
        # 风险金额
        risk_amount = (self.params.total_account_size * self.params.risk_percent / 100) / self.params.num_symbols
        
        # 止损距离
        if short:
            stop_distance = stop_loss - entry_price
        else:
            stop_distance = entry_price - stop_loss
        
        if stop_distance <= 0:
            return 0
        
        # 基于风险的仓位
        size_by_risk = risk_amount / stop_distance
        
        # 限制最大资金使用
        max_value = account_value * self.params.max_cash_ratio
        max_size_by_cash = max_value / entry_price
        size_final = min(size_by_risk, max_size_by_cash)
        
        # 转换为手数
        lots = size_final / 100000
        lots_capped = max(self.params.min_lot, min(lots, self.params.max_lot))
        size_final = lots_capped * 100000
        
        # 记录日志
        log_entry = {
            'datetime': self.datetime.datetime(),
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'stop_distance': stop_distance,
            'stop_distance_pct': (stop_distance / entry_price) * 100,
            'risk_amount': risk_amount,
            'account_value': account_value,
            'size_by_risk': size_by_risk,
            'size_by_cash': max_size_by_cash,
            'size_final': size_final,
            'lots': lots_capped,
            'theoretical_risk': size_final * stop_distance,
            'theoretical_risk_pct': (size_final * stop_distance / self.params.total_account_size) * 100,
        }
        self.size_log.append(log_entry)
        
        return size_final
    
    def next(self):
        # 简单做多逻辑
        if not self.position:
            if len(self) > 50 and self.data.close[0] > self.data.close[-1]:
                # 假设止损为前5根最低价
                stop_loss = min([self.data.low[-i] for i in range(5)])
                entry_price = self.data.close[0]
                
                size = self._calculate_position_size(entry_price, stop_loss, short=False)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.entry_price = entry_price
                    self.stop_loss = stop_loss
        else:
            # 止损
            if self.data.close[0] < self.stop_loss:
                self.order = self.close()
                self.entry_price = None
                self.stop_loss = None


def main():
    print("="*80)
    print("     USDJPY 交易细节分析")
    print("="*80)
    print()
    
    # 加载数据
    filepath = './data/USD_JPY_M5.csv'
    if not os.path.exists(filepath):
        print(f"数据文件不存在: {filepath}")
        return
    
    loader = CSVDataLoader(filepath=filepath)
    df = loader.load_data()
    
    print(f"数据加载: {len(df)} 根K线")
    print(f"时间范围: {df.index[0]} 至 {df.index[-1]}")
    print()
    
    # 运行回测
    cerebro = bt.Cerebro()
    data_feed = loader.to_backtrader_feed()
    cerebro.adddata(data_feed)
    
    # 使用真实策略
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
        total_account_size=5000.0,  # Blue Guardian原始资金
        risk_percent=0.8,            # 0.8%总风险
        num_symbols=2,               # 2个品种
        debug=False
    )
    
    cerebro.broker.set_cash(2478.5)  # USDJPY分配资金
    
    # 添加分析器
    cerebro.addanalyzer(TradeDetailAnalyzer, _name='trade_details')
    
    print("运行回测...")
    results = cerebro.run()
    strat = results[0]
    
    # 分析结果
    analysis = strat.analyzers.trade_details.get_analysis()
    trades = analysis['trades']
    orders = analysis['orders']
    
    print(f"完成! 共 {len(trades)} 笔交易, {len(orders)} 个订单")
    print()
    
    # 找出亏损最大的几笔
    print("="*80)
    print("亏损最大的10笔交易")
    print("="*80)
    print()
    
    loss_trades = [t for t in trades if t['pnlcomm'] < 0]
    loss_trades_sorted = sorted(loss_trades, key=lambda x: x['pnlcomm'])[:10]
    
    for i, trade in enumerate(loss_trades_sorted, 1):
        print(f"#{i} 交易编号: {trade['ref']}")
        print(f"   开仓: {trade['open_datetime']}")
        print(f"   平仓: {trade['close_datetime']}")
        print(f"   持仓时间: {trade['bars_held']} bars")
        print(f"   盈亏: ${trade['pnlcomm']:+,.2f}")
        print(f"   盈亏%: {(trade['pnlcomm'] / 5000) * 100:+.2f}% (基于$5000)")
        
        # 查找相关订单
        related_orders = [o for o in orders if abs((o['datetime'] - trade['open_datetime']).total_seconds()) < 3600]
        if related_orders:
            print(f"   相关订单: {len(related_orders)} 个")
            for j, order in enumerate(related_orders[:4], 1):
                action = "买入" if order['is_buy'] else "卖出"
                print(f"      {j}. {order['datetime']} {action} @ {order['executed_price']:.5f}, "
                      f"仓位: {order['executed_size']:,.0f} ({order['executed_size']/100000:.2f} lots)")
        
        # 理论风险对比
        expected_risk = 5000 * 0.8 / 100 / 2  # $20
        risk_multiplier = abs(trade['pnlcomm']) / expected_risk
        print(f"   理论风险: ${expected_risk:.2f}")
        print(f"   风险放大: {risk_multiplier:.1f}x")
        print()
    
    # 统计
    print("="*80)
    print("统计信息")
    print("="*80)
    print()
    
    total_trades = len(trades)
    losing_trades = len(loss_trades)
    winning_trades = total_trades - losing_trades
    
    total_loss = sum(t['pnlcomm'] for t in loss_trades)
    avg_loss = total_loss / losing_trades if losing_trades > 0 else 0
    max_loss = min(t['pnlcomm'] for t in loss_trades) if loss_trades else 0
    
    print(f"总交易: {total_trades}")
    print(f"盈利: {winning_trades}, 亏损: {losing_trades}")
    print(f"总亏损: ${total_loss:,.2f}")
    print(f"平均亏损: ${avg_loss:,.2f}")
    print(f"最大亏损: ${max_loss:,.2f}")
    
    # 理论vs实际
    expected_max_loss = 5000 * 0.8 / 100 / 2  # $20
    print()
    print(f"理论单笔最大风险: ${expected_max_loss:.2f}")
    print(f"实际单笔最大亏损: ${abs(max_loss):.2f}")
    print(f"风险放大系数: {abs(max_loss) / expected_max_loss:.1f}x")
    
    # 分析价格跳空
    print()
    print("亏损超过$100的交易 (可能存在滑点/跳空):")
    large_losses = [t for t in loss_trades if abs(t['pnlcomm']) > 100]
    for trade in large_losses:
        print(f"  {trade['open_datetime'].strftime('%Y-%m-%d %H:%M')}: "
              f"${trade['pnlcomm']:+,.2f}, "
              f"持仓{trade['bars_held']}根K线")


if __name__ == '__main__':
    main()
