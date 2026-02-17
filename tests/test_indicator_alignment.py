"""
指标对齐测试 — core/indicators vs Backtrader 内置指标

用真实 CSV 数据同时跑两套实现，逐K线对比，要求误差 < 1e-8。

测试范围:
  - EMA(50), EMA(200)
  - ATR(14)
  - ADX(14), +DI(14), -DI(14)
  - Donchian(20): up_line, down_line

使用方法:
    cd d:\\source\\cfd
    python tests/test_indicator_alignment.py
"""

import sys
import os
import math

# 确保可以 import core
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd
import backtrader as bt
from core import indicators


# ============================================================
# Backtrader 指标提取器策略
# ============================================================

class IndicatorExtractor(bt.Strategy):
    """
    Backtrader 策略，仅用于提取指标值，不做交易
    """
    params = (
        ('ema50_period', 50),
        ('ema200_period', 200),
        ('adx_period', 14),
        ('atr_period', 14),
        ('donchian_period', 20),
    )

    def __init__(self):
        self.ema50 = bt.indicators.EMA(self.data.close, period=self.params.ema50_period)
        self.ema200 = bt.indicators.EMA(self.data.close, period=self.params.ema200_period)
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        self.dmi = bt.indicators.DirectionalMovementIndex(self.data, period=self.params.adx_period)

        # Donchian: 与 range_detector.py 一致，使用 high(-1) / low(-1)
        # 即不含当前K线
        self.donchian_up = bt.indicators.Highest(
            self.data.high(-1), period=self.params.donchian_period
        )
        self.donchian_down = bt.indicators.Lowest(
            self.data.low(-1), period=self.params.donchian_period
        )

        # 存储结果
        self.results = {
            'ema50': [],
            'ema200': [],
            'atr': [],
            'adx': [],
            'plus_di': [],
            'minus_di': [],
            'donchian_up': [],
            'donchian_down': [],
        }

    def next(self):
        self.results['ema50'].append(self.ema50[0])
        self.results['ema200'].append(self.ema200[0])
        self.results['atr'].append(self.atr[0])
        self.results['adx'].append(self.dmi.adx[0])
        self.results['plus_di'].append(self.dmi.plusDI[0])
        self.results['minus_di'].append(self.dmi.minusDI[0])
        self.results['donchian_up'].append(self.donchian_up[0])
        self.results['donchian_down'].append(self.donchian_down[0])


def run_backtrader(csv_path: str) -> dict:
    """用 Backtrader 运行指标提取"""
    cerebro = bt.Cerebro()

    # 读取 CSV
    df = pd.read_csv(csv_path)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df.set_index('datetime', inplace=True)
    df = df[['open', 'high', 'low', 'close', 'volume']]

    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.addstrategy(IndicatorExtractor)

    result = cerebro.run()
    strat = result[0]

    return strat.results


def run_core_indicators(csv_path: str) -> dict:
    """用 core.indicators 运行指标计算"""
    df = pd.read_csv(csv_path)

    h = df['high'].values.astype(float)
    l = df['low'].values.astype(float)
    c = df['close'].values.astype(float)

    ema50 = indicators.ema(c, 50)
    ema200 = indicators.ema(c, 200)
    atr_vals = indicators.atr(h, l, c, 14)
    adx_vals, plus_di, minus_di = indicators.adx(h, l, c, 14)
    up_line, down_line = indicators.donchian(h, l, 20)

    return {
        'ema50': ema50,
        'ema200': ema200,
        'atr': atr_vals,
        'adx': adx_vals,
        'plus_di': plus_di,
        'minus_di': minus_di,
        'donchian_up': up_line,
        'donchian_down': down_line,
    }


def compare_results(bt_results: dict, core_results: dict, csv_path: str):
    """对比结果，要求误差 < 1e-8"""
    # Backtrader 因为 minimum period 会跳过前面的 bar，所以 bt_results 列表更短
    # 我们需要找到对齐的起始位置

    n_bt = len(bt_results['ema50'])
    n_core = len(core_results['ema50'])

    # Backtrader 从第 max(period) 根 bar 之后才开始输出
    # EMA200 最慢: 需要 200 根 bar seed
    # Donchian: 需要 period+1 根
    # ADX: 需要 ~3*period 根
    # 实际 offset = n_core - n_bt (Backtrader 跳过的前缀长度)

    offset = n_core - n_bt
    if offset < 0:
        print(f"ERROR: core has fewer bars ({n_core}) than backtrader ({n_bt})")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"数据文件: {csv_path}")
    print(f"总K线数: {n_core}, Backtrader输出: {n_bt}, 偏移: {offset}")
    print(f"{'='*70}")

    all_pass = True
    tolerance = 1e-8

    for key in bt_results:
        bt_arr = bt_results[key]
        core_arr = core_results[key]

        # 对齐: core[offset:] 应该与 bt[:] 一一对应
        mismatches = 0
        max_err = 0.0
        first_mismatch = None

        for i in range(n_bt):
            bt_val = bt_arr[i]
            core_val = core_arr[offset + i]

            if np.isnan(bt_val) and np.isnan(core_val):
                continue
            if np.isnan(bt_val) or np.isnan(core_val):
                mismatches += 1
                if first_mismatch is None:
                    first_mismatch = (i, bt_val, core_val)
                continue

            err = abs(bt_val - core_val)
            max_err = max(max_err, err)

            if err > tolerance:
                mismatches += 1
                if first_mismatch is None:
                    first_mismatch = (i, bt_val, core_val)

        status = "✓ PASS" if mismatches == 0 else "✗ FAIL"
        print(f"  {status}  {key:15s}  max_err={max_err:.2e}  mismatches={mismatches}/{n_bt}")

        if mismatches > 0:
            all_pass = False
            idx, bv, cv = first_mismatch
            print(f"         首个不匹配: bar[{idx}] bt={bv} core={cv} err={abs(bv-cv):.2e}")

    return all_pass


# ============================================================
# 主程序
# ============================================================

def main():
    csv_files = [
        'backtest/data/GBP_USD_M5.csv',
        'backtest/data/USD_JPY_M5.csv',
    ]

    all_pass = True

    for csv_path in csv_files:
        full_path = os.path.join(os.path.dirname(__file__), '..', csv_path)
        if not os.path.exists(full_path):
            print(f"SKIP: {csv_path} not found")
            continue

        print(f"\n正在运行 Backtrader...")
        bt_results = run_backtrader(full_path)

        print(f"正在运行 core.indicators...")
        core_results = run_core_indicators(full_path)

        if not compare_results(bt_results, core_results, csv_path):
            all_pass = False

    print(f"\n{'='*70}")
    if all_pass:
        print("🎉 全部通过！core.indicators 与 Backtrader 完全对齐。")
    else:
        print("❌ 存在不匹配，需要检查算法。")
    print(f"{'='*70}")

    sys.exit(0 if all_pass else 1)


if __name__ == '__main__':
    main()
