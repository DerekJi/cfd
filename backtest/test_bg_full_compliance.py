"""
Blue Guardian 完整合规性测试

检查三项风控指标:
1. 单笔亏损 < $50 (1%)
2. 单日亏损 < $150 (3%)  
3. 从初始余额算起的总回撤 < $300 (6%)

详细报告指标:
- 单笔最大亏损/盈利
- 最多连续亏损/盈利次数
- 单日最大亏损/盈利
- 胜率、盈亏比、总收益
"""

import sys
import os
from collections import defaultdict, OrderedDict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import backtrader as bt
from strategies.trend_filter_strategy_v1 import TrendFilterStrategy
from utils.data_loader import CSVDataLoader
from utils.forex_commission import create_forex_commission, get_quote_usd_rate

ACCOUNT = 5000.0
SL_SINGLE = 50.0    # 单笔限额 $50 (1%)
SL_DAILY = 150.0     # 单日限额 $150 (3%)
SL_TOTAL = 300.0     # 总亏损限额 $300 (6%)


class FullTradeTracker(bt.Analyzer):
    """完整交易追踪器"""

    def __init__(self):
        self.trades = []
        self.daily_equity = OrderedDict()
        self.daily_pnl = defaultdict(float)

    def next(self):
        dt = self.strategy.datetime.date()
        self.daily_equity[dt] = self.strategy.broker.get_value()

    def notify_trade(self, trade):
        if trade.isclosed:
            dt = self.strategy.datetime.date()
            pnl = trade.pnlcomm
            self.trades.append({
                'date': dt,
                'pnl': pnl,
                'size': trade.size,
                'price': trade.price,
            })
            self.daily_pnl[dt] += pnl

    def get_analysis(self):
        trades = self.trades
        losses = [abs(t['pnl']) for t in trades if t['pnl'] < 0]
        wins = [t['pnl'] for t in trades if t['pnl'] > 0]

        # 连续亏损/盈利
        max_consec_loss = 0
        max_consec_win = 0
        cur_loss = 0
        cur_win = 0
        for t in trades:
            if t['pnl'] < 0:
                cur_loss += 1
                cur_win = 0
                max_consec_loss = max(max_consec_loss, cur_loss)
            elif t['pnl'] > 0:
                cur_win += 1
                cur_loss = 0
                max_consec_win = max(max_consec_win, cur_win)
            else:
                cur_loss = 0
                cur_win = 0

        # 日度统计
        daily = dict(self.daily_pnl)
        daily_losses = {d: v for d, v in daily.items() if v < 0}
        daily_wins = {d: v for d, v in daily.items() if v > 0}

        return {
            'trades': trades,
            'daily_equity': dict(self.daily_equity),
            'daily_pnl': daily,
            'n_trades': len(trades),
            'n_wins': len(wins),
            'n_losses': len(losses),
            'win_rate': len(wins) / len(trades) * 100 if trades else 0,
            'total_pnl': sum(t['pnl'] for t in trades),
            'max_single_loss': max(losses) if losses else 0,
            'max_single_win': max(wins) if wins else 0,
            'avg_loss': sum(losses) / len(losses) if losses else 0,
            'avg_win': sum(wins) / len(wins) if wins else 0,
            'profit_ratio': (sum(wins) / len(wins)) / (sum(losses) / len(losses)) if losses and wins else 0,
            'max_consec_loss': max_consec_loss,
            'max_consec_win': max_consec_win,
            'max_daily_loss': abs(min(daily.values())) if daily else 0,
            'max_daily_win': max(daily.values()) if daily else 0,
            'worst_day': min(daily, key=daily.get) if daily else None,
            'best_day': max(daily, key=daily.get) if daily else None,
            'n_loss_days': len(daily_losses),
            'n_win_days': len(daily_wins),
            'daily_losses': daily_losses,
            'daily_wins': daily_wins,
        }


