"""
Blue Guardian 修复后测试

使用修复的策略（风险基于固定初始资金）
"""

import sys
import os
from datetime import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from strategies.trend_filter_strategy_blue_guardian import TrendFilterStrategyBlueGuardian
from utils.data_loader import CSVDataLoader
from utils.forex_commission import create_forex_commission


# Blue Guardian规则
ORIGINAL_BALANCE = 5000.0
CURRENT_BALANCE = 4957.0
CURRENT_LOSS = ORIGINAL_BALANCE - CURRENT_BALANCE  # $43

MAX_SINGLE_TRADE_LOSS = 50.0  # $50 (1%)
MAX_DAILY_LOSS = 150.0        # $150 (3%)
MAX_TOTAL_LOSS = 300.0        # $300 (6%)
REMAINING_LOSS_BUDGET = MAX_TOTAL_LOSS - CURRENT_LOSS  # $257


# 测试场景
TEST_SCENARIOS = [
    {
        'name': '保守0.8% (推荐)',
        'risk_pct': 0.8,
        'symbols': {
            'GBPUSD': {'file': './data/GBP_USD_M5.csv', 'adx': 35},
            'USDJPY': {'file': './data/USD_JPY_M5.csv', 'adx': 35},
        }
    },
    {
        'name': '极保守0.6%',
        'risk_pct': 0.6,
        'symbols': {
            'GBPUSD': {'file': './data/GBP_USD_M5.csv', 'adx': 35},
            'USDJPY': {'file': './data/USD_JPY_M5.csv', 'adx': 35},
        }
    },
    {
        'name': '激进1.0% (对比)',
        'risk_pct': 1.0,
        'symbols': {
            'GBPUSD': {'file': './data/GBP_USD_M5.csv', 'adx': 35},
            'USDJPY': {'file': './data/USD_JPY_M5.csv', 'adx': 35},
        }
    },
]


def analyze_trades_for_violations(trades_list, initial_capital):
    """分析交易记录，检查违规"""
    violations = {
        'single_trade': [],
        'daily_loss': [],
    }
    
    # 按日期分组
    daily_pnl = {}
    
    for trade in trades_list:
        if not trade.isclosed:
            continue
        
        trade_pnl = trade.pnlcomm
        trade_date = trade.dtclose.date() if hasattr(trade, 'dtclose') else None
        
        # 检查单笔亏损
        if trade_pnl < 0:
            loss = abs(trade_pnl)
            loss_pct = (loss / ORIGINAL_BALANCE) * 100
            
            if loss > MAX_SINGLE_TRADE_LOSS:
                violations['single_trade'].append({
                    'date': trade_date,
                    'loss': loss,
                    'loss_pct': loss_pct,
                    'excess': loss - MAX_SINGLE_TRADE_LOSS,
                })
        
        # 累计当日盈亏
        if trade_date:
            if trade_date not in daily_pnl:
                daily_pnl[trade_date] = 0
            daily_pnl[trade_date] += trade_pnl
    
    # 检查单日亏损
    for date, pnl in daily_pnl.items():
        if pnl < 0:
            loss = abs(pnl)
            loss_pct = (loss / ORIGINAL_BALANCE) * 100
            
            if loss > MAX_DAILY_LOSS:
                violations['daily_loss'].append({
                    'date': date,
                    'loss': loss,
                    'loss_pct': loss_pct,
                    'excess': loss - MAX_DAILY_LOSS,
                })
    
    return violations


