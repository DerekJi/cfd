"""Analyze why AUDJPY has no trades despite similar ADX distribution"""
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
from datetime import datetime, time, timedelta

def analyze_filters(symbol, filepath):
    """分析各个过滤器对交易机会的影响"""
    
    print(f"\n{'='*60}")
    print(f"Analyzing filters for {symbol}")
    print(f"{'='*60}")
    
    # Load data
    df = pd.read_csv(filepath)
    df['datetime'] = pd.to_datetime(df['time']) if 'time' in df.columns else pd.to_datetime(df['datetime'])
    df = df.set_index('datetime')
    df = df.sort_index()
    
    total_bars = len(df)
    print(f"\nTotal bars: {total_bars:,}")
    
    # Calculate indicators
    print("\nCalculating indicators...")
    
    # ADX (simplified - using ATR proxy for demonstration)
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['donchian_high'] = df['high'].rolling(20).max()
    df['donchian_low'] = df['low'].rolling(20).min()
    
    # Calculate ADX properly
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    
    plus_dm = df['high'] - df['high'].shift(1)
    minus_dm = df['low'].shift(1) - df['low']
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[(plus_dm - minus_dm) < 0] = 0
    minus_dm[(minus_dm - plus_dm) < 0] = 0
    
    atr = df['tr'].rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr)
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    df['adx'] = dx.rolling(14).mean()
    
    # Drop NaN rows
    df = df.dropna()
    valid_bars = len(df)
    print(f"Valid bars after indicators: {valid_bars:,}")
    
    # Filter 1: ADX > 35
    adx_filter = df['adx'] > 35
    adx_pass = adx_filter.sum()
    print(f"\n1️⃣ ADX > 35: {adx_pass:,} bars ({100*adx_pass/valid_bars:.1f}%)")
    
    # Filter 2: Donchian breakouts (when ADX > 35)
    df_adx = df[adx_filter].copy()
    long_breakout = df_adx['close'] > df_adx['donchian_high'].shift(1)
    short_breakout = df_adx['close'] < df_adx['donchian_low'].shift(1)
    breakout_filter = long_breakout | short_breakout
    breakout_pass = breakout_filter.sum()
    print(f"2️⃣ Donchian breakout (when ADX>35): {breakout_pass:,} bars ({100*breakout_pass/adx_pass:.1f}% of ADX>35)")
    
    # Filter 3: Price on correct side of EMA200
    df_breakout = df_adx[breakout_filter].copy()
    long_ema_ok = df_breakout[long_breakout.loc[breakout_filter]]['close'] > df_breakout[long_breakout.loc[breakout_filter]]['ema200']
    short_ema_ok = df_breakout[short_breakout.loc[breakout_filter]]['close'] < df_breakout[short_breakout.loc[breakout_filter]]['ema200']
    ema_pass = long_ema_ok.sum() + short_ema_ok.sum()
    print(f"3️⃣ Price on correct EMA200 side: {ema_pass:,} bars ({100*ema_pass/breakout_pass:.1f}% of breakouts)")
    
    # Filter 4: Time window filter (exclude Tokyo/Sydney ±15min)
    # Tokyo open: 09:00 JST = 00:00 UTC (considering DST variations)
    # Sydney open: 09:00 AEDT = 22:00 UTC (previous day)
    
    def is_tokyo_sydney_window(dt):
        """Check if datetime is within ±15min of Tokyo/Sydney open"""
        utc_time = dt.time()
        
        # Tokyo open window: 23:45-00:15 UTC
        tokyo_start = time(23, 45)
        tokyo_end = time(0, 15)
        
        # Sydney open window: 21:45-22:15 UTC  
        sydney_start = time(21, 45)
        sydney_end = time(22, 15)
        
        if tokyo_start <= utc_time or utc_time <= tokyo_end:
            return True
        if sydney_start <= utc_time <= sydney_end:
            return True
        return False
    
    time_filter_fail = pd.Series([is_tokyo_sydney_window(dt) for dt in df_breakout.index])
    time_pass = (~time_filter_fail).sum()
    print(f"4️⃣ Outside Tokyo/Sydney ±15min: {time_pass:,} bars ({100*time_pass/len(df_breakout):.1f}% of EMA-filtered)")
    
    # Summary
    print(f"\n{'='*60}")
    print("FILTER CASCADE SUMMARY")
    print(f"{'='*60}")
    print(f"Start:                    {valid_bars:,} bars")
    print(f"After ADX>35:             {adx_pass:,} bars ({100*adx_pass/valid_bars:.1f}%)")
    print(f"After Donchian breakout:  {breakout_pass:,} bars ({100*breakout_pass/valid_bars:.2f}%)")
    print(f"After EMA200 filter:      {ema_pass:,} bars ({100*ema_pass/valid_bars:.3f}%)")
    print(f"After time filter:        {time_pass:,} bars ({100*time_pass/valid_bars:.3f}%)")
    print(f"\nFinal opportunity rate: {100*time_pass/valid_bars:.4f}%")
    
    return {
        'symbol': symbol,
        'total_bars': valid_bars,
        'adx_pass': adx_pass,
        'adx_pct': 100*adx_pass/valid_bars,
        'breakout_pass': breakout_pass,
        'breakout_pct': 100*breakout_pass/valid_bars,
        'ema_pass': ema_pass,
        'ema_pct': 100*ema_pass/valid_bars,
        'time_pass': time_pass,
        'time_pct': 100*time_pass/valid_bars
    }

def main():
    symbols = [
        ('GBPUSD', './data/GBP_USD_M5.csv'),
        ('USDJPY', './data/USD_JPY_M5.csv'),
        ('AUDJPY', './data/AUD_JPY_M5.csv'),
    ]
    
    results = []
    for symbol, filepath in symbols:
        result = analyze_filters(symbol, filepath)
        results.append(result)
    
    # Comparison table
    print(f"\n\n{'='*80}")
    print("MULTI-SYMBOL COMPARISON")
    print(f"{'='*80}")
    print(f"{'Symbol':<10} {'ADX>35%':<10} {'Breakout%':<12} {'EMA200%':<12} {'TimeOK%':<12}")
    print(f"{'-'*80}")
    
    for r in results:
        print(f"{r['symbol']:<10} {r['adx_pct']:>8.1f}%  {r['breakout_pct']:>10.3f}%  {r['ema_pct']:>10.4f}%  {r['time_pct']:>10.4f}%")
    
    return 0

if __name__ == '__main__':
    exit(main())
