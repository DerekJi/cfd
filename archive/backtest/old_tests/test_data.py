"""
快速测试真实数据脚本
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data_loader import CSVDataLoader
from config import DATA_CONFIG


def test_real_data():
    """测试真实数据文件"""
    data_path = DATA_CONFIG['data_path']
    
    print("="*80)
    print(" "*25 + "真实数据测试")
    print("="*80)
    
    print(f"\n检查文件: {data_path}")
    
    if not os.path.exists(data_path):
        print("\n❌ 数据文件不存在")
        print("\n请先下载数据:")
        print("  python download_data.py")
        print("\n或者查看指南:")
        print("  docs/数据获取指南.md")
        return False
    
    # 检查文件大小
    file_size = os.path.getsize(data_path) / (1024 * 1024)  # MB
    print(f"✓ 文件存在, 大小: {file_size:.2f} MB")
    
    # 加载数据
    print("\n加载数据...")
    try:
        loader = CSVDataLoader(data_path)
        df = loader.load_data()
        
        # 验证数据
        print("\n验证数据质量...")
        is_valid = loader.validate_data()
        
        # 统计信息
        print("\n" + "="*80)
        print("数据统计")
        print("="*80)
        print(f"时间范围: {df.index[0]} 至 {df.index[-1]}")
        print(f"K线数量: {len(df):,}")
        print(f"交易天数: {(df.index[-1] - df.index[0]).days} 天")
        print(f"\n价格统计:")
        print(f"  最高价: {df['high'].max():.5f}")
        print(f"  最低价: {df['low'].min():.5f}")
        print(f"  价格区间: {(df['high'].max() - df['low'].min()):.5f} ({(df['high'].max() - df['low'].min()) * 10000:.0f} pips)")
        print(f"\n成交量统计:")
        print(f"  总成交量: {df['volume'].sum():,.0f}")
        print(f"  平均成交量: {df['volume'].mean():,.0f}")
        
        # 数据密度分析
        total_minutes = (df.index[-1] - df.index[0]).total_seconds() / 60
        expected_bars = total_minutes / 5  # 5分钟K线
        coverage = (len(df) / expected_bars) * 100
        
        print(f"\n数据完整性:")
        print(f"  理论K线数: {expected_bars:,.0f}")
        print(f"  实际K线数: {len(df):,}")
        print(f"  覆盖率: {coverage:.1f}%")
        
        if coverage < 70:
            print("  ⚠️ 数据可能有较多缺失（外汇市场周末休市是正常的）")
        elif coverage < 90:
            print("  ✓ 数据完整性良好")
        else:
            print("  ✓ 数据非常完整")
        
        # 建议
        print("\n" + "="*80)
        print("回测建议")
        print("="*80)
        
        days = (df.index[-1] - df.index[0]).days
        if days < 30:
            print("⚠️ 数据时间范围较短（少于1个月）")
            print("   建议: 至少使用3个月以上的数据进行回测")
        elif days < 90:
            print("✓ 数据时间范围可用（1-3个月）")
            print("   建议: 如果可能，增加到6个月以上会更好")
        elif days < 180:
            print("✓ 数据时间范围良好（3-6个月）")
        else:
            print("✅ 数据时间范围优秀（6个月以上）")
        
        print("\n现在可以运行回测:")
        print("  python run_backtest.py")
        
        print("\n" + "="*80)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 数据加载失败: {e}")
        print("\n可能的原因:")
        print("  1. 文件格式不正确")
        print("  2. 缺少必要的列")
        print("  3. 日期格式无法解析")
        print("\n请检查数据格式，或使用转换工具:")
        print("  python convert_histdata.py")
        return False


if __name__ == '__main__':
    success = test_real_data()
    sys.exit(0 if success else 1)
