"""分析突破后的回调行为"""
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

def analyze_pullback_behavior(symbol, filepath):
    """分析突破后的回调行为"""
    
    print(f"\n{'='*70}")
    print(f"Analyzing pullback behavior for {symbol}")
    print(f"{'='*70}")
    
    # Load data
    df = pd.read_csv(filepath)
    df['datetime'] = pd.to_datetime(df['time']) if 'time' in df.columns else pd.to_datetime(df['datetime'])
    df = df.set_index('datetime')
    df = df.sort_index()
    
    # Calculate indicators
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['donchian_high'] = df['high'].rolling(20).max()
    df['donchian_low'] = df['low'].rolling(20).min()
    
    # Calculate ATR
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(14).mean()
    
    # Calculate ADX
    plus_dm = df['high'] - df['high'].shift(1)
    minus_dm = df['low'].shift(1) - df['low']
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[(plus_dm - minus_dm) < 0] = 0
    minus_dm[(minus_dm - plus_dm) < 0] = 0
    
    plus_di = 100 * (plus_dm.rolling(14).mean() / df['atr'])
    minus_di = 100 * (minus_dm.rolling(14).mean() / df['atr'])
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    df['adx'] = dx.rolling(14).mean()
    
    df = df.dropna()
    
    # Find breakouts when ADX > 35
    long_breakout = (df['close'] > df['donchian_high'].shift(1)) & (df['adx'] > 35) & (df['close'] > df['ema200'])
    short_breakout = (df['close'] < df['donchian_low'].shift(1)) & (df['adx'] > 35) & (df['close'] < df['ema200'])
    
    print(f"\nTotal bars: {len(df):,}")
    print(f"Long breakouts (ADX>35, price>EMA200): {long_breakout.sum():,}")
    print(f"Short breakouts (ADX>35, price<EMA200): {short_breakout.sum():,}")
    
    # Analyze pullback behavior after long breakouts
    pullback_stats = {
        'success_within_20': 0,
        'timeout_20': 0,
        'no_pullback': 0,
        'too_shallow': 0,
        'avg_pullback_bars': [],
        'avg_pullback_distance': []
    }
    
    long_breakout_indices = df[long_breakout].index
    
    for bo_idx in long_breakout_indices[:100]:  # Sample first 100 for speed
        try:
            bo_loc = df.index.get_loc(bo_idx)
        except KeyError:
            continue
            
        if bo_loc + 21 >= len(df):
            continue
        
        ema50_at_breakout = df.iloc[bo_loc]['ema50']
        atr_at_breakout = df.iloc[bo_loc]['atr']
        pullback_threshold = ema50_at_breakout + atr_at_breakout * 0.5
        
        # Check next 20 bars for pullback
        found_pullback = False
        for i in range(1, 21):
            if bo_loc + i >= len(df):
                break
            
            close_i = df.iloc[bo_loc + i]['close']
            ema50_i = df.iloc[bo_loc + i]['ema50']
            atr_i = df.iloc[bo_loc + i]['atr']
            current_threshold = ema50_i + atr_i * 0.5
            
            if close_i <= current_threshold:
                pullback_stats['success_within_20'] += 1
                pullback_stats['avg_pullback_bars'].append(i)                
                distance_to_ema = (close_i - ema50_i) / atr_i
                pullback_stats['avg_pullback_distance'].append(distance_to_ema)
                found_pullback = True
                break
        
        if not found_pullback:
            # Check if it ever came close
            window_closes = df.iloc[bo_loc+1:bo_loc+21]['close']
            window_ema50s = df.iloc[bo_loc+1:bo_loc+21]['ema50']
            window_atrs = df.iloc[bo_loc+1:bo_loc+21]['atr']
            
            min_distance = ((window_closes - window_ema50s) / window_atrs).min()
            
            if min_distance > 1.0:  # Never got closer than 1 ATR from EMA50
                pullback_stats['no_pullback'] += 1
            elif min_distance > 0.5:  # Got close but not close enough
                pullback_stats['too_shallow'] += 1
            else:
                pullback_stats['timeout_20'] += 1
    
    # Print statistics
    total_analyzed = len(long_breakout_indices[:100])
    print(f"\n{'='*70}")
    print(f"PULLBACK BEHAVIOR ANALYSIS (Sample: {total_analyzed} long breakouts)")
    print(f"{'='*70}")
    print(f"✅ Successful pullback within 20 bars: {pullback_stats['success_within_20']} ({100*pullback_stats['success_within_20']/total_analyzed:.1f}%)")
    print(f"❌ No pullback (stayed >1 ATR away):   {pullback_stats['no_pullback']} ({100*pullback_stats['no_pullback']/total_analyzed:.1f}%)")
    print(f"⚠️  Too shallow (0.5-1 ATR away):      {pullback_stats['too_shallow']} ({100*pullback_stats['too_shallow']/total_analyzed:.1f}%)")
    print(f"⏱️  Timeout (pulled back after >20):    {pullback_stats['timeout_20']} ({100*pullback_stats['timeout_20']/total_analyzed:.1f}%)")
    
    if pullback_stats['avg_pullback_bars']:
        avg_bars = np.mean(pullback_stats['avg_pullback_bars'])
        avg_dist = np.mean(pullback_stats['avg_pullback_distance'])
        print(f"\nAverage pullback timing: {avg_bars:.1f} bars")
        print(f"Average pullback distance from EMA50: {avg_dist:.2f} ATR")
    
    return pullback_stats

def main():
    symbols = [
        ('GBPUSD', './data/GBP_USD_M5.csv'),
        ('USDJPY', './data/USD_JPY_M5.csv'),
        ('AUDJPY', './data/AUD_JPY_M5.csv'),
    ]
    
    results = {}
    for symbol, filepath in symbols:
        stats = analyze_pullback_behavior(symbol, filepath)
        results[symbol] = stats
    
    # Comparison
    print(f"\n\n{'='*80}")
    print("PULLBACK SUCCESS RATE COMPARISON")
    print(f"{'='*80}")
    print(f"{'Symbol':<10} {'Success%':<12} {'No Pull%':<12} {'Too Shallow%':<15} {'Timeout%':<10}")
    print(f"{'-'*80}")
    
    for symbol, stats in results.items():
        total = sum([stats['success_within_20'], stats['no_pullback'], 
                     stats['too_shallow'], stats['timeout_20']])
        if total > 0:
            success_pct = 100 * stats['success_within_20'] / total
            no_pull_pct = 100 * stats['no_pullback'] / total
            shallow_pct = 100 * stats['too_shallow'] / total
            timeout_pct = 100 * stats['timeout_20'] / total
            
            print(f"{symbol:<10} {success_pct:>10.1f}%  {no_pull_pct:>10.1f}%  {shallow_pct:>13.1f}%  {timeout_pct:>8.1f}%")
    
    return 0

if __name__ == '__main__':
    exit(main())
