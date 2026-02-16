"""
Blue Guardian资金管理规则测试

测试严格资金管理规则下的策略风险：
- 单笔亏损 ≤ 1% (原始资金)
- 单日亏损 ≤ 3% (原始资金)  
- 总亏损 ≤ 6% (原始资金)

当前账户状态：
- 原始资金: $5,000
- 当前余额: $4,957 (已亏$43, 0.86%)
- 剩余可亏: $257 (5.14%)
"""

import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置UTF-8编码
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader
from utils.forex_commission import create_forex_commission


# Blue Guardian规则
ORIGINAL_BALANCE = 5000.0  # 原始资金
CURRENT_BALANCE = 4957.0   # 当前余额
CURRENT_LOSS = ORIGINAL_BALANCE - CURRENT_BALANCE  # $43

MAX_SINGLE_TRADE_LOSS_PCT = 1.0   # 单笔最大亏损1%
MAX_DAILY_LOSS_PCT = 3.0          # 单日最大亏损3%
MAX_TOTAL_LOSS_PCT = 6.0          # 总亏损6%

MAX_SINGLE_TRADE_LOSS = ORIGINAL_BALANCE * MAX_SINGLE_TRADE_LOSS_PCT / 100  # $50
MAX_DAILY_LOSS = ORIGINAL_BALANCE * MAX_DAILY_LOSS_PCT / 100                # $150
MAX_TOTAL_LOSS = ORIGINAL_BALANCE * MAX_TOTAL_LOSS_PCT / 100                # $300

REMAINING_LOSS_BUDGET = MAX_TOTAL_LOSS - CURRENT_LOSS  # $257


# 测试配置
TEST_SCENARIOS = [
    {
        'name': '当前配置 (风险1.0%)',
        'symbols': {
            'GBPUSD': {'file': './data/GBP_USD_M5.csv', 'adx': 35, 'risk': 1.0},
            'USDJPY': {'file': './data/USD_JPY_M5.csv', 'adx': 35, 'risk': 1.0},
        }
    },
    {
        'name': '保守配置 (风险0.8%)',
        'symbols': {
            'GBPUSD': {'file': './data/GBP_USD_M5.csv', 'adx': 35, 'risk': 0.8},
            'USDJPY': {'file': './data/USD_JPY_M5.csv', 'adx': 35, 'risk': 0.8},
        }
    },
    {
        'name': '极度保守 (风险0.6%)',
        'symbols': {
            'GBPUSD': {'file': './data/GBP_USD_M5.csv', 'adx': 35, 'risk': 0.6},
            'USDJPY': {'file': './data/USD_JPY_M5.csv', 'adx': 35, 'risk': 0.6},
        }
    },
]