def run_sym(symbol, datafile, cash, risk_pct, num_sym):
    loader = CSVDataLoader(filepath=datafile)
    loader.load_data()
    loader.validate_data()
    cerebro = bt.Cerebro()
    cerebro.adddata(loader.to_backtrader_feed())
    cerebro.addstrategy(
        TrendFilterStrategy,
        up_period=20, down_period=20,
        ema50_period=50, ema200_period=200,
        adx_period=14, adx_threshold=35,
        atr_period=14, analysis_bars=5, pullback_wait_bars=20,
        total_account_size=ACCOUNT,
        risk_percent=risk_pct,
        num_symbols=num_sym,
        quote_usd_rate=get_quote_usd_rate(symbol),
        debug=False,
    )
    cerebro.broker.set_cash(cash)
    cerebro.broker.addcommissioninfo(
        create_forex_commission(symbol=symbol, commission_per_lot=2.5, leverage=30.0)  # $2.5×2=$5 RT
    )
    cerebro.addanalyzer(FullTradeTracker, _name='tracker')
    results = cerebro.run()
    return results[0].analyzers.tracker.get_analysis()


def print_symbol_detail(sym, r):
    """打印单品种详细报告"""
    print(f'\n    --- {sym} 详细统计 ---')
    print(f'    交易总数: {r["n_trades"]}  (胜: {r["n_wins"]}  负: {r["n_losses"]})')
    print(f'    胜率: {r["win_rate"]:.1f}%')
    print(f'    盈亏比: {r["profit_ratio"]:.2f}')
    print(f'    总收益: ${r["total_pnl"]:+.2f}')
    print(f'    ')
    print(f'    单笔最大盈利: ${r["max_single_win"]:.2f}')
    print(f'    单笔最大亏损: ${r["max_single_loss"]:.2f}')
    print(f'    平均盈利: ${r["avg_win"]:.2f}')
    print(f'    平均亏损: ${r["avg_loss"]:.2f}')
    print(f'    ')
    print(f'    最多连续盈利: {r["max_consec_win"]} 笔')
    print(f'    最多连续亏损: {r["max_consec_loss"]} 笔')
    print(f'    ')
    print(f'    盈利天数: {r["n_win_days"]}  亏损天数: {r["n_loss_days"]}')
    print(f'    单日最大盈利: ${r["max_daily_win"]:.2f} ({r["best_day"]})')
    print(f'    单日最大亏损: ${r["max_daily_loss"]:.2f} ({r["worst_day"]})')


