"""
GBPUSD参数精细优化测试

测试不同ADX阈值在GBPUSD上的表现，找到最优配置
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置UTF-8编码
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader


def test_adx_threshold(adx_threshold, data_path='./data/GBP_USD_M5.csv'):
    """
    测试单个ADX阈值
    
    Args:
        adx_threshold: ADX阈值
        data_path: 数据文件路径
    
    Returns:
        dict: 测试结果
    """
    try:
        # 加载数据
        loader = CSVDataLoader(filepath=data_path)
        df = loader.load_data()
        loader.validate_data()
        
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
            adx_threshold=adx_threshold,
            atr_period=14,
            analysis_bars=5,
            pullback_wait_bars=20,
            risk_percent=1.0,
            debug=False
        )
        
        # 设置资金
        initial_cash = 10000.0
        cerebro.broker.set_cash(initial_cash)
        
        # 添加分析器
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        
        # 运行回测
        results = cerebro.run()
        strat = results[0]
        
        # 提取结果
        returns = strat.analyzers.returns.get_analysis()
        drawdown = strat.analyzers.drawdown.get_analysis()
        trades = strat.analyzers.trades.get_analysis()
        sharpe = strat.analyzers.sharpe.get_analysis()
        
        total_trades = trades.get('total', {}).get('closed', 0)
        won_trades = trades.get('won', {}).get('total', 0)
        lost_trades = trades.get('lost', {}).get('total', 0)
        
        final_value = cerebro.broker.get_value()
        total_return = returns.get('rtot', 0) * 100
        max_dd = drawdown.get('max', {}).get('drawdown', 0)
        
        result = {
            'adx_threshold': adx_threshold,
            'initial_cash': initial_cash,
            'final_value': final_value,
            'total_return': total_return,
            'annual_return': returns.get('rnorm', 0) * 100,
            'max_drawdown': max_dd,
            'sharpe_ratio': sharpe.get('sharperatio', None),
            'total_trades': total_trades,
            'won_trades': won_trades,
            'lost_trades': lost_trades,
            'win_rate': (won_trades / total_trades * 100) if total_trades > 0 else 0,
            'avg_win': trades.get('won', {}).get('pnl', {}).get('average', 0),
            'avg_loss': trades.get('lost', {}).get('pnl', {}).get('average', 0),
        }
        
        # 计算盈亏比
        if result['avg_loss'] != 0:
            result['profit_factor'] = abs(result['avg_win'] / result['avg_loss'])
        else:
            result['profit_factor'] = 0
        
        # 计算收益/回撤比
        if max_dd > 0:
            result['return_dd_ratio'] = total_return / max_dd
        else:
            result['return_dd_ratio'] = 0
        
        return result
        
    except Exception as e:
        return {
            'adx_threshold': adx_threshold,
            'error': str(e)
        }


def run_optimization():
    """运行参数优化"""
    
    print("="*80)
    print("              GBPUSD参数精细化优化 - ADX阈值测试")
    print("="*80)
    print()
    print("测试目标: 找到GBPUSD的最优ADX阈值")
    print("测试范围: 28, 30, 32, 35, 38")
    print()
    print("="*80)
    print()
    
    # 测试参数
    adx_thresholds = [28, 30, 32, 35, 38]
    
    # 存储结果
    results = []
    
    # 逐个测试
    for adx in adx_thresholds:
        print(f"{'='*80}")
        print(f"测试 ADX阈值 = {adx}")
        print(f"{'='*80}")
        
        result = test_adx_threshold(adx)
        
        if 'error' in result:
            print(f"❌ 测试失败: {result['error']}")
            continue
        
        results.append(result)
        
        print(f"\n结果:")
        print(f"  总收益率: {result['total_return']:+.2f}%")
        print(f"  年化收益: {result['annual_return']:+.2f}%")
        print(f"  最大回撤: {result['max_drawdown']:.2f}%")
        print(f"  收益/回撤比: {result['return_dd_ratio']:.2f}")
        print(f"  夏普比率: {result['sharpe_ratio']}")
        print(f"  ")
        print(f"  总交易数: {result['total_trades']}笔")
        print(f"  胜率: {result['win_rate']:.1f}%")
        print(f"  盈亏比: {result['profit_factor']:.2f}")
        print(f"  平均盈利: ${result['avg_win']:.2f}")
        print(f"  平均亏损: ${result['avg_loss']:.2f}")
        print()
    
    if not results:
        print("❌ 没有成功的测试结果")
        return
    
    # 汇总分析
    print(f"\n{'='*80}")
    print("                          汇总分析")
    print("="*80)
    print()
    
    # 显示对比表
    print("📊 参数对比表:\n")
    print(f"{'ADX':<6} {'收益率':<10} {'回撤':<8} {'收益/回撤':<10} {'盈亏比':<8} {'胜率':<8} {'交易数':<8}")
    print("-"*80)
    
    for r in results:
        print(f"{r['adx_threshold']:<6} "
              f"{r['total_return']:+.2f}%{'':<4} "
              f"{r['max_drawdown']:.2f}%{'':<3} "
              f"{r['return_dd_ratio']:.2f}{'':<6} "
              f"{r['profit_factor']:.2f}{'':<4} "
              f"{r['win_rate']:.1f}%{'':<3} "
              f"{r['total_trades']:<8}")
    
    print()
    print("="*80)
    print()
    
    # 找到最优参数（多维度评估）
    print("🎯 最优参数分析:\n")
    
    # 1. 最高收益
    best_return = max(results, key=lambda x: x['total_return'])
    print(f"✅ 最高收益: ADX={best_return['adx_threshold']}, 收益={best_return['total_return']:+.2f}%")
    
    # 2. 最低回撤
    best_dd = min(results, key=lambda x: x['max_drawdown'])
    print(f"✅ 最低回撤: ADX={best_dd['adx_threshold']}, 回撤={best_dd['max_drawdown']:.2f}%")
    
    # 3. 最高盈亏比
    best_pf = max(results, key=lambda x: x['profit_factor'])
    print(f"✅ 最高盈亏比: ADX={best_pf['adx_threshold']}, 盈亏比={best_pf['profit_factor']:.2f}")
    
    # 4. 最佳收益/回撤比
    best_ratio = max(results, key=lambda x: x['return_dd_ratio'])
    print(f"✅ 最佳收益/回撤比: ADX={best_ratio['adx_threshold']}, 比值={best_ratio['return_dd_ratio']:.2f}")
    
    print()
    print("="*80)
    print()
    
    # 综合评分（收益×盈亏比/回撤）
    for r in results:
        if r['max_drawdown'] > 0:
            r['score'] = (r['total_return'] * r['profit_factor']) / r['max_drawdown']
        else:
            r['score'] = r['total_return'] * r['profit_factor']
    
    best_overall = max(results, key=lambda x: x['score'])
    
    print("⭐ 综合最优（收益×盈亏比/回撤）:\n")
    print(f"  推荐ADX阈值: {best_overall['adx_threshold']}")
    print(f"  总收益率: {best_overall['total_return']:+.2f}%")
    print(f"  最大回撤: {best_overall['max_drawdown']:.2f}%")
    print(f"  盈亏比: {best_overall['profit_factor']:.2f}")
    print(f"  胜率: {best_overall['win_rate']:.1f}%")
    print(f"  交易数: {best_overall['total_trades']}笔")
    print(f"  综合得分: {best_overall['score']:.2f}")
    
    print()
    print("="*80)
    print()
    
    # 保存结果
    report_path = f"./results/reports/gbpusd_adx_optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("GBPUSD ADX阈值优化报告\n")
        f.write("="*80 + "\n\n")
        
        f.write(f"测试日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"测试品种: GBPUSD M5\n")
        f.write(f"测试参数: ADX阈值 {adx_thresholds}\n\n")
        
        f.write("参数对比:\n")
        f.write(f"{'ADX':<6} {'收益率':<10} {'回撤':<8} {'收益/回撤':<10} {'盈亏比':<8} {'胜率':<8} {'交易数':<8}\n")
        f.write("-"*80 + "\n")
        
        for r in results:
            f.write(f"{r['adx_threshold']:<6} "
                   f"{r['total_return']:+.2f}%{'':<4} "
                   f"{r['max_drawdown']:.2f}%{'':<3} "
                   f"{r['return_dd_ratio']:.2f}{'':<6} "
                   f"{r['profit_factor']:.2f}{'':<4} "
                   f"{r['win_rate']:.1f}%{'':<3} "
                   f"{r['total_trades']:<8}\n")
        
        f.write("\n推荐配置:\n")
        f.write(f"  ADX阈值: {best_overall['adx_threshold']}\n")
        f.write(f"  预期收益: {best_overall['total_return']:+.2f}%\n")
        f.write(f"  预期回撤: {best_overall['max_drawdown']:.2f}%\n")
        f.write(f"  盈亏比: {best_overall['profit_factor']:.2f}\n")
    
    print(f"✓ 详细报告已保存: {report_path}")
    print()
    
    return best_overall


if __name__ == '__main__':
    import time
    start_time = time.time()
    
    best_config = run_optimization()
    
    elapsed_time = time.time() - start_time
    print(f"\n⏱️  优化耗时: {elapsed_time:.2f} 秒\n")