class BlueGuardianAnalyzer(bt.Analyzer):
    """Blue Guardian规则监控分析器"""
    
    def __init__(self):
        self.trades = []
        self.daily_pnl = {}
        self.equity_curve = []
        self.violations = {
            'single_trade': [],
            'daily_loss': [],
            'total_loss': [],
        }
        
    def notify_trade(self, trade):
        if trade.isclosed:
            trade_pnl = trade.pnl
            trade_date = self.strategy.datetime.date()
            
            # 记录交易
            self.trades.append({
                'date': trade_date,
                'datetime': self.strategy.datetime.datetime(),
                'pnl': trade_pnl,
                'size': trade.size,
            })
            
            # 累计当日盈亏
            if trade_date not in self.daily_pnl:
                self.daily_pnl[trade_date] = 0
            self.daily_pnl[trade_date] += trade_pnl
            
    def notify_cashvalue(self, cash, value):
        """记录权益曲线"""
        self.equity_curve.append({
            'datetime': self.strategy.datetime.datetime(),
            'cash': cash,
            'value': value,
        })
    
    def stop(self):
        """回测结束后分析违规情况"""
        
        # 1. 检查单笔交易亏损
        for trade in self.trades:
            if trade['pnl'] < 0:  # 亏损交易
                loss_amount = abs(trade['pnl'])
                loss_pct = (loss_amount / ORIGINAL_BALANCE) * 100
                
                if loss_amount > MAX_SINGLE_TRADE_LOSS:
                    self.violations['single_trade'].append({
                        'date': trade['date'],
                        'datetime': trade['datetime'],
                        'loss': loss_amount,
                        'loss_pct': loss_pct,
                        'limit': MAX_SINGLE_TRADE_LOSS,
                        'excess': loss_amount - MAX_SINGLE_TRADE_LOSS,
                    })
        
        # 2. 检查单日亏损
        for date, daily_pnl in self.daily_pnl.items():
            if daily_pnl < 0:  # 亏损日
                loss_amount = abs(daily_pnl)
                loss_pct = (loss_amount / ORIGINAL_BALANCE) * 100
                
                if loss_amount > MAX_DAILY_LOSS:
                    self.violations['daily_loss'].append({
                        'date': date,
                        'loss': loss_amount,
                        'loss_pct': loss_pct,
                        'limit': MAX_DAILY_LOSS,
                        'excess': loss_amount - MAX_DAILY_LOSS,
                    })
        
        # 3. 检查总回撤（从当前余额$4,957开始）
        if len(self.equity_curve) > 0:
            initial_value = CURRENT_BALANCE  # 从当前余额开始
            max_drawdown = 0
            max_drawdown_value = initial_value
            
            for point in self.equity_curve:
                value = point['value']
                drawdown = initial_value - value
                
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_value = value
                    
                    # 检查是否超过剩余可亏损额度
                    if drawdown > REMAINING_LOSS_BUDGET:
                        self.violations['total_loss'].append({
                            'datetime': point['datetime'],
                            'current_value': value,
                            'drawdown': drawdown,
                            'drawdown_pct': (drawdown / ORIGINAL_BALANCE) * 100,
                            'limit': REMAINING_LOSS_BUDGET,
                            'excess': drawdown - REMAINING_LOSS_BUDGET,
                            'would_breach_total_limit': True,
                        })
    
    def get_analysis(self):
        return {
            'trades': self.trades,
            'daily_pnl': self.daily_pnl,
            'violations': self.violations,
            'equity_curve': self.equity_curve,
        }


def run_single_symbol_backtest(symbol, config, initial_cash):
    """运行单品种回测"""
    
    if not os.path.exists(config['file']):
        return None
    
    try:
        # 加载数据
        loader = CSVDataLoader(filepath=config['file'])
        df = loader.load_data()
        
        if not loader.validate_data():
            return None
        
        # 配置回测
        cerebro = bt.Cerebro()
        data_feed = loader.to_backtrader_feed()
        cerebro.adddata(data_feed)
        
        # 添加策略
        cerebro.addstrategy(
            TrendFilterStrategy,
            up_period=20,
            down_period=20,
            ema50_period=50,
            ema200_period=200,
            adx_period=14,
            adx_threshold=config['adx'],
            atr_period=14,
            analysis_bars=5,
            pullback_wait_bars=20,
            risk_percent=config['risk'],
            debug=False
        )
        
        # 设置资金
        cerebro.broker.set_cash(initial_cash)
        
        # ✅ Bug #11修复: 使用ForexCommissionInfo正确计算盈亏
        forex_comm = create_forex_commission(
            symbol=symbol,
            commission_per_lot=5.0,
            leverage=30.0,
        )
        cerebro.broker.addcommissioninfo(forex_comm)
        
        # 添加分析器
        cerebro.addanalyzer(BlueGuardianAnalyzer, _name='blue_guardian')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # 运行回测
        results = cerebro.run()
        strat = results[0]
        
        # 提取结果
        bg_analysis = strat.analyzers.blue_guardian.get_analysis()
        returns = strat.analyzers.returns.get_analysis()
        drawdown = strat.analyzers.drawdown.get_analysis()
        trades = strat.analyzers.trades.get_analysis()
        
        return {
            'symbol': symbol,
            'initial_cash': initial_cash,
            'final_value': cerebro.broker.get_value(),
            'bg_analysis': bg_analysis,
            'returns': returns,
            'drawdown': drawdown,
            'trades': trades,
        }
        
    except Exception as e:
        print(f"    ❌ {symbol} 回测失败: {e}")
        return None


