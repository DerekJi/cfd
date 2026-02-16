"""Analyze ADX distribution for multiple symbols"""
import sys
import os
import codecs

# Set UTF-8 encoding for Windows console output
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import backtrader as bt
from utils.data_loader import CSVDataLoader
from indicators.adx_indicator import ADX

class ADXAnalyzer(bt.Strategy):
    """ADX分析策略"""
    params = (
        ('adx_period', 14),
    )
    
    def __init__(self):
        self.adx = ADX(self.data, period=self.params.adx_period)
        self.adx_values = []
        
    def next(self):
        if len(self) > 200:  # 等待EMA200计算完成
            self.adx_values.append(self.adx[0])

def analyze_symbol(symbol, filepath):
    """分析单个品种的ADX分布"""
    print(f"\n{'='*60}")
    print(f"Analyzing {symbol}")
    print('='*60)
    
    # 加载数据
    cerebro = bt.Cerebro()
    loader = CSVDataLoader(filepath=filepath)
    loader.load_data()
    data_feed = loader.to_backtrader_feed()
    cerebro.adddata(data_feed)
    cerebro.addstrategy(ADXAnalyzer)
    
    # 运行
    results = cerebro.run()
    strat = results[0]
    
    # 分析ADX分布
    adx_values = np.array(strat.adx_values)
    print(f"\nTotal bars analyzed: {len(adx_values)}")
    print(f"\nADX Statistics:")
    print(f"  Min: {adx_values.min():.2f}")
    print(f"  Max: {adx_values.max():.2f}")
    print(f"  Mean: {adx_values.mean():.2f}")
    print(f"  Median: {np.median(adx_values):.2f}")
    
    # 关键阈值统计
    print(f"\nADX Threshold Analysis:")
    print(f"  ADX > 20: {(adx_values > 20).sum():6d} ({(adx_values > 20).mean()*100:5.1f}%)")
    print(f"  ADX > 25: {(adx_values > 25).sum():6d} ({(adx_values > 25).mean()*100:5.1f}%)")
    print(f"  ADX > 30: {(adx_values > 30).sum():6d} ({(adx_values > 30).mean()*100:5.1f}%)")
    print(f"  ADX > 35: {(adx_values > 35).sum():6d} ({(adx_values > 35).mean()*100:5.1f}%) ← Current threshold")
    print(f"  ADX > 40: {(adx_values > 40).sum():6d} ({(adx_values > 40).mean()*100:5.1f}%)")
    
    return {
        'symbol': symbol,
        'mean': adx_values.mean(),
        'median': np.median(adx_values),
        'pct_gt_25': (adx_values > 25).mean() * 100,
        'pct_gt_30': (adx_values > 30).mean() * 100,
        'pct_gt_35': (adx_values > 35).mean() * 100,
    }

def main():
    # 分析多个品种
    symbols = [
        ('GBPUSD', './data/GBP_USD_M5.csv'),
        ('USDJPY', './data/USD_JPY_M5.csv'),
        ('AUDJPY', './data/AUD_JPY_M5.csv'),
    ]
    
    results = []
    for symbol, filepath in symbols:
        if os.path.exists(filepath):
            result = analyze_symbol(symbol, filepath)
            results.append(result)
        else:
            print(f"\nSkipping {symbol} (file not found)")
    
    # 对比总结
    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print('='*60)
    print(f"{'Symbol':<10} {'ADX Mean':<10} {'ADX>25%':<10} {'ADX>30%':<10} {'ADX>35%':<10}")
    print('-'*60)
    for r in results:
        print(f"{r['symbol']:<10} {r['mean']:>8.2f}   {r['pct_gt_25']:>7.1f}%   {r['pct_gt_30']:>7.1f}%   {r['pct_gt_35']:>7.1f}%")
    
    return 0

if __name__ == '__main__':
    exit(main())
