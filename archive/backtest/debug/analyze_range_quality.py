"""
分析震荡区间质量
验证当前的UP/DOWN线识别是否准确
"""

import pandas as pd
import numpy as np


def analyze_range_characteristics(csv_path, lookback=20):
    """
    分析数据中的震荡区间特征
    
    真正的震荡行情应该具有：
    1. 价格在UP/DOWN线之间来回波动
    2. 多次触碰上下边界
    3. 区间宽度相对稳定
    4. 波动率适中
    """
    df = pd.read_csv(csv_path)
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # 计算Donchian Channel
    df['up_line'] = df['high'].rolling(window=lookback).max().shift(1)
    df['down_line'] = df['low'].rolling(window=lookback).min().shift(1)
    df['mid_line'] = (df['up_line'] + df['down_line']) / 2
    df['range_width'] = df['up_line'] - df['down_line']
    df['range_width_pct'] = df['range_width'] / df['mid_line'] * 100
    
    # 检查震荡特征
    results = []
    
    for i in range(lookback * 2, len(df), lookback):
        window_data = df.iloc[i-lookback:i]
        
        # 特征1: 触碰次数
        touch_up = sum(window_data['high'] >= window_data['up_line'] * 0.999)
        touch_down = sum(window_data['low'] <= window_data['down_line'] * 1.001)
        
        # 特征2: 价格在区间内的比例
        in_range = sum(
            (window_data['low'] >= window_data['down_line']) & 
            (window_data['high'] <= window_data['up_line'])
        )
        in_range_pct = in_range / lookback * 100
        
        # 特征3: 区间宽度稳定性
        range_std = window_data['range_width'].std()
        range_mean = window_data['range_width'].mean()
        range_cv = (range_std / range_mean * 100) if range_mean > 0 else 999
        
        # 特征4: 突破后的表现
        if i < len(df) - 10:
            future_data = df.iloc[i:i+10]
            breakout_up = any(future_data['close'] > window_data['up_line'].iloc[-1])
            breakout_down = any(future_data['close'] < window_data['down_line'].iloc[-1])
            
            if breakout_up:
                # 检查是否是有效突破（价格持续在突破位上方）
                valid_breakout = sum(
                    future_data['close'] > window_data['up_line'].iloc[-1]
                ) >= 7  # 至少7/10的K线在上方
            else:
                valid_breakout = None
        else:
            breakout_up = False
            valid_breakout = None
        
        results.append({
            'bar': i,
            'time': window_data['datetime'].iloc[-1],
            'touch_up': touch_up,
            'touch_down': touch_down,
            'in_range_pct': in_range_pct,
            'range_width_pct': window_data['range_width_pct'].iloc[-1],
            'range_cv': range_cv,
            'breakout_up': breakout_up,
            'valid_breakout': valid_breakout
        })
    
    results_df = pd.DataFrame(results)
    
    # 统计分析
    print("="*80)
    print("震荡区间质量分析")
    print("="*80)
    print(f"\n总样本数: {len(results_df)}")
    
    print(f"\n【触碰特征】")
    print(f"  平均触碰UP线次数: {results_df['touch_up'].mean():.2f}")
    print(f"  平均触碰DOWN线次数: {results_df['touch_down'].mean():.2f}")
    
    print(f"\n【区间内比例】")
    print(f"  平均价格在区间内比例: {results_df['in_range_pct'].mean():.1f}%")
    print(f"  <30%（趋势行情）: {sum(results_df['in_range_pct'] < 30)} 样本")
    print(f"  30-70%（混合行情）: {sum((results_df['in_range_pct'] >= 30) & (results_df['in_range_pct'] < 70))} 样本")
    print(f"  >70%（震荡行情）: {sum(results_df['in_range_pct'] >= 70)} 样本")
    
    print(f"\n【区间宽度】")
    print(f"  平均区间宽度: {results_df['range_width_pct'].mean():.3f}%")
    print(f"  区间稳定性（CV）: {results_df['range_cv'].mean():.1f}%")
    
    print(f"\n【突破有效性】")
    valid_breakouts_df = results_df[results_df['valid_breakout'].notna()]
    if len(valid_breakouts_df) > 0:
        valid_rate = sum(valid_breakouts_df['valid_breakout']) / len(valid_breakouts_df) * 100
        print(f"  突破次数: {len(valid_breakouts_df)}")
        print(f"  有效突破率: {valid_rate:.1f}%")
        print(f"  假突破率: {100-valid_rate:.1f}%")
    
    # 定义"真正的震荡区间"标准
    print(f"\n{'='*80}")
    print("建议的震荡区间识别标准：")
    print("="*80)
    
    # 尝试不同的阈值组合
    thresholds = [
        {'name': '宽松', 'in_range': 40, 'touch_total': 2, 'range_cv': 50},
        {'name': '适中', 'in_range': 50, 'touch_total': 3, 'range_cv': 40},
        {'name': '严格', 'in_range': 60, 'touch_total': 4, 'range_cv': 30},
    ]
    
    for t in thresholds:
        results_df['touch_total'] = results_df['touch_up'] + results_df['touch_down']
        qualified = results_df[
            (results_df['in_range_pct'] >= t['in_range']) &
            (results_df['touch_total'] >= t['touch_total']) &
            (results_df['range_cv'] <= t['range_cv'])
        ]
        
        print(f"\n【{t['name']}标准】")
        print(f"  条件: 区间内≥{t['in_range']}%, 触碰≥{t['touch_total']}次, CV≤{t['range_cv']}%")
        print(f"  符合震荡特征: {len(qualified)}/{len(results_df)} ({len(qualified)/len(results_df)*100:.1f}%)")
        
        # 检查这些"真震荡"中的突破有效性
        qualified_with_breakout = qualified[qualified['valid_breakout'].notna()]
        if len(qualified_with_breakout) > 0:
            valid_in_qualified = sum(qualified_with_breakout['valid_breakout']) / len(qualified_with_breakout) * 100
            print(f"  有效突破率: {valid_in_qualified:.1f}%")
    
    return results_df


if __name__ == '__main__':
    csv_path = './data/GBP_USD_M5.csv'
    df = analyze_range_characteristics(csv_path, lookback=20)
    
    print("\n" + "="*80)
    print("💡 结论建议")
    print("="*80)
    print("""
如果发现：
1. 大部分样本的"区间内比例"<50% → 说明经常处于趋势状态，不适合震荡突破策略
2. 触碰次数很少 → 说明不是真正的震荡，只是碰巧价格在某个范围
3. 假突破率>60% → 需要添加震荡确认条件

建议改进：
✓ 添加震荡确认：只在真正的震荡区间（区间内比例>50%，触碰≥3次）交易
✓ 提高突破确认条件：不仅要突破，还要有明显的动能
✓ 过滤趋势市场：添加趋势过滤器（如ADX），避免在趋势中寻找震荡
    """)
