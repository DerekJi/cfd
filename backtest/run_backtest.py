"""
主运行脚本
Main script to run backtest
"""

import sys
import os
from datetime import datetime

# 修复Windows终端编码问题
if sys.platform == 'win32':
    import codecs
    # 检查是否已经被包装过
    if not isinstance(sys.stdout, codecs.StreamWriter):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# 添加路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import backtrader as bt
from config import *
from utils.data_loader import CSVDataLoader, create_sample_data
from strategies.range_breakout_v3 import RangeBreakoutStrategy
from utils.analyzers import (
    DetailedTradeAnalyzer,
    DrawdownAnalyzer,
    StateTransitionAnalyzer,
    WinStreakAnalyzer
)


def run_backtest(use_sample_data=True):
    """
    运行回测
    
    Args:
        use_sample_data: 是否使用示例数据
    """
    print("\n" + "="*80)
    print(" "*25 + "半自动交易策略回测系统 V3.0")
    print("="*80 + "\n")
    
    # 1. 创建Cerebro引擎
    cerebro = bt.Cerebro()
    
    # 2. 加载数据
    if use_sample_data:
        print("📊 使用示例数据进行回测...")
        data_path = DATA_CONFIG.get('test_data_path', './backtest/data/EURUSD_5m_test.csv')
        
        # 生成示例数据
        if not os.path.exists(data_path):
            print("  └─ 生成示例数据...")
            create_sample_data(data_path, num_bars=2000)
    else:
        print("📊 加载真实数据...")
        data_path = DATA_CONFIG['data_path']
        
        if not os.path.exists(data_path):
            print(f"\n❌ 数据文件不存在: {data_path}")
            print("\n💡 如何获取真实数据？")
            print("="*60)
            print("选项1（推荐）: 使用数据下载工具")
            print("  python download_data.py")
            print("\n选项2: 手动下载")
            print("  1. 访问 https://www.histdata.com/")
            print("  2. 下载 EUR/USD M1 数据")
            print(f"  3. 保存到: {os.path.abspath(data_path)}")
            print("\n选项3: 查看完整指南")
            print("  docs/数据获取指南.md")
            print("="*60)
            return
    
    # 加载数据
    loader = CSVDataLoader(data_path)
    df = loader.load_data(
        start_date=DATA_CONFIG.get('start_date'),
        end_date=DATA_CONFIG.get('end_date')
    )
    loader.validate_data()
    
    # 转换为Backtrader数据源
    data_feed = loader.to_backtrader_feed()
    cerebro.adddata(data_feed)
    
    # 3. 添加策略
    print("\n🎯 配置策略参数...")
    cerebro.addstrategy(
        RangeBreakoutStrategy,
        lookback_period=RANGE_DETECTION_CONFIG['lookback_period'],
        atr_period=ATR_CONFIG['period'],
        buffer_multiplier=ATR_CONFIG['buffer_multiplier'],
        confirm_bars=STRATEGY_CONFIG['confirm_bars'],
        max_wait_bars=STRATEGY_CONFIG['max_wait_bars'],
        trailing_stop=STRATEGY_CONFIG['trailing_stop_enabled'],
        risk_percent=RISK_CONFIG['risk_percent'],
        min_lots=RISK_CONFIG['min_lots'],
        max_lots=RISK_CONFIG['max_lots'],
        spread_pips=RISK_CONFIG['spread_pips'],
        debug=True
    )
    
    # 4. 设置初始资金和外汇交易佣金
    cerebro.broker.set_cash(BACKTEST_CONFIG['cerebro_cash'])
    
    # 设置外汇交易佣金模式
    cerebro.broker.setcommission(
        commission=BACKTEST_CONFIG['cerebro_commission'],
        margin=None,  # 不使用保证金
        mult=1.0,  # 乘数为1
        commtype=bt.CommInfoBase.COMM_FIXED,  # 固定佣金
        stocklike=True  # 按股票模式（直接用资金购买）
    )
    
    # 5. 添加分析器
    print("  └─ 添加分析器...")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(DetailedTradeAnalyzer, _name='detailed_trades')
    cerebro.addanalyzer(DrawdownAnalyzer, _name='custom_drawdown')
    cerebro.addanalyzer(StateTransitionAnalyzer, _name='state_transitions')
    cerebro.addanalyzer(WinStreakAnalyzer, _name='win_streak')
    
    # 6. 运行回测
    print("\n🚀 开始回测...\n")
    print("-"*80)
    
    start_time = datetime.now()
    results = cerebro.run()
    end_time = datetime.now()
    
    print("-"*80)
    print(f"\n⏱️  回测耗时: {(end_time - start_time).total_seconds():.2f} 秒\n")
    
    # 7. 分析结果
    strat = results[0]
    
    print("="*80)
    print(" "*30 + "详细分析报告")
    print("="*80 + "\n")
    
    # 基础指标
    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    returns = strat.analyzers.returns.get_analysis()
    trades = strat.analyzers.trades.get_analysis()
    
    print("📈 收益指标:")
    print(f"  总收益率: {returns.get('rtot', 0) * 100:.2f}%")
    print(f"  年化收益率: {returns.get('rnorm', 0) * 100:.2f}%")
    sharpe_ratio = sharpe.get('sharperatio')
    print(f"  夏普比率: {sharpe_ratio if sharpe_ratio is not None else 'N/A'}")
    
    print("\n📉 风险指标:")
    print(f"  最大回撤: {drawdown.get('max', {}).get('drawdown', 0):.2f}%")
    print(f"  最长回撤期: {drawdown.get('max', {}).get('len', 0)} 根K线")
    
    print("\n💼 交易统计:")
    total_trades = trades.get('total', {}).get('total', 0)
    won_trades = trades.get('won', {}).get('total', 0)
    lost_trades = trades.get('lost', {}).get('total', 0)
    
    print(f"  总交易数: {total_trades}")
    if total_trades > 0:
        print(f"  盈利交易: {won_trades} ({won_trades/total_trades*100:.1f}%)")
        print(f"  亏损交易: {lost_trades} ({lost_trades/total_trades*100:.1f}%)")
        
        avg_win = trades.get('won', {}).get('pnl', {}).get('average', 0)
        avg_loss = trades.get('lost', {}).get('pnl', {}).get('average', 0)
        print(f"  平均盈利: ${avg_win:.2f}")
        print(f"  平均亏损: ${avg_loss:.2f}")
        
        if avg_loss != 0:
            print(f"  盈亏比: {abs(avg_win/avg_loss):.2f}")
    
    # 自定义分析器结果
    detailed_trades = strat.analyzers.detailed_trades.get_analysis()
    win_streak = strat.analyzers.win_streak.get_analysis()
    state_transitions = strat.analyzers.state_transitions.get_analysis()
    
    print("\n🎲 连续盈亏:")
    print(f"  最大连胜: {win_streak['max_win_streak']} 次")
    print(f"  最大连败: {win_streak['max_loss_streak']} 次")
    
    print("\n🔄 状态机统计:")
    print(f"  状态转换次数: {state_transitions['total_transitions']}")
    avg_duration = state_transitions['avg_state_duration']
    state_names = ['IDLE', 'TOUCHING', 'TOUCHED', 'RETRACED', 'POSITION']
    for state, duration in avg_duration.items():
        if duration > 0:
            print(f"  {state_names[state]} 平均持续: {duration:.1f} 根K线")
    
    print("\n" + "="*80 + "\n")
    
    # 8. 保存结果
    if BACKTEST_CONFIG['save_results']:
        save_results(strat, detailed_trades)
    
    # 9. 绘制图表
    if BACKTEST_CONFIG['plot_results']:
        print("📊 生成图表...")
        try:
            cerebro.plot(style='candlestick', barup='green', bardown='red')
        except Exception as e:
            print(f"  ⚠️  图表生成失败: {e}")
            print("  提示: 可能需要在非交互环境中禁用绘图")
    
    return strat