def simulate_portfolio(scenario):
    """模拟投资组合"""
    
    print(f"\n{'='*80}")
    print(f"测试场景: {scenario['name']}")
    print(f"{'='*80}\n")
    
    # 为每个品种分配一半资金
    per_symbol_cash = CURRENT_BALANCE / len(scenario['symbols'])
    
    results = {}
    all_trades = []
    
    # 运行各品种回测
    for symbol, config in scenario['symbols'].items():
        print(f"  运行 {symbol} 回测 (风险={config['risk']}%)... ", end='', flush=True)
        result = run_single_symbol_backtest(symbol, config, per_symbol_cash)
        
        if result:
            results[symbol] = result
            
            # 收集所有交易
            if result['bg_analysis']['trades']:
                for trade in result['bg_analysis']['trades']:
                    trade['symbol'] = symbol
                    all_trades.append(trade)
            
            print(f"✓")
        else:
            print(f"❌")
    
    if not results:
        print("  ❌ 所有品种回测失败")
        return None
    
    # 合并分析
    print(f"\n{'='*80}")
    print("风险评估结果")
    print(f"{'='*80}\n")
    
    # 统计各品种表现
    print("各品种表现:")
    total_final_value = 0
    total_violations = {'single_trade': [], 'daily_loss': [], 'total_loss': []}
    
    for symbol, result in results.items():
        total_final_value += result['final_value']
        pnl = result['final_value'] - per_symbol_cash
        pnl_pct = (pnl / per_symbol_cash) * 100
        
        config = scenario['symbols'][symbol]
        
        print(f"  {symbol:<10} (风险={config['risk']}%):")
        print(f"    初始: ${per_symbol_cash:,.2f}")
        print(f"    最终: ${result['final_value']:,.2f}")
        print(f"    盈亏: ${pnl:+,.2f} ({pnl_pct:+.2f}%)")
        
        # 收集违规
        violations = result['bg_analysis']['violations']
        for vtype in ['single_trade', 'daily_loss', 'total_loss']:
            total_violations[vtype].extend(violations[vtype])
        
        print()
    
    # 组合总表现
    portfolio_pnl = total_final_value - CURRENT_BALANCE
    portfolio_pnl_pct = (portfolio_pnl / CURRENT_BALANCE) * 100
    total_drawdown = CURRENT_BALANCE - min([p['value'] for r in results.values() 
                                            for p in r['bg_analysis']['equity_curve']])
    
    print(f"组合总表现:")
    print(f"  初始资金: ${CURRENT_BALANCE:,.2f}")
    print(f"  最终资金: ${total_final_value:,.2f}")
    print(f"  总盈亏: ${portfolio_pnl:+,.2f} ({portfolio_pnl_pct:+.2f}%)")
    print(f"  最大回撤: ${total_drawdown:,.2f}")
    print()
    
    # 违规检查
    has_violations = False
    
    print("="*80)
    print("Blue Guardian规则检查")
    print("="*80)
    print()
    
    # 1. 单笔交易亏损检查
    print(f"1️⃣  单笔亏损限制: ≤ ${MAX_SINGLE_TRADE_LOSS:.2f} ({MAX_SINGLE_TRADE_LOSS_PCT}%)")
    if total_violations['single_trade']:
        has_violations = True
        print(f"   ❌ 发现 {len(total_violations['single_trade'])} 次违规！\n")
        
        # 显示最严重的5次
        sorted_violations = sorted(total_violations['single_trade'], 
                                   key=lambda x: x['excess'], reverse=True)
        for i, v in enumerate(sorted_violations[:5], 1):
            print(f"      #{i} {v['datetime']}")
            print(f"         亏损: ${v['loss']:.2f} ({v['loss_pct']:.2f}%)")
            print(f"         超限: ${v['excess']:.2f}")
    else:
        print(f"   ✅ 无违规")
    
    print()
    
    # 2. 单日亏损检查
    print(f"2️⃣  单日亏损限制: ≤ ${MAX_DAILY_LOSS:.2f} ({MAX_DAILY_LOSS_PCT}%)")
    if total_violations['daily_loss']:
        has_violations = True
        print(f"   ❌ 发现 {len(total_violations['daily_loss'])} 天违规！\n")
        
        # 显示最严重的5天
        sorted_violations = sorted(total_violations['daily_loss'], 
                                   key=lambda x: x['excess'], reverse=True)
        for i, v in enumerate(sorted_violations[:5], 1):
            print(f"      #{i} {v['date']}")
            print(f"         亏损: ${v['loss']:.2f} ({v['loss_pct']:.2f}%)")
            print(f"         超限: ${v['excess']:.2f}")
    else:
        print(f"   ✅ 无违规")
    
    print()
    
    # 3. 总亏损检查
    print(f"3️⃣  总亏损限制: ≤ ${MAX_TOTAL_LOSS:.2f} ({MAX_TOTAL_LOSS_PCT}%)")
    print(f"   已亏损: ${CURRENT_LOSS:.2f}")
    print(f"   剩余额度: ${REMAINING_LOSS_BUDGET:.2f}")
    
    if total_violations['total_loss']:
        has_violations = True
        print(f"   ❌ 发现 {len(total_violations['total_loss'])} 次触及清盘线！\n")
        
        # 显示最严重的情况
        sorted_violations = sorted(total_violations['total_loss'], 
                                   key=lambda x: x['excess'], reverse=True)
        for i, v in enumerate(sorted_violations[:3], 1):
            print(f"      #{i} {v['datetime']}")
            print(f"         账户价值: ${v['current_value']:.2f}")
            print(f"         回撤: ${v['drawdown']:.2f} ({v['drawdown_pct']:.2f}%)")
            print(f"         超限: ${v['excess']:.2f}")
            print(f"         ⚠️  会触发清盘！")
    else:
        print(f"   ✅ 安全")
    
    print()
    print("="*80)
    
    # 总结
    print()
    if has_violations:
        print("⚠️  警告: 此配置存在违规风险，不适合Blue Guardian规则！")
    else:
        print("✅ 此配置符合Blue Guardian规则，可以安全使用！")
    
    print()
    
    return {
        'scenario': scenario['name'],
        'final_value': total_final_value,
        'pnl': portfolio_pnl,
        'pnl_pct': portfolio_pnl_pct,
        'has_violations': has_violations,
        'violations': total_violations,
    }


