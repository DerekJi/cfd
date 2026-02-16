"""
HistData CSV格式转换工具
将HistData.com下载的M1数据转换为M5，并转换为标准格式
"""

import pandas as pd
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_CONFIG


def convert_histdata_m1_to_m5(input_file, output_file=None):
    """
    将HistData的M1数据转换为M5
    
    Args:
        input_file: HistData下载的CSV文件路径
        output_file: 输出文件路径（可选）
    """
    print(f"正在读取文件: {input_file}")
    
    # HistData的CSV格式通常是：
    # 20240101 000000;1.10000;1.10001;1.09999;1.10000;10
    # 或者
    # 2024-01-01 00:00:00,1.10000,1.10001,1.09999,1.10000,10
    
    try:
        # 尝试第一种格式（分号分隔，日期时间分开）
        df = pd.read_csv(input_file, sep=';', header=None)
        
        if len(df.columns) == 6:
            # 格式：日期 时间;开;高;低;收;量
            df.columns = ['datetime', 'time', 'open', 'high', 'low', 'close', 'volume']
            # 合并日期时间
            df['datetime'] = pd.to_datetime(
                df['datetime'].astype(str) + ' ' + df['time'].astype(str),
                format='%Y%m%d %H%M%S'
            )
            df = df.drop('time', axis=1)
        else:
            raise ValueError("格式不匹配，尝试其他格式")
            
    except Exception as e:
        print(f"第一种格式失败: {e}")
        print("尝试第二种格式...")
        
        try:
            # 尝试第二种格式（逗号分隔）
            df = pd.read_csv(
                input_file,
                names=['datetime', 'open', 'high', 'low', 'close', 'volume'],
                parse_dates=['datetime']
            )
        except Exception as e2:
            print(f"❌ 文件格式无法识别: {e2}")
            print("\n请确保文件格式为以下之一:")
            print("  1. 20240101 000000;1.10000;1.10001;1.09999;1.10000;10")
            print("  2. 2024-01-01 00:00:00,1.10000,1.10001,1.09999,1.10000,10")
            return None
    
    print(f"✓ 成功读取 {len(df)} 根M1 K线")
    print(f"  时间范围: {df['datetime'].min()} 至 {df['datetime'].max()}")
    
    # 转换为M5
    print("\n正在重采样为M5...")
    df.set_index('datetime', inplace=True)
    
    df_m5 = df.resample('5T').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    
    print(f"✓ 重采样完成: {len(df_m5)} 根M5 K线")
    
    # 保存
    if output_file is None:
        output_file = DATA_CONFIG['data_path']
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    df_m5.reset_index().to_csv(output_file, index=False)
    
    print(f"\n✅ 转换成功！")
    print(f"   输出文件: {os.path.abspath(output_file)}")
    print(f"   K线数量: {len(df_m5)}")
    print(f"   时间范围: {df_m5.index[0]} 至 {df_m5.index[-1]}")
    
    return df_m5


def merge_multiple_files(input_files, output_file=None):
    """
    合并多个HistData文件（例如不同月份的数据）
    
    Args:
        input_files: 输入文件列表
        output_file: 输出文件路径
    """
    print(f"准备合并 {len(input_files)} 个文件...")
    
    all_data = []
    
    for i, file in enumerate(input_files, 1):
        print(f"\n[{i}/{len(input_files)}] 处理文件: {file}")
        df = convert_histdata_m1_to_m5(file, output_file=None)
        if df is not None:
            all_data.append(df)
    
    if not all_data:
        print("\n❌ 没有可用的数据")
        return None
    
    # 合并所有数据
    print("\n合并数据...")
    merged_df = pd.concat(all_data).sort_index()
    
    # 去重（可能有重叠的数据）
    merged_df = merged_df[~merged_df.index.duplicated(keep='first')]
    
    print(f"✓ 合并完成: {len(merged_df)} 根K线")
    
    # 保存
    if output_file is None:
        output_file = DATA_CONFIG['data_path']
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    merged_df.reset_index().to_csv(output_file, index=False)
    
    print(f"\n✅ 所有数据已合并保存！")
    print(f"   输出文件: {os.path.abspath(output_file)}")
    print(f"   总K线数: {len(merged_df)}")
    print(f"   时间范围: {merged_df.index[0]} 至 {merged_df.index[-1]}")
    
    return merged_df


def main():
    """主函数"""
    print("="*80)
    print(" "*20 + "HistData格式转换工具")
    print("="*80)
    
    print("\n此工具可以:")
    print("  1. 将HistData的M1数据转换为M5")
    print("  2. 合并多个月份的数据文件")
    print("  3. 转换为系统支持的标准格式")
    
    print("\n请选择操作:")
    print("  1. 转换单个文件")
    print("  2. 合并多个文件")
    print("  3. 退出")
    
    choice = input("\n请输入选项 (1-3): ").strip()
    
    if choice == '1':
        input_file = input("\n请输入HistData CSV文件路径: ").strip()
        
        if not os.path.exists(input_file):
            print(f"❌ 文件不存在: {input_file}")
            return
        
        output_file = input(f"\n输出文件路径 (默认: {DATA_CONFIG['data_path']}): ").strip()
        if not output_file:
            output_file = None
        
        convert_histdata_m1_to_m5(input_file, output_file)
        
    elif choice == '2':
        print("\n请输入要合并的文件路径（每行一个，输入空行结束）:")
        input_files = []
        while True:
            file_path = input("文件路径: ").strip()
            if not file_path:
                break
            if os.path.exists(file_path):
                input_files.append(file_path)
            else:
                print(f"  ⚠️ 文件不存在: {file_path}")
        
        if not input_files:
            print("❌ 没有有效的文件")
            return
        
        output_file = input(f"\n输出文件路径 (默认: {DATA_CONFIG['data_path']}): ").strip()
        if not output_file:
            output_file = None
        
        merge_multiple_files(input_files, output_file)
        
    elif choice == '3':
        print("退出")
        return
    else:
        print("❌ 无效选项")
        return
    
    print("\n" + "="*80)
    print("✅ 完成！现在可以运行回测了:")
    print("   python run_backtest.py")
    print("="*80)


if __name__ == '__main__':
    main()
