"""
多品种回测测试

测试趋势过滤策略在不同品种上的表现
目标：
1. 验证策略稳健性（各品种表现是否均衡）
2. 为不同品种找到最优参数组合
"""

import sys
import os
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置UTF-8编码
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader
from utils.forex_commission import create_forex_commission


# 测试配置
SYMBOLS = {
    'GBPUSD': {
        'file': './data/GBP_USD_M5.csv',
        'pip_value': 0.0001,
        'description': 'GBP/USD - 英镑/美元'
    },
    'EURUSD': {
        'file': './data/EUR_USD_M5.csv', 
        'pip_value': 0.0001,
        'description': 'EUR/USD - 欧元/美元'
    },
    'XAUUSD': {
        'file': './data/XAU_USD_M5.csv',
        'pip_value': 0.01,
        'description': 'XAU/USD - 黄金'
    },
    'XAGUSD': {
        'file': './data/XAG_USD_M5.csv',
        'pip_value': 0.001,
        'description': 'XAG/USD - 白银'
    },
    'USDJPY': {
        'file': './data/USD_JPY_M5.csv',
        'pip_value': 0.01,
        'description': 'USD/JPY - 美元/日元'
    },
    'AUDUSD': {
        'file': './data/AUD_USD_M5.csv',
        'pip_value': 0.0001,
        'description': 'AUD/USD - 澳元/美元'
    },
}

# 参数网格搜索
PARAM_GRID = {
    'adx_threshold': [20, 25, 30, 35],  # ADX阈值（根据Task 1优化结果扩展）
    'ema50_period': [50],               # EMA50周期
    'ema200_period': [200],             # EMA200周期
    'up_period': [20],                  # Donchian周期
}


def test_single_symbol(symbol, config, params, silent=True):
    """
    测试单个品种
    
    Args:
        symbol: 品种名称
        config: 品种配置
        params: 策略参数
        silent: 是否静默模式
    
    Returns:
        dict: 测试结果
    """
    if not os.path.exists(config['file']):
        return {
            'status': 'no_data',
            'message': f'数据文件不存在: {config["file"]}'
        }
    
    try:
        # 加载数据
        loader = CSVDataLoader(filepath=config['file'])
        df = loader.load_data()
        
        if not loader.validate_data():
            return {
                'status': 'invalid_data',
                'message': '数据验证失败'
            }
        
        # 配置回测
        cerebro = bt.Cerebro()
        data_feed = loader.to_backtrader_feed()
        cerebro.adddata(data_feed)
        
        # 添加策略
        cerebro.addstrategy(
            TrendFilterStrategy,
            up_period=params['up_period'],
            down_period=params['up_period'],
            ema50_period=params['ema50_period'],
            ema200_period=params['ema200_period'],
            adx_period=14,
            adx_threshold=params['adx_threshold'],
            atr_period=14,
            analysis_bars=5,
            pullback_wait_bars=20,
            risk_percent=1.0,
            debug=False  # 静默模式
        )
        
        # 设置资金
        cerebro.broker.set_cash(10000.0)
        
        # ✅ Bug #11修复: 使用ForexCommissionInfo正确计算盈亏
        forex_comm = create_forex_commission(symbol=symbol, leverage=30.0)
        cerebro.broker.addcommissioninfo(forex_comm)
        
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
        
        result = {
            'status': 'success',
            'symbol': symbol,
            'params': params,
            'bars': len(df),
            'initial_cash': 10000.0,
            'final_value': cerebro.broker.get_value(),
            'total_return': returns.get('rtot', 0) * 100,
            'annual_return': returns.get('rnorm', 0) * 100,
            'max_drawdown': drawdown.get('max', {}).get('drawdown', 0),
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
        
        return result
        
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }


def run_multi_symbol_test():
    """运行多品种测试"""
    
    print("="*80)
    print("                     多品种回测测试系统")
    print("="*80)
    print()
    print("测试目标：")
    print("  1. 验证策略在不同品种上的稳健性")
    print("  2. 为不同品种找到最优参数")
    print()
    print("="*80)
    print()
    
    # 存储所有结果
    all_results = []
    
    # 遍历所有品种
    for symbol, config in SYMBOLS.items():
        print(f"\n{'='*80}")
        print(f"测试品种: {symbol} - {config['description']}")
        print(f"{'='*80}")
        
        if not os.path.exists(config['file']):
            print(f"⚠️  数据文件不存在: {config['file']}")
            print("   请先下载数据文件")
            continue
        
        # 测试不同参数组合
        symbol_results = []
        
        for adx_threshold in PARAM_GRID['adx_threshold']:
            params = {
                'adx_threshold': adx_threshold,
                'ema50_period': PARAM_GRID['ema50_period'][0],
                'ema200_period': PARAM_GRID['ema200_period'][0],
                'up_period': PARAM_GRID['up_period'][0],
            }
            
            print(f"\n  测试参数: ADX阈值={adx_threshold}")
            
            result = test_single_symbol(symbol, config, params, silent=True)
            
            if result['status'] == 'success':
                symbol_results.append(result)
                all_results.append(result)
                
                print(f"    收益: {result['total_return']:+.2f}%")
                print(f"    交易数: {result['total_trades']}笔")
                print(f"    胜率: {result['win_rate']:.1f}%")
                print(f"    盈亏比: {result['profit_factor']:.2f}")
                print(f"    回撤: {result['max_drawdown']:.2f}%")
            else:
                print(f"    ❌ 测试失败: {result.get('message', 'Unknown error')}")
        
        # 显示该品种的最佳参数
        if symbol_results:
            best_result = max(symbol_results, key=lambda x: x['total_return'])
            print(f"\n  ✅ {symbol}最佳参数:")
            print(f"     ADX阈值: {best_result['params']['adx_threshold']}")
            print(f"     总收益: {best_result['total_return']:+.2f}%")
            print(f"     盈亏比: {best_result['profit_factor']:.2f}")
    
    print(f"\n\n{'='*80}")
    print("                        汇总报告")
    print("="*80)
    print()
    
    if not all_results:
        print("❌ 没有成功的测试结果")
        return
    
    # 按品种汇总
    summary_by_symbol = {}
    for result in all_results:
        symbol = result['symbol']
        if symbol not in summary_by_symbol:
            summary_by_symbol[symbol] = []
        summary_by_symbol[symbol].append(result)
    
    # 显示每个品种的最佳结果
    print("📊 各品种表现（最佳参数）:\n")
    print(f"{'品种':<10} {'ADX阈值':<10} {'收益率':<10} {'胜率':<10} {'盈亏比':<10} {'回撤':<10} {'交易数':<10}")
    print("-"*80)
    
    total_returns = []
    for symbol, results in summary_by_symbol.items():
        best = max(results, key=lambda x: x['total_return'])
        total_returns.append(best['total_return'])
        
        print(f"{symbol:<10} "
              f"{best['params']['adx_threshold']:<10} "
              f"{best['total_return']:+.2f}%{'':<4} "
              f"{best['win_rate']:.1f}%{'':<4} "
              f"{best['profit_factor']:.2f}{'':<6} "
              f"{best['max_drawdown']:.2f}%{'':<4} "
              f"{best['total_trades']:<10}")
    
    print()
    print("="*80)
    print("📈 稳健性分析:\n")
    
    if len(total_returns) > 1:
        avg_return = sum(total_returns) / len(total_returns)
        std_return = (sum((r - avg_return)**2 for r in total_returns) / len(total_returns))**0.5
        
        print(f"  平均收益: {avg_return:+.2f}%")
        print(f"  收益标准差: {std_return:.2f}%")
        print(f"  收益范围: {min(total_returns):+.2f}% ~ {max(total_returns):+.2f}%")
        
        if std_return / abs(avg_return) < 0.5 if avg_return != 0 else std_return < 2:
            print(f"\n  ✅ 策略在不同品种上表现较为稳定")
        else:
            print(f"\n  ⚠️  策略在不同品种上表现差异较大，建议使用品种特定参数")
    else:
        print("  ⚠️  只有一个品种的测试结果，无法评估稳健性")
    
    print()
    print("="*80)
    
    # 保存结果到CSV
    if all_results:
        df_results = pd.DataFrame([
            {
                'symbol': r['symbol'],
                'adx_threshold': r['params']['adx_threshold'],
                'total_return': r['total_return'],
                'win_rate': r['win_rate'],
                'profit_factor': r['profit_factor'],
                'max_drawdown': r['max_drawdown'],
                'total_trades': r['total_trades'],
                'sharpe_ratio': r['sharpe_ratio']
            }
            for r in all_results
        ])
        
        report_path = f"./results/reports/multi_symbol_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        df_results.to_csv(report_path, index=False, encoding='utf-8-sig')
        print(f"✓ 详细结果已保存: {report_path}")
        print()


if __name__ == '__main__':
    import time
    start_time = time.time()
    
    run_multi_symbol_test()
    
    elapsed_time = time.time() - start_time
    print(f"\n⏱️  总耗时: {elapsed_time:.2f} 秒\n")