def check_portfolio(name, gbp_ratio, jpy_ratio, risk_pct):
    gbp_cash = ACCOUNT * gbp_ratio
    jpy_cash = ACCOUNT * jpy_ratio
    print(f'\n{"=" * 80}')
    print(f'  {name}')
    print(f'  GBPUSD {gbp_ratio*100:.0f}%=${gbp_cash:.0f}  '
          f'USDJPY {jpy_ratio*100:.0f}%=${jpy_cash:.0f}  '
          f'总=${ACCOUNT:.0f}  风险={risk_pct}%')
    print(f'{"=" * 80}')

    g = run_sym('GBP_USD', './data/GBP_USD_M5.csv', gbp_cash, risk_pct, 2)
    u = run_sym('USD_JPY', './data/USD_JPY_M5.csv', jpy_cash, risk_pct, 2)

    # ===== 各品种详细报告 =====
    print_symbol_detail('GBPUSD', g)
    print_symbol_detail('USDJPY', u)

    # ===== 组合统计 =====
    print(f'\n    --- 组合统计 ---')
    total_trades = g['n_trades'] + u['n_trades']
    total_pnl = g['total_pnl'] + u['total_pnl']
    total_wins = g['n_wins'] + u['n_wins']
    total_losses = g['n_losses'] + u['n_losses']
    combo_wr = total_wins / total_trades * 100 if total_trades else 0
    print(f'    总交易: {total_trades}  总收益: ${total_pnl:+.2f}')
    print(f'    组合胜率: {combo_wr:.1f}%')

    # ===== 1. 单笔亏损 =====
    print(f'\n  [1] 单笔亏损检查 (限额 ${SL_SINGLE:.0f})')
    for sym, r in [('GBPUSD', g), ('USDJPY', u)]:
        ok = 'PASS' if r['max_single_loss'] < SL_SINGLE else 'FAIL'
        print(f'      {sym}: 最大单笔亏损 ${r["max_single_loss"]:.2f}  [{ok}]')

    # ===== 2. 组合每日盈亏 =====
    all_dates = sorted(set(list(g['daily_pnl'].keys()) + list(u['daily_pnl'].keys())))
    combo_daily = {}
    for d in all_dates:
        combo_daily[d] = g['daily_pnl'].get(d, 0) + u['daily_pnl'].get(d, 0)

    daily_losses = {d: abs(v) for d, v in combo_daily.items() if v < 0}
    daily_wins = {d: v for d, v in combo_daily.items() if v > 0}
    max_daily_loss = max(daily_losses.values()) if daily_losses else 0
    max_daily_win = max(daily_wins.values()) if daily_wins else 0
    worst_day = max(daily_losses, key=daily_losses.get) if daily_losses else None
    best_day = max(daily_wins, key=daily_wins.get) if daily_wins else None

    print(f'\n  [2] 单日亏损检查 (限额 ${SL_DAILY:.0f})')
    ok2 = 'PASS' if max_daily_loss < SL_DAILY else 'FAIL'
    print(f'      组合最大单日亏损: ${max_daily_loss:.2f}  [{ok2}]  ({worst_day})')
    print(f'      组合最大单日盈利: ${max_daily_win:.2f}  ({best_day})')
    print(f'      组合盈利天数: {len(daily_wins)}  亏损天数: {len(daily_losses)}')
    top5_loss = sorted(daily_losses.items(), key=lambda x: x[1], reverse=True)[:5]
    top5_win = sorted(daily_wins.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f'      Top 5 最差交易日:')
    for d, loss in top5_loss:
        gp = g['daily_pnl'].get(d, 0)
        up = u['daily_pnl'].get(d, 0)
        print(f'        {d}: -${loss:.2f}  (GBP:${gp:+.2f}  JPY:${up:+.2f})')
    print(f'      Top 5 最佳交易日:')
    for d, win in top5_win:
        gp = g['daily_pnl'].get(d, 0)
        up = u['daily_pnl'].get(d, 0)
        print(f'        {d}: +${win:.2f}  (GBP:${gp:+.2f}  JPY:${up:+.2f})')

    # ===== 3. 组合权益曲线 =====
    all_eq_dates = sorted(set(
        list(g['daily_equity'].keys()) + list(u['daily_equity'].keys())
    ))
    last_g = gbp_cash
    last_u = jpy_cash
    combo_equity = OrderedDict()
    for d in all_eq_dates:
        if d in g['daily_equity']:
            last_g = g['daily_equity'][d]
        if d in u['daily_equity']:
            last_u = u['daily_equity'][d]
        combo_equity[d] = last_g + last_u

    min_equity = min(combo_equity.values())
    max_loss_from_start = ACCOUNT - min_equity
    min_eq_date = [d for d, v in combo_equity.items() if v == min_equity][0]
    max_equity = max(combo_equity.values())
    max_eq_date = [d for d, v in combo_equity.items() if v == max_equity][0]

    peak = ACCOUNT
    max_dd = 0
    max_dd_date = None
    for d, v in combo_equity.items():
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
            max_dd_date = d

    final_eq = list(combo_equity.values())[-1]

    print(f'\n  [3] 总回撤检查 (限额 ${SL_TOTAL:.0f})')
    ok3 = 'PASS' if max_loss_from_start < SL_TOTAL else 'FAIL'
    print(f'      从初始${ACCOUNT:.0f}算起最大浮亏: ${max_loss_from_start:.2f}  [{ok3}]')
    print(f'        最低点: ${min_equity:.2f} ({min_eq_date})')
    print(f'      Peak-to-Trough最大回撤: ${max_dd:.2f}')
    print(f'        日期: {max_dd_date}')
    print(f'      最高权益: ${max_equity:.2f} ({max_eq_date})')
    print(f'      最终权益: ${final_eq:.2f} (收益: ${final_eq - ACCOUNT:+.2f}, '
          f'{(final_eq - ACCOUNT) / ACCOUNT * 100:+.1f}%)')

    # ===== 综合判定 =====
    s1 = g['max_single_loss'] < SL_SINGLE and u['max_single_loss'] < SL_SINGLE
    s2 = max_daily_loss < SL_DAILY
    s3 = max_loss_from_start < SL_TOTAL

    print(f'\n  [综合判定]')
    print(f'    {"PASS" if s1 else "FAIL"} 单笔亏损: '
          f'GBP ${g["max_single_loss"]:.2f} / JPY ${u["max_single_loss"]:.2f} '
          f'(限额 ${SL_SINGLE:.0f})')
    print(f'    {"PASS" if s2 else "FAIL"} 单日亏损: '
          f'${max_daily_loss:.2f} (限额 ${SL_DAILY:.0f})')
    print(f'    {"PASS" if s3 else "FAIL"} 总回撤(从初始余额): '
          f'${max_loss_from_start:.2f} (限额 ${SL_TOTAL:.0f})')
    print(f'    INFO Peak-to-Trough回撤: ${max_dd:.2f}')

    if s1 and s2 and s3:
        print(f'    >>> Blue Guardian 全部合规 <<<')
    else:
        fails = []
        if not s1:
            fails.append('单笔亏损')
        if not s2:
            fails.append('单日亏损')
        if not s3:
            fails.append('总回撤')
        print(f'    >>> 未通过项: {", ".join(fails)} <<<')

    return s1, s2, s3, g, u


