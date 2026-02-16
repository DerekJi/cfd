"""
策略条件分析工具
分析为什么没有触发交易
"""

import sys
import os
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import DATA_CONFIG


def analyze_data_for_opportunities(csv_file='./data/EUR_USD_M5.csv'):
    """分析数据中的潜在交易机会"""
    
    print("="*80)
    print(" "*25 + "策略条件分析")
    print("="*80)
    
    # 读取数据
    try:
        df = pd.read_csv(csv_file)
        df['datetime'] = pd.to_datetime(df['datetime'])
    except Exception as e:
        print(f"\n❌ 无法读取数据: {e}")
        return
    
    print(f"\n数据概况:")
    print(f"  总K线数: {len(df)}")
    print(f"  时间范围: {df['datetime'].min()} 至 {df['datetime'].max()}")
    print(f"  价格范围: {df['close'].min():.5f} - {df['close'].max():.5f}")
    
    # 计算Donchian通道（20周期）
    lookback = 20
    df['up_line'] = df['high'].rolling(window=lookback).max()
    df['down_line'] = df['low'].rolling(window=lookback).min()
    df['mid_line'] = (df['up_line'] + df['down_line']) / 2
    
    # 计算ATR（14周期）
    atr_period = 14
    df['tr'] = df[['high', 'low', 'close']].apply(
        lambda x: max(x['high'] - x['low'], 
                      abs(x['high'] - x['close']), 
                      abs(x['low'] - x['close'])), axis=1
    )
    df['atr'] = df['tr'].rolling(window=atr_period).mean()
    df['buffer'] = df['atr'] * 0.2
    
    # 去掉前面的NaN
    df = df.dropna()
    
    print(f"\n有效数据: {len(df)} 根K线")
    
    # 分析1: 突破UP线的次数
    breakouts = 0
    sustained_breakouts = 0
    
    for i in range(1, len(df)):
        prev_close = df.iloc[i-1]['close']
        curr_close = df.iloc[i]['close']
        up_line = df.iloc[i-1]['up_line']
        
        # 突破UP线
        if prev_close <= up_line and curr_close > up_line:
            breakouts += 1
            
            # 检查是否持续1根以上
            if i+1 < len(df) and df.iloc[i+1]['close'] > up_line:
                sustained_breakouts += 1
    
    print(f"\n📊 突破统计:")
    print(f"  UP线突破次数: {breakouts}")
    print(f"  持续突破次数: {sustained_breakouts} (至少维持1根K线)")
    print(f"  持续率: {sustained_breakouts/breakouts*100 if breakouts > 0 else 0:.1f}%")
    
    # 分析2: 完整信号（突破+回调+再突破）
    complete_signals = 0
    
    for i in range(lookback+atr_period, len(df)-10):
        close = df.iloc[i]['close']
        up_line = df.iloc[i]['up_line']
        buffer = df.iloc[i]['buffer']
        
        # 检查是否突破UP线
        if close > up_line:
            # 检查后续6根K线内是否有回调+再突破
            for j in range(i+1, min(i+7, len(df))):
                retrace_close = df.iloc[j]['close']
                retrace_threshold = up_line - buffer
                
                # 回调到 UP - Buffer 以下
                if retrace_close <= retrace_threshold:
                    # 检查之后是否再次突破
                    for k in range(j+1, min(j+7, len(df))):
                        if df.iloc[k]['close'] > up_line:
                            complete_signals += 1
                            break
                    break
    
    print(f"\n🎯 完整信号统计:")
    print(f"  完整模式次数: {complete_signals} (突破→回调→再突破)")
    print(f"  平均每千根K线: {complete_signals/len(df)*1000:.1f} 次")
    
    # 分析3: 波动性统计
    avg_atr = df['atr'].mean()
    avg_buffer = df['buffer'].mean()
    avg_range = (df['up_line'] - df['down_line']).mean()
    
    print(f"\n📈 波动性指标:")
    print(f"  平均ATR: {avg_atr:.5f}")
    print(f"  平均Buffer: {avg_buffer:.5f}")
    print(f"  平均区间宽度: {avg_range:.5f}")
    print(f"  Buffer/区间比: {avg_buffer/avg_range*100:.1f}%")
    
    # 分析4: 价格与UP线的关系
    above_up = (df['close'] > df['up_line']).sum()
    below_down = (df['close'] < df['down_line']).sum()
    in_range = len(df) - above_up - below_down
    
    print(f"\n📍 价格分布:")
    print(f"  UP线上方: {above_up} ({above_up/len(df)*100:.1f}%)")
    print(f"  DOWN线下方: {below_down} ({below_down/len(df)*100:.1f}%)")
    print(f"  区间内: {in_range} ({in_range/len(df)*100:.1f}%)")
    
    print("\n" + "="*80)
    print("\n💡 建议:")
    if complete_signals < 5:
        print("  ⚠️ 数据中完整交易信号非常少！")
        print("  建议1: 下载更长时间的数据（如1年以上）")
        print("  建议2: 尝试波动性更大的货币对（如GBP/USD, USD/JPY）")
        print("  建议3: 考虑调整策略参数：")
        print("         - 减少confirm_bars（当前1根）")
        print("         - 增大buffer_multiplier（当前0.2）")
        print("         - 缩短lookback_period（当前20根）")
    else:
        print(f"  ✓ 数据中有 {complete_signals} 个潜在交易机会")
        print("  策略参数可能需要微调以捕获这些机会")
    
    print("="*80)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', default='./data/EUR_USD_M5.csv', 
                       help='CSV数据文件路径')
    args = parser.parse_args()
    
    analyze_data_for_opportunities(args.file)
