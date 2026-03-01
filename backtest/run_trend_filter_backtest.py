"""
趋势过滤策略回测脚本

使用ADX+EMA200过滤假突破
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime

# 设置UTF-8编码
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtrader as bt
from config_trend_filter import get_default_config
from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader
from utils.forex_commission import create_forex_commission, get_quote_usd_rate


def run_trend_filter_backtest(use_sample_data=False, config=None):
    """运行趋势过滤策略回测"""
    
    # 加载配置
    if config is None:
        config = get_default_config()
    
    print("="*80)
    print("                 趋势过滤突破策略回测系统 V1.0")
    print("="*80)
    print()
    print("策略说明:")
    print("  • ADX > 25: 强趋势市场")
    print("  • 向上突破 + 价格 > EMA200 → 确认上升趋势 → 等回踩做多")
    print("  • 向下突破 + 价格 < EMA200 → 确认下降趋势 → 等回踩做空")
    print("  • 不满足条件的突破直接放弃，避免假突破")
    print("="*80)
    print()
    
    # 加载数据
    print("📊 加载数据...")
    loader = CSVDataLoader(filepath=config.data_path)
    df = loader.load_data()
    
    if not loader.validate_data():
        print("❌ 数据验证失败")
        return
    
    print(f"✓ 数据加载成功: {len(df)} 根K线")
    print(f"  时间范围: {df.index[0]} 至 {df.index[-1]}")
    print(f"  数据列: {df.columns.tolist()}")
    print("✓ 数据验证通过")
    print()
    
    # 配置回测引擎
    print("🎯 配置回测引擎...")
    cerebro = bt.Cerebro()
    
    # 添加数据
    data_feed = loader.to_backtrader_feed()
    cerebro.adddata(data_feed)
    
    # ✅ 从数据文件路径推断品种名称
    import re
    symbol_match = re.search(r'([A-Z]{3}_[A-Z]{3}|[A-Z]{6})', os.path.basename(config.data_path))
    symbol_name = symbol_match.group(1) if symbol_match else 'GBPUSD'
    
    # 添加策略
    cerebro.addstrategy(
        TrendFilterStrategy,
        up_period=config.up_period,
        down_period=config.down_period,
        ema50_period=config.ema50_period,
        ema200_period=config.ema200_period,
        adx_period=config.adx_period,
        adx_threshold=config.adx_threshold,
        atr_period=config.atr_period,
        analysis_bars=config.analysis_bars,
        pullback_wait_bars=config.pullback_wait_bars,
        risk_percent=config.risk_percent,
        quote_usd_rate=get_quote_usd_rate(symbol_name),
        min_lot=config.min_lot,
        max_lot=config.max_lot,
        max_cash_ratio=config.max_cash_ratio,
        debug=config.debug
    )
    
    # 设置资金
    cerebro.broker.set_cash(config.initial_cash)
    
    # ✅ Bug #11修复: 使用ForexCommissionInfo正确计算盈亏
    forex_comm = create_forex_commission(symbol=symbol_name, leverage=30.0)
    cerebro.broker.addcommissioninfo(forex_comm)
    
    # 添加分析器
    print("  └─ 添加分析器...")
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    
    print()
    print("🚀 开始回测...")
    print("-"*80)
    print()
    
    # 运行回测
    results = cerebro.run()
    strat = results[0]
    
    print()
    print("-"*80)
    print()
    
    # 获取分析结果
    returns_analyzer = strat.analyzers.returns.get_analysis()
    drawdown_analyzer = strat.analyzers.drawdown.get_analysis()
    trades_analyzer = strat.analyzers.trades.get_analysis()
    sharpe_analyzer = strat.analyzers.sharpe.get_analysis()
    
    # 打印详细报告
    print("="*80)
    print("                         详细分析报告")
    print("="*80)
    print()
    
    # 收益指标
    print("📈 收益指标:")
    total_return = returns_analyzer.get('rtot', 0) * 100
    annual_return = returns_analyzer.get('rnorm', 0) * 100
    print(f"  总收益率: {total_return:.2f}%")
    print(f"  年化收益率: {annual_return:.2f}%")
    print(f"  夏普比率: {sharpe_analyzer.get('sharperatio', 'N/A')}")
    print()
    
    # 风险指标
    print("📉 风险指标:")
    max_dd = drawdown_analyzer.get('max', {}).get('drawdown', 0)
    max_dd_len = drawdown_analyzer.get('max', {}).get('len', 0)
    print(f"  最大回撤: {max_dd:.2f}%")
    print(f"  最长回撤期: {max_dd_len} 根K线")
    print()
    
    # 交易统计
    print("💼 交易统计:")
    total_trades = trades_analyzer.get('total', {}).get('closed', 0)
    won_trades = trades_analyzer.get('won', {}).get('total', 0)
    lost_trades = trades_analyzer.get('lost', {}).get('total', 0)
    
    if total_trades > 0:
        win_rate = (won_trades / total_trades) * 100
        avg_win = trades_analyzer.get('won', {}).get('pnl', {}).get('average', 0)
        avg_loss = trades_analyzer.get('lost', {}).get('pnl', {}).get('average', 0)
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        print(f"  总交易数: {total_trades}")
        print(f"  盈利交易: {won_trades} ({win_rate:.1f}%)")
        print(f"  亏损交易: {lost_trades} ({100-win_rate:.1f}%)")
        print(f"  平均盈利: ${avg_win:.2f}")
        print(f"  平均亏损: ${avg_loss:.2f}")
        print(f"  盈亏比: {profit_factor:.2f}")
    else:
        print("  没有完成的交易")
    print()
    
    # 连续盈亏
    print("🎲 连续盈亏:")
    max_win_streak = trades_analyzer.get('streak', {}).get('won', {}).get('longest', 0)
    max_loss_streak = trades_analyzer.get('streak', {}).get('lost', {}).get('longest', 0)
    print(f"  最大连胜: {max_win_streak} 次")
    print(f"  最大连败: {max_loss_streak} 次")
    print()
    
    print("="*80)
    print()
    
    # 保存报告
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = f"./results/reports/trend_filter_report_{timestamp}.txt"
    
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("趋势过滤突破策略回测报告\n")
        f.write("="*80 + "\n\n")
        
        f.write("策略配置:\n")
        f.write(f"  UP/DOWN周期: {config.up_period}\n")
        f.write(f"  EMA周期: {config.ema50_period} / {config.ema200_period}\n")
        f.write(f"  ADX周期: {config.adx_period} (阈值: {config.adx_threshold})\n")
        f.write(f"  风险管理: {config.risk_percent}%\n\n")
        
        f.write("收益指标:\n")
        f.write(f"  总收益率: {total_return:.2f}%\n")
        f.write(f"  年化收益率: {annual_return:.2f}%\n")
        f.write(f"  夏普比率: {sharpe_analyzer.get('sharperatio', 'N/A')}\n\n")
        
        f.write("风险指标:\n")
        f.write(f"  最大回撤: {max_dd:.2f}%\n")
        f.write(f"  最长回撤期: {max_dd_len} 根K线\n\n")
        
        f.write("交易统计:\n")
        if total_trades > 0:
            f.write(f"  总交易数: {total_trades}\n")
            f.write(f"  盈利交易: {won_trades} ({win_rate:.1f}%)\n")
            f.write(f"  亏损交易: {lost_trades} ({100-win_rate:.1f}%)\n")
            f.write(f"  平均盈利: ${avg_win:.2f}\n")
            f.write(f"  平均亏损: ${avg_loss:.2f}\n")
            f.write(f"  盈亏比: {profit_factor:.2f}\n")
        else:
            f.write("  没有完成的交易\n")
    
    print(f"  ✓ 报告已保存: {report_path}")
    print()


if __name__ == '__main__':
    import argparse
    import time
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='趋势过滤策略回测')
    parser.add_argument('--symbol', type=str, default='GBPUSD',
                       help='交易品种 (GBPUSD, USDJPY, XAUUSD, XAGUSD等)')
    parser.add_argument('--risk', type=float, default=1.0,
                       help='风险百分比 (默认: 1.0)')
    parser.add_argument('--start-date', type=str, default=None,
                       help='起始日期 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default=None,
                       help='结束日期 (YYYY-MM-DD)')
    args = parser.parse_args()
    
    # 根据symbol设置数据路径
    symbol_map = {
        'GBPUSD': 'GBP_USD_M5.csv',
        'USDJPY': 'USD_JPY_M5.csv',
        'EURUSD': 'EUR_USD_M5.csv',
        'AUDUSD': 'AUD_USD_M5.csv',
        'AUDJPY': 'AUD_JPY_M5.csv',
        'XAUUSD': 'XAU_USD_M5.csv',
        'XAGUSD': 'XAG_USD_M5.csv',
    }
    
    # 转换symbol格式（移除下划线和斜杠）
    symbol_clean = args.symbol.upper().replace('_', '').replace('/', '')
    data_file = symbol_map.get(symbol_clean, f'{args.symbol}_M5.csv')
    
    # 计时
    start_time = time.time()
    
    # 修改配置
    import os as _os
    from config_trend_filter import get_default_config, _BACKTEST_DIR
    config = get_default_config()
    config.data_path = _os.path.join(_BACKTEST_DIR, 'data', data_file)
    config.risk_percent = args.risk
    
    print(f"📊 测试品种: {symbol_clean}")
    print(f"📁 数据文件: {config.data_path}")
    print(f"💰 风险设置: {config.risk_percent}%")
    print()
    
    # 运行回测（传递修改后的config）
    run_trend_filter_backtest(use_sample_data=False, config=config)
    
    # 输出耗时
    elapsed_time = time.time() - start_time
    print(f"\n⏱️  回测耗时: {elapsed_time:.2f} 秒\n")
