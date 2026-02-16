"""
Blue Guardian 风险分配修复测试

测试修复后的风险计算：
- 风险基于总原始资金
- 多品种平均分配风险
- 防止风险叠加超限
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
from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader
from utils.forex_commission import create_forex_commission, get_quote_usd_rate


# Blue Guardian规则
ORIGINAL_BALANCE = 5000.0
CURRENT_BALANCE = 4957.0
CURRENT_LOSS = ORIGINAL_BALANCE - CURRENT_BALANCE  # $43

MAX_SINGLE_TRADE_LOSS_PCT = 1.0   # 1%
MAX_DAILY_LOSS_PCT = 3.0          # 3%
MAX_TOTAL_LOSS_PCT = 6.0          # 6%

MAX_SINGLE_TRADE_LOSS = ORIGINAL_BALANCE * MAX_SINGLE_TRADE_LOSS_PCT / 100  # $50
MAX_DAILY_LOSS = ORIGINAL_BALANCE * MAX_DAILY_LOSS_PCT / 100                # $150
MAX_TOTAL_LOSS = ORIGINAL_BALANCE * MAX_TOTAL_LOSS_PCT / 100                # $300

REMAINING_LOSS_BUDGET = MAX_TOTAL_LOSS - CURRENT_LOSS  # $257


# 测试配置
TEST_SCENARIOS = [
    {
        'name': '修复后配置 (0.8%总风险)',
        'total_risk_pct': 0.8,
        'symbols': {
            'GBPUSD': {'file': './data/GBP_USD_M5.csv', 'adx': 35},
            'USDJPY': {'file': './data/USD_JPY_M5.csv', 'adx': 35},
        }
    },
    {
        'name': '修复后配置 (0.6%总风险)',
        'total_risk_pct': 0.6,
        'symbols': {
            'GBPUSD': {'file': './data/GBP_USD_M5.csv', 'adx': 35},
            'USDJPY': {'file': './data/USD_JPY_M5.csv', 'adx': 35},
        }
    },
    {
        'name': '修复后配置 (1.0%总风险)',
        'total_risk_pct': 1.0,
        'symbols': {
            'GBPUSD': {'file': './data/GBP_USD_M5.csv', 'adx': 35},
            'USDJPY': {'file': './data/USD_JPY_M5.csv', 'adx': 35},
        }
    },
]


class RiskMonitor(bt.Analyzer):
    """风险监控分析器 - 详细记录每笔交易的风险"""
    
    def __init__(self):
        self.trades = []
        self.daily_pnl = {}
        self.positions = []
        
    def notify_trade(self, trade):
        if trade.isclosed:
            trade_pnl = trade.pnlcomm
            trade_date = self.strategy.datetime.date()
            
            # 记录交易
            self.trades.append({
                'date': trade_date,
                'datetime': self.strategy.datetime.datetime(),
                'pnl': trade_pnl,
                'pnl_pct_of_original': (trade_pnl / ORIGINAL_BALANCE) * 100,
                'size': trade.size,
                'price': trade.price,
            })
            
            # 累计当日盈亏
            if trade_date not in self.daily_pnl:
                self.daily_pnl[trade_date] = 0
            self.daily_pnl[trade_date] += trade_pnl
    
    def get_analysis(self):
        # 分析违规情况
        violations = {
            'single_trade': [],
            'daily_loss': [],
        }
        
        # 单笔亏损检查
        for trade in self.trades:
            if trade['pnl'] < 0:
                loss = abs(trade['pnl'])
                if loss > MAX_SINGLE_TRADE_LOSS:
                    violations['single_trade'].append({
                        'date': trade['date'],
                        'datetime': trade['datetime'],
                        'loss': loss,
                        'loss_pct': (loss / ORIGINAL_BALANCE) * 100,
                        'excess': loss - MAX_SINGLE_TRADE_LOSS,
                    })
        
        # 单日亏损检查
        for date, pnl in self.daily_pnl.items():
            if pnl < 0:
                loss = abs(pnl)
                if loss > MAX_DAILY_LOSS:
                    violations['daily_loss'].append({
                        'date': date,
                        'loss': loss,
                        'loss_pct': (loss / ORIGINAL_BALANCE) * 100,
                        'excess': loss - MAX_DAILY_LOSS,
                    })
        
        return {
            'trades': self.trades,
            'daily_pnl': self.daily_pnl,
            'violations': violations,
        }


def run_backtest(symbol, config, initial_cash, total_account, risk_pct, num_symbols):
    """运行单品种回测"""
    
    if not os.path.exists(config['file']):
        return None
    
    try:
        print(f"    加载数据... ", end='', flush=True)
        loader = CSVDataLoader(filepath=config['file'])
        df = loader.load_data()
        
        if not loader.validate_data():
            print("❌")
            return None
        print("✓")
        
        # 配置回测
        cerebro = bt.Cerebro()
        data_feed = loader.to_backtrader_feed()
        cerebro.adddata(data_feed)
        
        # 添加策略（使用修复后的参数）
        quote_rate = get_quote_usd_rate(symbol)
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
            total_account_size=total_account,  # ✅ 总账户规模
            risk_percent=risk_pct,             # ✅ 总风险百分比
            num_symbols=num_symbols,           # ✅ 品种数量
            quote_usd_rate=quote_rate,         # ✅ 交叉货币对PnL转换率
            debug=False
        )
        
        # 设置资金
        cerebro.broker.set_cash(initial_cash)
        
        # ✅ Bug #11修复: 使用自定义ForexCommissionInfo
        # 对USDJPY等间接报价货币对，正确计算盈亏: PnL = size × Δprice / newprice
        # 对GBPUSD等直接报价货币对，使用标准公式: PnL = size × Δprice
        forex_comm = create_forex_commission(
            symbol=symbol,
            commission_per_lot=2.5,  # $2.5/手/单边 (Backtrader开+平各调一次 = $5/手 Round Turn)
            leverage=30.0,           # 30倍杠杆
        )
        cerebro.broker.addcommissioninfo(forex_comm)
        
        # 添加分析器
        cerebro.addanalyzer(RiskMonitor, _name='risk_monitor')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        print(f"    回测... ", end='', flush=True)
        results = cerebro.run()
        strat = results[0]
        print("✓")
        
        # 提取结果
        risk_analysis = strat.analyzers.risk_monitor.get_analysis()
        returns = strat.analyzers.returns.get_analysis()
        drawdown = strat.analyzers.drawdown.get_analysis()
        trades = strat.analyzers.trades.get_analysis()
        
        return {
            'symbol': symbol,
            'initial_cash': initial_cash,
            'final_value': cerebro.broker.get_value(),
            'risk_analysis': risk_analysis,
            'returns': returns,
            'drawdown': drawdown,
            'trades': trades,
        }
        
    except Exception as e:
        print(f"❌ {e}")
        import traceback
        traceback.print_exc()
        return None


def test_scenario(scenario):
    """测试场景"""
    
    print(f"\n{'='*80}")
    print(f"测试: {scenario['name']}")
    print(f"{'='*80}")
    print()
    print(f"风险配置:")
    print(f"  总账户: ${ORIGINAL_BALANCE:,.2f}")
    print(f"  当前余额: ${CURRENT_BALANCE:,.2f}")
    print(f"  品种数量: {len(scenario['symbols'])}")
    print(f"  总风险: {scenario['total_risk_pct']}%")
    print(f"  单品种风险: {scenario['total_risk_pct'] / len(scenario['symbols']):.2f}%")
    print(f"  理论单笔最大亏损: ${ORIGINAL_BALANCE * scenario['total_risk_pct'] / 100 / len(scenario['symbols']):.2f}")
    print()
    
    # ✅ 修复Bug #12: USDJPY因30倍杠杆需要更多保证金
    # 不等分资金：USDJPY 65%, GBPUSD 35%
    # 原因：0.86手USDJPY需要$2,869保证金（3.33%），平分资金不足
    cash_allocation = {
        'USDJPY': 0.65,  # 65% = $3,222，支持0.86手
        'GBPUSD': 0.35,  # 35% = $1,735，足够GBPUSD交易
    }
    
    num_symbols = len(scenario['symbols'])
    
    results = {}
    all_trades = []
    combined_daily_pnl = {}
    total_violations = {'single_trade': [], 'daily_loss': []}
    
    for symbol, config in scenario['symbols'].items():
        print(f"  {symbol}:")
        
        # 按比例分配资金
        symbol_cash_ratio = cash_allocation.get(symbol, 1.0 / num_symbols)
        symbol_cash = CURRENT_BALANCE * symbol_cash_ratio
        
        print(f"    分配资金: ${symbol_cash:.2f} ({symbol_cash_ratio*100:.0f}%)")
        
        result = run_backtest(
            symbol, 
            config, 
            symbol_cash,  # 使用不等分资金
            ORIGINAL_BALANCE,  # 总账户规模
            scenario['total_risk_pct'],
            num_symbols
        )
        
        if result:
            results[symbol] = result
            
            # 合并交易记录
            all_trades.extend(result['risk_analysis']['trades'])
            
            # 合并每日盈亏
            for date, pnl in result['risk_analysis']['daily_pnl'].items():
                if date not in combined_daily_pnl:
                    combined_daily_pnl[date] = 0
                combined_daily_pnl[date] += pnl
            
            # 合并违规记录
            for v_type in ['single_trade', 'daily_loss']:
                total_violations[v_type].extend(result['risk_analysis']['violations'][v_type])
        
        print()
    
    if not results:
        return None
    
    # 分析结果
    print(f"{'='*80}")
    print("各品种表现")
    print(f"{'='*80}\n")
    
    total_final = 0
    for symbol, result in results.items():
        total_final += result['final_value']
        pnl = result['final_value'] - result['initial_cash']
        pnl_pct = (pnl / result['initial_cash']) * 100
        
        num_trades = result['trades'].get('total', {}).get('closed', 0)
        won = result['trades'].get('won', {}).get('total', 0)
        win_rate = (won / num_trades * 100) if num_trades > 0 else 0
        max_dd = result['drawdown'].get('max', {}).get('drawdown', 0)
        
        print(f"  {symbol}:")
        print(f"    盈亏: ${pnl:+,.2f} ({pnl_pct:+.2f}%)")
        print(f"    交易: {num_trades}笔, 胜率: {win_rate:.1f}%, 最大回撤: {max_dd:.2f}%")
        
        # 找最大单笔亏损
        max_loss = 0
        max_loss_trade = None
        for trade in result['risk_analysis']['trades']:
            if trade['pnl'] < max_loss:
                max_loss = trade['pnl']
                max_loss_trade = trade
        
        if max_loss_trade:
            print(f"    最大单笔亏损: ${max_loss:.2f} ({max_loss_trade['pnl_pct_of_original']:.2f}% of 总账户)")
    
    total_pnl = total_final - CURRENT_BALANCE
    total_pnl_pct = (total_pnl / CURRENT_BALANCE) * 100
    
    print(f"\n  组合总计:")
    print(f"    初始: ${CURRENT_BALANCE:,.2f}")
    print(f"    最终: ${total_final:,.2f}")
    print(f"    盈亏: ${total_pnl:+,.2f} ({total_pnl_pct:+.2f}%)")
    
    # 风险分析
    print(f"\n{'='*80}")
    print("风险检查")
    print(f"{'='*80}\n")
    
    has_violations = False
    
    # 1. 单笔亏损
    print(f"1️⃣  单笔亏损限制: ≤ ${MAX_SINGLE_TRADE_LOSS:.2f} ({MAX_SINGLE_TRADE_LOSS_PCT}%)")
    if total_violations['single_trade']:
        has_violations = True
        print(f"   ❌ {len(total_violations['single_trade'])} 次违规")
        for i, v in enumerate(sorted(total_violations['single_trade'], 
                                     key=lambda x: x['excess'], reverse=True)[:3], 1):
            print(f"      #{i} {v['datetime']}: 亏损${v['loss']:.2f} ({v['loss_pct']:.2f}%), 超限${v['excess']:.2f}")
    else:
        # 显示最大单笔亏损
        all_losses = [t for t in all_trades if t['pnl'] < 0]
        if all_losses:
            max_loss = min(all_losses, key=lambda x: x['pnl'])
            print(f"   ✅ 无违规")
            print(f"      最大单笔亏损: ${abs(max_loss['pnl']):.2f} ({max_loss['pnl_pct_of_original']:.2f}%)")
        else:
            print(f"   ✅ 无亏损交易")
    
    print()
    
    # 2. 单日亏损（组合后）
    print(f"2️⃣  单日亏损限制: ≤ ${MAX_DAILY_LOSS:.2f} ({MAX_DAILY_LOSS_PCT}%)")
    
    # 重新计算组合后的单日亏损
    combined_violations = []
    for date, pnl in combined_daily_pnl.items():
        if pnl < 0:
            loss = abs(pnl)
            loss_pct = (loss / ORIGINAL_BALANCE) * 100
            if loss > MAX_DAILY_LOSS:
                combined_violations.append({
                    'date': date,
                    'loss': loss,
                    'loss_pct': loss_pct,
                    'excess': loss - MAX_DAILY_LOSS,
                })
    
    if combined_violations:
        has_violations = True
        print(f"   ❌ {len(combined_violations)} 天违规")
        for i, v in enumerate(sorted(combined_violations, 
                                     key=lambda x: x['excess'], reverse=True)[:3], 1):
            print(f"      #{i} {v['date']}: 亏损${v['loss']:.2f} ({v['loss_pct']:.2f}%), 超限${v['excess']:.2f}")
    else:
        # 显示最大单日亏损
        max_daily_loss = min(combined_daily_pnl.values()) if combined_daily_pnl else 0
        if max_daily_loss < 0:
            print(f"   ✅ 无违规")
            print(f"      最大单日亏损: ${abs(max_daily_loss):.2f} ({abs(max_daily_loss)/ORIGINAL_BALANCE*100:.2f}%)")
        else:
            print(f"   ✅ 无亏损日")
    
    print()
    
    # 3. 总亏损
    print(f"3️⃣  总亏损限制: ≤ ${MAX_TOTAL_LOSS:.2f} ({MAX_TOTAL_LOSS_PCT}%)")
    print(f"   已亏损: ${CURRENT_LOSS:.2f}")
    print(f"   剩余额度: ${REMAINING_LOSS_BUDGET:.2f}")
    
    if total_pnl < -REMAINING_LOSS_BUDGET:
        has_violations = True
        print(f"   ❌ 触发清盘 (测试期亏损${abs(total_pnl):.2f} > 剩余${REMAINING_LOSS_BUDGET:.2f})")
    else:
        print(f"   ✅ 安全 (测试期盈亏: ${total_pnl:+.2f})")
    
    print()
    print(f"{'='*80}")
    
    if has_violations:
        print("\n⚠️  存在违规风险\n")
    else:
        print("\n✅ 符合所有Blue Guardian规则\n")
    
    # 风险统计
    print("风险统计:")
    print(f"  理论单品种最大风险: ${ORIGINAL_BALANCE * scenario['total_risk_pct'] / 100 / num_symbols:.2f}")
    print(f"  实际最大单笔亏损: ${abs(min([t['pnl'] for t in all_trades if t['pnl'] < 0], default=0)):.2f}")
    print(f"  实际最大单日亏损: ${abs(min(combined_daily_pnl.values(), default=0)):.2f}")
    print(f"  风险放大系数: {abs(min(combined_daily_pnl.values(), default=0)) / (ORIGINAL_BALANCE * scenario['total_risk_pct'] / 100 / num_symbols):.2f}x")
    print()
    
    return {
        'scenario': scenario['name'],
        'risk_pct': scenario['total_risk_pct'],
        'final_value': total_final,
        'pnl': total_pnl,
        'pnl_pct': total_pnl_pct,
        'has_violations': has_violations,
        'max_single_loss': abs(min([t['pnl'] for t in all_trades if t['pnl'] < 0], default=0)),
        'max_daily_loss': abs(min(combined_daily_pnl.values(), default=0)),
    }


def main():
    """主函数"""
    
    print("="*80)
    print("     Blue Guardian 风险分配修复测试")
    print("="*80)
    print()
    print("修复内容:")
    print("  ✅ 风险基于总原始资金（而非分配资金）")
    print("  ✅ 多品种平均分配风险")
    print("  ✅ 防止风险叠加超限")
    print()
    print("账户状态:")
    print(f"  原始资金: ${ORIGINAL_BALANCE:,.2f}")
    print(f"  当前余额: ${CURRENT_BALANCE:,.2f}")
    print(f"  已亏损: ${CURRENT_LOSS:.2f}")
    print(f"  剩余可亏: ${REMAINING_LOSS_BUDGET:.2f}")
    print()
    print("Blue Guardian规则:")
    print(f"  单笔最大亏损: ${MAX_SINGLE_TRADE_LOSS:.2f} ({MAX_SINGLE_TRADE_LOSS_PCT}%)")
    print(f"  单日最大亏损: ${MAX_DAILY_LOSS:.2f} ({MAX_DAILY_LOSS_PCT}%)")
    print(f"  总最大亏损: ${MAX_TOTAL_LOSS:.2f} ({MAX_TOTAL_LOSS_PCT}%)")
    print()
    print("="*80)
    
    summary = []
    
    for scenario in TEST_SCENARIOS:
        result = test_scenario(scenario)
        if result:
            summary.append(result)
    
    # 最终总结
    print("\n" + "="*80)
    print("                          测试总结")
    print("="*80)
    print()
    
    print(f"{'配置':<30} {'风险':<8} {'收益':<15} {'最大单笔':<12} {'最大单日':<12} {'状态':<10}")
    print("-"*80)
    
    for s in summary:
        status = "✅ 安全" if not s['has_violations'] else "❌ 违规"
        print(f"{s['scenario']:<30} {s['risk_pct']:.1f}%    "
              f"{s['pnl']:>+8.2f} ({s['pnl_pct']:>+6.2f}%)  "
              f"${s['max_single_loss']:>7.2f}    ${s['max_daily_loss']:>7.2f}    {status}")
    
    print()
    
    # 推荐
    safe = [s for s in summary if not s['has_violations']]
    
    if safe:
        best = max(safe, key=lambda x: x['pnl'])
        print(f"✅ 推荐配置: {best['scenario']}")
        print(f"   总风险: {best['risk_pct']}%")
        print(f"   单品种风险: {best['risk_pct'] / 2:.2f}%")
        print(f"   预期收益: ${best['pnl']:+,.2f} ({best['pnl_pct']:+.2f}%)")
        print(f"   最大单笔亏损: ${best['max_single_loss']:.2f} (< ${MAX_SINGLE_TRADE_LOSS:.2f})")
        print(f"   最大单日亏损: ${best['max_daily_loss']:.2f} (< ${MAX_DAILY_LOSS:.2f})")
        print(f"   符合所有Blue Guardian规则 ✅")
    else:
        print("⚠️  所有配置都有违规风险")
        print("   建议进一步降低总风险百分比")
    
    print()
    print("="*80)


if __name__ == '__main__':
    main()
