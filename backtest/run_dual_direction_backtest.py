"""
双向趋势追踪策略回测脚本

策略说明:
  - 基于 EMA5/EMA20/EMA200 组合K线穿越信号
  - 分形高低点作为初始止损
  - 动态追踪止损（保本 → 追踪两阶段）
  - 多空双向交易
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime

if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from config_dual_direction import get_default_config, _BACKTEST_DIR
from strategies.dual_direction_trend_strategy import DualDirectionTrendStrategy
from utils.data_loader import CSVDataLoader
from utils.forex_commission import create_forex_commission, get_quote_usd_rate, get_pair_type, get_contract_size


def run_dual_direction_backtest(config=None):
    """运行双向趋势追踪策略回测"""

    if config is None:
        config = get_default_config()

    print("=" * 80)
    print("           双向趋势追踪策略回测系统 (Dual-Direction Trend Trailing)")
    print("=" * 80)
    print()
    print("策略说明:")
    print("  • EMA5/EMA20 均线穿越 + EMA200 大趋势方向过滤")
    print("  • 组合K线逻辑（当前+前一根）减少假信号")
    print("  • 分形高低点作为初始止损位")
    print("  • 阶段一: 浮盈 ≥ 1×ATR → 保本止损")
    print("  • 阶段二: max(EMA20 ± 0.5×ATR, close ∓ trailingDist) 追踪")
    print("=" * 80)
    print()

    # ---- 加载数据 ----
    print("📊 加载数据...")
    loader = CSVDataLoader(filepath=config.data_path)
    df = loader.load_data()

    if not loader.validate_data():
        print("❌ 数据验证失败")
        return

    print(f"✓ 数据: {len(df)} 根K线  [{df.index[0]} → {df.index[-1]}]")
    print()

    # ---- 推断品种名称 ----
    import re
    symbol_match = re.search(r'([A-Z]{3}_[A-Z]{3}|[A-Z]{6})', os.path.basename(config.data_path))
    symbol_name = symbol_match.group(1).replace('_', '') if symbol_match else 'GBPUSD'

    # ---- 搭建 Cerebro ----
    print("🎯 配置回测引擎...")
    cerebro = bt.Cerebro()

    data_feed = loader.to_backtrader_feed()
    cerebro.adddata(data_feed)

    # 贵金属 M5 分形距离天然更小（绝对值）。
    # stop_loss 已经包含 sl_initial_atr_mult×ATR buffer，对金银直接禁用 min_trailing 过滤；
    # 普通外汇保持 config 默认值 (1.5×ATR)，防止震荡行情频繁入场。
    pair_type_local = get_pair_type(symbol_name)
    sym_upper = symbol_name.upper()
    if sym_upper in ('XAUUSD', 'XAGUSD'):
        min_trailing = 0.0   # 已有 ATR buffer，无需额外过滤
    else:
        min_trailing = config.min_trailing_dist_atr

    cerebro.addstrategy(
        DualDirectionTrendStrategy,
        ema_fast_len=config.ema_fast_len,
        ema_slow_len=config.ema_slow_len,
        ema_base_len=config.ema_base_len,
        atr_len=config.atr_len,
        check_volume=config.check_volume,
        vol_sma_len=config.vol_sma_len,
        vol_mult=config.vol_mult,
        fractal_period=config.fractal_period,
        sl_initial_atr_mult=config.sl_initial_atr_mult,
        sl_breakeven_atr_mult=config.sl_breakeven_atr_mult,
        sl_trailing_atr_mult=config.sl_trailing_atr_mult,
        min_trailing_dist_atr=min_trailing,
        cooldown_bars=config.cooldown_bars,
        risk_percent=config.risk_percent,
        total_account_size=config.initial_cash,
        pair_type=pair_type_local,
        quote_usd_rate=get_quote_usd_rate(symbol_name),
        contract_size=get_contract_size(symbol_name),
        min_lot=config.min_lot,
        max_lot=config.max_lot,
        debug=config.debug,
        # 开仓报告
        symbol=symbol_name,
        enable_trade_report=config.enable_trade_report,
        report_dir=config.report_dir,
        max_reports=config.max_reports,
    )

    cerebro.broker.set_cash(config.initial_cash)
    forex_comm = create_forex_commission(symbol=symbol_name, leverage=30.0,
                                         lot_size=get_contract_size(symbol_name))
    cerebro.broker.addcommissioninfo(forex_comm)

    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')

    print()
    print("🚀 开始回测...")
    print("-" * 80)
    print()

    results = cerebro.run()
    strat = results[0]

    print()
    print("-" * 80)
    print()

    # ---- 分析结果 ----
    returns_a = strat.analyzers.returns.get_analysis()
    drawdown_a = strat.analyzers.drawdown.get_analysis()
    trades_a = strat.analyzers.trades.get_analysis()
    sharpe_a = strat.analyzers.sharpe.get_analysis()

    print("=" * 80)
    print("                         详细分析报告")
    print("=" * 80)
    print()

    total_return = returns_a.get('rtot', 0) * 100
    annual_return = returns_a.get('rnorm', 0) * 100
    max_dd = drawdown_a.get('max', {}).get('drawdown', 0)
    max_dd_len = drawdown_a.get('max', {}).get('len', 0)
    sharpe = sharpe_a.get('sharperatio', 'N/A')

    total_trades = trades_a.get('total', {}).get('closed', 0)
    won_trades = trades_a.get('won', {}).get('total', 0)
    lost_trades = trades_a.get('lost', {}).get('total', 0)
    avg_win = trades_a.get('won', {}).get('pnl', {}).get('average', 0)
    avg_loss = trades_a.get('lost', {}).get('pnl', {}).get('average', 0)
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0
    max_win_streak = trades_a.get('streak', {}).get('won', {}).get('longest', 0)
    max_loss_streak = trades_a.get('streak', {}).get('lost', {}).get('longest', 0)

    print("📈 收益指标:")
    print(f"  总收益率:   {total_return:.2f}%")
    print(f"  年化收益率: {annual_return:.2f}%")
    print(f"  夏普比率:   {sharpe}")
    print()

    print("📉 风险指标:")
    print(f"  最大回撤:   {max_dd:.2f}%")
    print(f"  最长回撤期: {max_dd_len} 根K线")
    print()

    print("💼 交易统计:")
    if total_trades > 0:
        print(f"  总交易数:   {total_trades}")
        print(f"  盈利交易:   {won_trades} ({win_rate:.1f}%)")
        print(f"  亏损交易:   {lost_trades} ({100 - win_rate:.1f}%)")
        print(f"  平均盈利:   ${avg_win:.2f}")
        print(f"  平均亏损:   ${avg_loss:.2f}")
        print(f"  盈亏比:     {profit_factor:.2f}")
    else:
        print("  没有完成的交易")
    print()

    print("🎲 连续盈亏:")
    print(f"  最大连胜: {max_win_streak} 次")
    print(f"  最大连败: {max_loss_streak} 次")
    print()
    print("=" * 80)
    print()

    # ---- 保存报告 ----
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_dir = os.path.join(_BACKTEST_DIR, 'results', 'reports')
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f'dual_direction_report_{symbol_name}_{timestamp}.txt')

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write(f"双向趋势追踪策略回测报告 — {symbol_name}\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"策略配置:\n")
        f.write(f"  EMA: {config.ema_fast_len} / {config.ema_slow_len} / {config.ema_base_len}\n")
        f.write(f"  ATR 周期: {config.atr_len}\n")
        f.write(f"  分形周期: {config.fractal_period}\n")
        f.write(f"  初始止损 ATR 倍数: {config.sl_initial_atr_mult}\n")
        f.write(f"  风险: {config.risk_percent}%\n\n")
        f.write(f"收益指标:\n")
        f.write(f"  总收益率:   {total_return:.2f}%\n")
        f.write(f"  年化收益率: {annual_return:.2f}%\n")
        f.write(f"  夏普比率:   {sharpe}\n\n")
        f.write(f"风险指标:\n")
        f.write(f"  最大回撤:   {max_dd:.2f}%\n\n")
        f.write(f"交易统计:\n")
        if total_trades > 0:
            f.write(f"  总交易数: {total_trades}\n")
            f.write(f"  胜率: {win_rate:.1f}%\n")
            f.write(f"  盈亏比: {profit_factor:.2f}\n")

    print(f"  ✓ 报告已保存: {report_path}")
    print()


if __name__ == '__main__':
    import argparse
    import time

    parser = argparse.ArgumentParser(description='双向趋势追踪策略回测')
    parser.add_argument('--symbol', type=str, default='GBPUSD',
                        help='交易品种 (GBPUSD, USDJPY, EURUSD, AUDUSD, AUDJPY, XAUUSD, XAGUSD)')
    parser.add_argument('--risk', type=float, default=1.0,
                        help='风险百分比 (默认: 1.0)')
    parser.add_argument('--no-debug', action='store_true',
                        help='关闭详细日志（加快速度）')
    parser.add_argument('--report', action='store_true',
                        help='开启开仓报告生成（markdown + K线图）')
    parser.add_argument('--report-dir', type=str, default='',
                        help='报告输出目录，默认 backtest/results/trade_reports/')
    parser.add_argument('--max-reports', type=int, default=0,
                        help='最多生成报告数（0=不限制）')
    args = parser.parse_args()

    symbol_map = {
        'GBPUSD': 'GBP_USD_M5.csv',
        'USDJPY': 'USD_JPY_M5.csv',
        'EURUSD': 'EUR_USD_M5.csv',
        'AUDUSD': 'AUD_USD_M5.csv',
        'AUDJPY': 'AUD_JPY_M5.csv',
        'XAUUSD': 'XAU_USD_M5.csv',
        'XAGUSD': 'XAG_USD_M5.csv',
    }

    symbol_clean = args.symbol.upper().replace('_', '').replace('/', '')
    data_file = symbol_map.get(symbol_clean, f'{args.symbol}_M5.csv')

    config = get_default_config()
    config.data_path = os.path.join(_BACKTEST_DIR, 'data', data_file)
    config.risk_percent = args.risk
    config.debug = not args.no_debug
    config.enable_trade_report = args.report
    config.report_dir = args.report_dir or os.path.join(
        _BACKTEST_DIR, 'results', 'trade_reports', symbol_clean
    )
    config.max_reports = args.max_reports

    print(f"📊 测试品种: {symbol_clean}")
    print(f"📁 数据文件: {config.data_path}")
    print(f"💰 风险设置: {config.risk_percent}%")
    print()

    start_time = time.time()
    run_dual_direction_backtest(config=config)
    print(f"⏱️  回测耗时: {time.time() - start_time:.2f} 秒\n")