if __name__ == '__main__':
    print('=' * 80)
    print('  Blue Guardian 完整风控合规性测试')
    print(f'  账户: ${ACCOUNT:.0f}')
    print(f'  单笔限额: ${SL_SINGLE:.0f} ({SL_SINGLE/ACCOUNT*100:.0f}%)')
    print(f'  单日限额: ${SL_DAILY:.0f} ({SL_DAILY/ACCOUNT*100:.0f}%)')
    print(f'  总亏损限额: ${SL_TOTAL:.0f} ({SL_TOTAL/ACCOUNT*100:.0f}%)')
    print('=' * 80)

    r_a = check_portfolio('方案A: GBPUSD 50% + USDJPY 50%', 0.50, 0.50, 0.8)
    r_b = check_portfolio('方案B: GBPUSD 40% + USDJPY 60%', 0.40, 0.60, 0.8)

    print(f'\n{"=" * 80}')
    print('  汇总对比')
    print(f'{"=" * 80}')
    print(f'  {"检查项":20s}  {"方案A(50/50)":15s}  {"方案B(40/60)":15s}')
    print(f'  {"-" * 55}')
    labels = ['单笔亏损', '单日亏损', '总回撤']
    for i, label in enumerate(labels):
        sa = 'PASS' if r_a[i] else 'FAIL'
        sb = 'PASS' if r_b[i] else 'FAIL'
        print(f'  {label:20s}  {sa:15s}  {sb:15s}')

    # 收益对比
    print(f'\n  {"收益对比":20s}')
    print(f'  {"-" * 55}')
    ga, ua = r_a[3], r_a[4]
    gb, ub = r_b[3], r_b[4]
    pnl_a = ga['total_pnl'] + ua['total_pnl']
    pnl_b = gb['total_pnl'] + ub['total_pnl']
    print(f'  {"GBPUSD收益":20s}  ${ga["total_pnl"]:>+10.2f}     ${gb["total_pnl"]:>+10.2f}')
    print(f'  {"USDJPY收益":20s}  ${ua["total_pnl"]:>+10.2f}     ${ub["total_pnl"]:>+10.2f}')
    print(f'  {"组合总收益":20s}  ${pnl_a:>+10.2f}     ${pnl_b:>+10.2f}')
    print(f'  {"总交易数":20s}  {ga["n_trades"]+ua["n_trades"]:>10d}      {gb["n_trades"]+ub["n_trades"]:>10d}')
