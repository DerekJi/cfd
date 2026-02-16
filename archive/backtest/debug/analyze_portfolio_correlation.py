"""
多品种投资组合相关性分析

分析外汇品种间的相关性，找出最优组合来分散风险
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置UTF-8编码
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader


# 外汇品种配置
FOREX_SYMBOLS = {
    'GBPUSD': {
        'file': './data/GBP_USD_M5.csv',
        'adx': 35,
        'risk': 1.0,
        'description': 'GBP/USD - 英镑/美元'
    },
    'EURUSD': {
        'file': './data/EUR_USD_M5.csv',
        'adx': 30,
        'risk': 1.0,
        'description': 'EUR/USD - 欧元/美元'
    },
    'USDJPY': {
        'file': './data/USD_JPY_M5.csv',
        'adx': 35,
        'risk': 1.0,
        'description': 'USD/JPY - 美元/日元'
    },
    'AUDUSD': {
        'file': './data/AUD_USD_M5.csv',
        'adx': 35,
        'risk': 1.0,
        'description': 'AUD/USD - 澳元/美元'
    },
}


def run_backtest_for_equity_curve(symbol, config):
    """运行回测并返回权益曲线"""
    
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
        initial_cash = 10000.0
        cerebro.broker.set_cash(initial_cash)
        
        # 记录权益曲线
        cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='time_return')
        
        # 运行回测
        results = cerebro.run()
        strat = results[0]
        
        # 获取权益曲线
        time_return = strat.analyzers.time_return.get_analysis()
        
        # 转换为DataFrame
        equity_curve = pd.Series(time_return)
        equity_curve = (1 + equity_curve).cumprod() * initial_cash
        
        return equity_curve
        
    except Exception as e:
        print(f"  ❌ {symbol} 回测失败: {e}")
        return None


def calculate_correlation_matrix(equity_curves):
    """计算品种间收益率相关系数矩阵"""
    
    # 转换为收益率
    returns = {}
    for symbol, curve in equity_curves.items():
        returns[symbol] = curve.pct_change().dropna()
    
    # 创建DataFrame
    returns_df = pd.DataFrame(returns)
    
    # 计算相关系数矩阵
    correlation_matrix = returns_df.corr()
    
    return correlation_matrix, returns_df


def calculate_portfolio_performance(returns_df, weights):
    """计算投资组合表现"""
    
    # 组合收益率
    portfolio_returns = (returns_df * weights).sum(axis=1)
    
    # 计算指标
    total_return = (1 + portfolio_returns).prod() - 1
    annual_return = total_return  # 已经是年化（12.5个月≈1年）
    
    volatility = portfolio_returns.std() * np.sqrt(252 * 288)  # M5 -> 年化波动率
    
    # 最大回撤
    cum_returns = (1 + portfolio_returns).cumprod()
    running_max = cum_returns.expanding().max()
    drawdown = (cum_returns - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # 夏普比率
    if volatility > 0:
        sharpe = annual_return / volatility
    else:
        sharpe = 0
    
    return {
        'total_return': total_return * 100,
        'annual_return': annual_return * 100,
        'volatility': volatility * 100,
        'max_drawdown': abs(max_drawdown) * 100,
        'sharpe_ratio': sharpe,
    }


def find_optimal_portfolios(returns_df, symbols):
    """寻找最优投资组合"""
    
    portfolios = []
    
    # 1. 等权重组合
    n = len(symbols)
    equal_weights = np.array([1/n] * n)
    perf = calculate_portfolio_performance(returns_df[symbols], equal_weights)
    portfolios.append({
        'name': f'{", ".join(symbols)} 等权',
        'symbols': symbols,
        'weights': dict(zip(symbols, equal_weights)),
        **perf
    })
    
    # 2. 如果有4个品种，尝试不同的3品种组合
    if len(symbols) == 4:
        from itertools import combinations
        for combo in combinations(symbols, 3):
            combo_symbols = list(combo)
            weights = np.array([1/3] * 3)
            perf = calculate_portfolio_performance(returns_df[combo_symbols], weights)
            portfolios.append({
                'name': f'{", ".join(combo_symbols)} 等权',
                'symbols': combo_symbols,
                'weights': dict(zip(combo_symbols, weights)),
                **perf
            })
    
    # 3. 两两组合 (低相关性配对)
    if len(symbols) >= 2:
        from itertools import combinations
        for combo in combinations(symbols, 2):
            combo_symbols = list(combo)
            weights = np.array([0.5] * 2)
            perf = calculate_portfolio_performance(returns_df[combo_symbols], weights)
            portfolios.append({
                'name': f'{combo_symbols[0]} + {combo_symbols[1]}',
                'symbols': combo_symbols,
                'weights': dict(zip(combo_symbols, weights)),
                **perf
            })
    
    return portfolios


def main():
    """主函数"""
    
    print("="*80)
    print("                 多品种投资组合相关性分析")
    print("="*80)
    print()
    print("分析目标：")
    print("  1. 计算外汇品种间的相关性")
    print("  2. 评估不同组合的风险收益特征")
    print("  3. 找出最优分散化组合")
    print()
    print("="*80)
    print()
    
    # Step 1: 运行所有品种回测，获取权益曲线
    print("📊 第一步: 生成各品种权益曲线...")
    print()
    
    equity_curves = {}
    single_performances = {}
    
    for symbol, config in FOREX_SYMBOLS.items():
        print(f"  处理 {symbol}... ", end='', flush=True)
        curve = run_backtest_for_equity_curve(symbol, config)
        if curve is not None and len(curve) > 0:
            equity_curves[symbol] = curve
            
            # 计算单品种表现
            returns = curve.pct_change().dropna()
            total_return = (curve.iloc[-1] / curve.iloc[0] - 1) * 100
            cum_returns = (1 + returns).cumprod()
            running_max = cum_returns.expanding().max()
            drawdown = (cum_returns - running_max) / running_max
            max_dd = abs(drawdown.min()) * 100
            
            single_performances[symbol] = {
                'return': total_return,
                'max_dd': max_dd,
                'adx': config['adx']
            }
            
            print(f"✓ (收益: {total_return:+.2f}%, 回撤: {max_dd:.2f}%)")
        else:
            print("❌")
    
    print()
    
    if len(equity_curves) < 2:
        print("❌ 至少需要2个品种的数据才能进行相关性分析")
        return
    
    print(f"✓ 成功加载 {len(equity_curves)} 个品种的权益数据")
    print()
    
    # Step 2: 计算相关性矩阵
    print("="*80)
    print("📈 第二步: 计算品种间相关性...")
    print()
    
    correlation_matrix, returns_df = calculate_correlation_matrix(equity_curves)
    
    print("收益率相关系数矩阵:")
    print()
    print(correlation_matrix.to_string(float_format=lambda x: f"{x:7.3f}"))
    print()
    
    # 找出低相关性配对
    print("低相关性配对 (|相关系数| < 0.3):")
    symbols = list(correlation_matrix.columns)
    low_corr_pairs = []
    for i in range(len(symbols)):
        for j in range(i+1, len(symbols)):
            corr = correlation_matrix.iloc[i, j]
            if abs(corr) < 0.3:
                low_corr_pairs.append((symbols[i], symbols[j], corr))
                print(f"  • {symbols[i]} ↔ {symbols[j]}: {corr:+.3f}")
    
    if not low_corr_pairs:
        print("  (无完全低相关配对，显示最低的几对)")
        all_pairs = []
        for i in range(len(symbols)):
            for j in range(i+1, len(symbols)):
                corr = correlation_matrix.iloc[i, j]
                all_pairs.append((symbols[i], symbols[j], corr))
        all_pairs.sort(key=lambda x: abs(x[2]))
        for pair in all_pairs[:3]:
            print(f"  • {pair[0]} ↔ {pair[1]}: {pair[2]:+.3f}")
    
    print()
    
    # Step 3: 评估不同投资组合
    print("="*80)
    print("💼 第三步: 评估不同投资组合方案...")
    print()
    
    portfolios = find_optimal_portfolios(returns_df, list(equity_curves.keys()))
    
    # 按夏普比率排序
    portfolios.sort(key=lambda x: x['sharpe_ratio'], reverse=True)
    
    # 显示结果
    print(f"{'组合配置':<40} {'收益率':<10} {'回撤':<10} {'波动率':<10} {'夏普':<8}")
    print("-"*80)
    
    for p in portfolios:
        print(f"{p['name']:<40} {p['total_return']:>7.2f}%  {p['max_drawdown']:>7.2f}%  "
              f"{p['volatility']:>7.2f}%  {p['sharpe_ratio']:>6.2f}")
    
    print()
    
    # Step 4: 对比单品种 vs 组合
    print("="*80)
    print("📊 第四步: 单品种 vs 最优组合对比...")
    print()
    
    best_portfolio = portfolios[0]
    
    print("单品种表现:")
    for symbol, perf in single_performances.items():
        print(f"  {symbol:<10} (ADX={perf['adx']:<2}): "
              f"收益 {perf['return']:>7.2f}%, 回撤 {perf['max_dd']:>6.2f}%")
    
    print()
    print("最优组合表现:")
    print(f"  配置: {best_portfolio['name']}")
    print(f"  权重: {best_portfolio['weights']}")
    print(f"  收益: {best_portfolio['total_return']:>7.2f}%")
    print(f"  回撤: {best_portfolio['max_drawdown']:>7.2f}%")
    print(f"  波动: {best_portfolio['volatility']:>7.2f}%")
    print(f"  夏普: {best_portfolio['sharpe_ratio']:>7.2f}")
    
    print()
    
    # 计算分散化效益
    avg_single_return = np.mean([p['return'] for p in single_performances.values()])
    avg_single_dd = np.mean([p['max_dd'] for p in single_performances.values()])
    
    return_improvement = best_portfolio['total_return'] - avg_single_return
    dd_improvement = avg_single_dd - best_portfolio['max_drawdown']
    
    print("分散化效益:")
    print(f"  收益提升: {return_improvement:+.2f}% (vs 单品种平均)")
    print(f"  回撤改善: {dd_improvement:+.2f}% (降低)")
    print(f"  风险调整收益: 夏普比率 {best_portfolio['sharpe_ratio']:.2f}")
    
    print()
    
    # Step 5: 推荐方案
    print("="*80)
    print("🎯 第五步: 投资组合推荐...")
    print()
    
    # 找出夏普比率最高的
    best_by_sharpe = portfolios[0]
    
    # 找出收益最高的（回撤可接受）
    best_by_return = max([p for p in portfolios if p['max_drawdown'] < 15], 
                         key=lambda x: x['total_return'])
    
    # 找出最稳健的（回撤最小）
    best_by_stability = min(portfolios, key=lambda x: x['max_drawdown'])
    
    print("【激进型】最高收益组合:")
    print(f"  {best_by_return['name']}")
    print(f"  收益: {best_by_return['total_return']:+.2f}%, "
          f"回撤: {best_by_return['max_drawdown']:.2f}%, "
          f"夏普: {best_by_return['sharpe_ratio']:.2f}")
    
    print()
    print("【平衡型】最高夏普组合 (推荐):")
    print(f"  {best_by_sharpe['name']}")
    print(f"  收益: {best_by_sharpe['total_return']:+.2f}%, "
          f"回撤: {best_by_sharpe['max_drawdown']:.2f}%, "
          f"夏普: {best_by_sharpe['sharpe_ratio']:.2f}")
    
    print()
    print("【稳健型】最低回撤组合:")
    print(f"  {best_by_stability['name']}")
    print(f"  收益: {best_by_stability['total_return']:+.2f}%, "
          f"回撤: {best_by_stability['max_drawdown']:.2f}%, "
          f"夏普: {best_by_stability['sharpe_ratio']:.2f}")
    
    print()
    print("="*80)
    print()
    
    # 保存详细结果
    output_file = f'./results/reports/portfolio_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    portfolios_df = pd.DataFrame(portfolios)
    portfolios_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    print(f"✓ 详细结果已保存: {output_file}")
    print()


if __name__ == '__main__':
    main()