def run_backtest(symbol, config, initial_cash, risk_pct):
    """运行单品种回测"""
    
    if not os.path.exists(config['file']):
        return None
    
    try:
        print(f"    加载数据... ", end='', flush=True)
        loader = CSVDataLoader(filepath=config['file'])
        df = loader.load_data()
        
        if not loader.validate_data():
            print("❌ 数据无效")
            return None
        
        print("✓")
        
        # 配置回测
        cerebro = bt.Cerebro()
        data_feed = loader.to_backtrader_feed()
        cerebro.adddata(data_feed)
        
        # 添加策略
        cerebro.addstrategy(
            TrendFilterStrategyBlueGuardian,
            up_period=20,
            down_period=20,
            ema50_period=50,
            ema200_period=200,
            adx_period=14,
            adx_threshold=config['adx'],
            atr_period=14,
            analysis_bars=5,
            pullback_wait_bars=20,
            initial_capital=initial_cash,  # 固定初始资金
            risk_percent=risk_pct,
            max_single_loss=MAX_SINGLE_TRADE_LOSS,
            debug=False  # 关闭详细日志
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
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        print(f"    运行回测... ", end='', flush=True)
        results = cerebro.run()
        strat = results[0]
        print("✓")
        
        # 提取结果
        returns = strat.analyzers.returns.get_analysis()
        drawdown = strat.analyzers.drawdown.get_analysis()
        trades = strat.analyzers.trades.get_analysis()
        
        # 分析违规
        violations = analyze_trades_for_violations(cerebro.broker.get_transactions(), initial_cash)
        
        return {
            'symbol': symbol,
            'initial_cash': initial_cash,
            'final_value': cerebro.broker.get_value(),
            'returns': returns,
            'drawdown': drawdown,
            'trades': trades,
            'violations': violations,
        }
        
    except Exception as e:
        print(f"❌ {e}")
        return None


def test_scenario(scenario):
    """测试单个场景"""
    
    print(f"\n{'='*80}")
    print(f"场景: {scenario['name']}")
    print(f"风险配置: {scenario['risk_pct']}% (基于固定初始资金)")
    print(f"{'='*80}\n")
    
    per_symbol_cash = CURRENT_BALANCE / len(scenario['symbols'])
    
    results = {}
    total_violations = {'single_trade': [], 'daily_loss': []}
    
    for symbol, config in scenario['symbols'].items():
        print(f"  {symbol}:")
        result = run_backtest(symbol, config, per_symbol_cash, scenario['risk_pct'])
        
        if result:
            results[symbol] = result
            
            # 合并违规
            for v_type in ['single_trade', 'daily_loss']:
                total_violations[v_type].extend(result['violations'][v_type])
        else:
            print(f"    ❌ 回测失败\n")
            continue
        
        print()
    
    if not results:
        return None
    
    # 汇总结果
    print(f"{'='*80}")
    print("结果汇总")
    print(f"{'='*80}\n")
    
    total_final_value = 0
    
    print("各品种表现:")
    for symbol, result in results.items():
        total_final_value += result['final_value']
        pnl = result['final_value'] - per_symbol_cash
        pnl_pct = (pnl / per_symbol_cash) * 100
        
        total_trades = result['trades'].get('total', {}).get('closed', 0)
        won = result['trades'].get('won', {}).get('total', 0)
        win_rate = (won / total_trades * 100) if total_trades > 0 else 0
        max_dd = result['drawdown'].get('max', {}).get('drawdown', 0)
        
        print(f"  {symbol:<10}")
        print(f"    最终: ${result['final_value']:,.2f} (盈亏: ${pnl:+,.2f}, {pnl_pct:+.2f}%)")
        print(f"    交易: {total_trades}笔, 胜率: {win_rate:.1f}%, 最大回撤: {max_dd:.2f}%")
    
    portfolio_pnl = total_final_value - CURRENT_BALANCE
    portfolio_pnl_pct = (portfolio_pnl / CURRENT_BALANCE) * 100
    
    print(f"\n组合总计:")
    print(f"  初始: ${CURRENT_BALANCE:,.2f}")
    print(f"  最终: ${total_final_value:,.2f}")
    print(f"  盈亏: ${portfolio_pnl:+,.2f} ({portfolio_pnl_pct:+.2f}%)")
    
    print(f"\n{'='*80}")
    print("Blue Guardian规则检查")
    print(f"{'='*80}\n")
    
    has_violations = False
    
    # 单笔亏损
    print(f"1️⃣  单笔亏损限制: ≤ ${MAX_SINGLE_TRADE_LOSS:.2f}")
    if total_violations['single_trade']:
        has_violations = True
        print(f"   ❌ {len(total_violations['single_trade'])} 次违规")
        for i, v in enumerate(sorted(total_violations['single_trade'], 
                                     key=lambda x: x['excess'], reverse=True)[:3], 1):
            print(f"      #{i} {v['date']}: 亏损${v['loss']:.2f}, 超限${v['excess']:.2f}")
    else:
        print(f"   ✅ 无违规")
    
    print()
    
    # 单日亏损
    print(f"2️⃣  单日亏损限制: ≤ ${MAX_DAILY_LOSS:.2f}")
    if total_violations['daily_loss']:
        has_violations = True
        print(f"   ❌ {len(total_violations['daily_loss'])} 天违规")
        for i, v in enumerate(sorted(total_violations['daily_loss'], 
                                     key=lambda x: x['excess'], reverse=True)[:3], 1):
            print(f"      #{i} {v['date']}: 亏损${v['loss']:.2f}, 超限${v['excess']:.2f}")
    else:
        print(f"   ✅ 无违规")
    
    print()
    
    # 总亏损 (简化检查)
    print(f"3️⃣  总亏损限制: ≤ ${MAX_TOTAL_LOSS:.2f}")
    print(f"   已亏损: ${CURRENT_LOSS:.2f}")
    print(f"   剩余额度: ${REMAINING_LOSS_BUDGET:.2f}")
    
    if portfolio_pnl < -REMAINING_LOSS_BUDGET:
        has_violations = True
        print(f"   ❌ 触发清盘 (亏损${abs(portfolio_pnl):.2f} > 剩余额度${REMAINING_LOSS_BUDGET:.2f})")
    else:
        print(f"   ✅ 安全 (测试期盈亏: ${portfolio_pnl:+.2f})")
    
    print()
    print(f"{'='*80}\n")
    
    if has_violations:
        print("⚠️  存在违规风险\n")
    else:
        print("✅ 符合所有Blue Guardian规则\n")
    
    return {
        'scenario': scenario['name'],
        'risk_pct': scenario['risk_pct'],
        'final_value': total_final_value,
        'pnl': portfolio_pnl,
        'pnl_pct': portfolio_pnl_pct,
        'has_violations': has_violations,
    }


def main():
    """主函数"""
    
    print("="*80)
    print("     Blue Guardian 修复后测试 (风险基于固定初始资金)")
    print("="*80)
    print()
    print("账户状态:")
    print(f"  原始资金: ${ORIGINAL_BALANCE:,.2f}")
    print(f"  当前余额: ${CURRENT_BALANCE:,.2f}")
    print(f"  已亏损: ${CURRENT_LOSS:.2f}")
    print(f"  剩余可亏: ${REMAINING_LOSS_BUDGET:.2f}")
    print()
    print("="*80)
    
    summary = []
    
    for scenario in TEST_SCENARIOS:
        result = test_scenario(scenario)
        if result:
            summary.append(result)
    
    # 最终总结
    print("\n" + "="*80)
    print("                          最终总结")
    print("="*80)
    print()
    
    print(f"{'配置':<25} {'风险':<8} {'收益':<15} {'状态':<10}")
    print("-"*80)
    
    for s in summary:
        status = "✅ 安全" if not s['has_violations'] else "❌ 有风险"
        print(f"{s['scenario']:<25} {s['risk_pct']:.1f}%    "
              f"{s['pnl']:>+8.2f} ({s['pnl_pct']:>+6.2f}%)  {status}")
    
    print()
    
    # 推荐
    safe = [s for s in summary if not s['has_violations']]
    
    if safe:
        best = max(safe, key=lambda x: x['pnl'])
        print(f"✅ 推荐配置: {best['scenario']}")
        print(f"   风险设置: {best['risk_pct']}%")
        print(f"   预期收益: ${best['pnl']:+,.2f} ({best['pnl_pct']:+.2f}%)")
        print(f"   符合Blue Guardian所有规则")
    else:
        print("⚠️  所有配置都有违规风险，建议:")
        print("   1. 进一步降低风险 (试试0.5%)")
        print("   2. 或仅交易GBPUSD")
    
    print()
    print("="*80)


if __name__ == '__main__':
    main()