def main():
    """主函数"""
    
    print("="*80)
    print("           Blue Guardian资金管理规则测试")
    print("="*80)
    print()
    print("账户状态:")
    print(f"  原始资金: ${ORIGINAL_BALANCE:,.2f}")
    print(f"  当前余额: ${CURRENT_BALANCE:,.2f}")
    print(f"  已亏损: ${CURRENT_LOSS:.2f} ({CURRENT_LOSS/ORIGINAL_BALANCE*100:.2f}%)")
    print()
    print("资金管理规则:")
    print(f"  1️⃣  单笔最大亏损: ${MAX_SINGLE_TRADE_LOSS:.2f} ({MAX_SINGLE_TRADE_LOSS_PCT}%)")
    print(f"  2️⃣  单日最大亏损: ${MAX_DAILY_LOSS:.2f} ({MAX_DAILY_LOSS_PCT}%)")
    print(f"  3️⃣  总最大亏损: ${MAX_TOTAL_LOSS:.2f} ({MAX_TOTAL_LOSS_PCT}%)")
    print(f"  剩余可亏损额度: ${REMAINING_LOSS_BUDGET:.2f}")
    print()
    print("="*80)
    
    # 测试所有场景
    summary = []
    
    for scenario in TEST_SCENARIOS:
        result = simulate_portfolio(scenario)
        if result:
            summary.append(result)
    
    # 最终总结
    print("\n" + "="*80)
    print("                          测试总结")
    print("="*80)
    print()
    
    print(f"{'配置':<30} {'收益':<12} {'是否安全':<10}")
    print("-"*80)
    
    for s in summary:
        safety = "✅ 安全" if not s['has_violations'] else "❌ 有风险"
        print(f"{s['scenario']:<30} {s['pnl']:>+8.2f} ({s['pnl_pct']:>+6.2f}%)  {safety}")
    
    print()
    
    # 推荐
    safe_scenarios = [s for s in summary if not s['has_violations']]
    
    if safe_scenarios:
        best = max(safe_scenarios, key=lambda x: x['pnl'])
        print(f"✅ 推荐配置: {best['scenario']}")
        print(f"   预期收益: ${best['pnl']:+,.2f} ({best['pnl_pct']:+.2f}%)")
        print(f"   风险评估: 符合所有Blue Guardian规则")
    else:
        print("⚠️  警告: 所有测试配置都存在违规风险！")
        print("   建议:")
        print("   1. 进一步降低风险百分比 (试试0.5%或0.4%)")
        print("   2. 暂时只交易GBPUSD (最稳健)")
        print("   3. 或者等待账户资金恢复后再启用组合")
    
    print()
    print("="*80)


if __name__ == '__main__':
    main()