def save_results(strategy, detailed_trades):
    """保存回测结果"""
    try:
        os.makedirs(OUTPUT_CONFIG['reports_dir'], exist_ok=True)
        
        # 生成报告文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = os.path.join(
            OUTPUT_CONFIG['reports_dir'],
            f'backtest_report_{timestamp}.txt'
        )
        
        # 保存详细交易记录
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write(" "*25 + "详细交易记录\n")
            f.write("="*80 + "\n\n")
            
            for i, trade in enumerate(detailed_trades['trades'], 1):
                f.write(f"交易 #{i}\n")
                f.write(f"  入场时间: {trade['entry_date']}\n")
                f.write(f"  出场时间: {trade['exit_date']}\n")
                f.write(f"  持仓时间: {trade['holding_bars']} 根K线\n")
                f.write(f"  入场价格: {trade['entry_price']:.5f}\n")
                f.write(f"  出场价格: {trade['exit_price']:.5f}\n")
                f.write(f"  盈亏: ${trade['pnl']:.2f} ({trade['pnl_percent']:.2f}%)\n")
                f.write("\n")
        
        print(f"  ✓ 报告已保存: {report_path}")
        
    except Exception as e:
        print(f"  ⚠️  保存结果失败: {e}")


if __name__ == '__main__':
    # 运行回测
    # 使用真实数据
    run_backtest(use_sample_data=False)
    
    # 如果只想用示例数据测试，取消注释下面这行
    # run_backtest(use_sample_data=False)
