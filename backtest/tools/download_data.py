"""
数据下载脚本
快速下载EURUSD历史数据
"""

import sys
import os

# 添加路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data_fetcher import OANDADataFetcher, MT5DataFetcher
from config import DATA_CONFIG


def download_with_oanda():
    """使用OANDA API下载数据"""
    print("\n" + "="*80)
    print("使用OANDA API下载数据")
    print("="*80)
    
    # 获取API密钥
    api_key = input("\n请输入OANDA API密钥（从 https://www.oanda.com/account/tpa/personal_token 获取）: ").strip()
    if not api_key:
        print("⚠️ 未输入API密钥")
        return
    
    account_id = input("请输入账户ID（可选，按Enter跳过）: ").strip()
    environment = input("环境类型 [practice/live]（默认: practice）: ").strip() or 'practice'
    
    try:
        # 初始化获取器
        fetcher = OANDADataFetcher(api_key, account_id, environment)
        
        # 下载数据
        output_file = DATA_CONFIG['data_path']
        
        df = fetcher.fetch_historical_data(
            instrument='EUR_USD',
            granularity='M5',
            start_date=DATA_CONFIG['start_date'],
            end_date=DATA_CONFIG['end_date'],
            output_file=output_file
        )
        
        if not df.empty:
            print(f"\n✅ 成功！数据已保存到: {output_file}")
            print(f"   时间范围: {df['datetime'].min()} 至 {df['datetime'].max()}")
            print(f"   K线数量: {len(df)}")
            return True
        else:
            print("\n⚠️ 未获取到数据")
            return False
            
    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        return False


def download_with_mt5():
    """使用MetaTrader 5下载数据"""
    print("\n" + "="*80)
    print("使用MetaTrader 5下载数据")
    print("="*80)
    print("\n前提条件:")
    print("  1. 已安装MetaTrader 5终端")
    print("  2. 已登录MT5账户")
    print("  3. 已安装Python包: pip install MetaTrader5")
    
    confirm = input("\n是否满足以上条件？(y/n): ").strip().lower()
    if confirm != 'y':
        print("请先满足前提条件")
        return False
    
    try:
        # 初始化获取器
        fetcher = MT5DataFetcher()
        
        # 下载数据
        output_file = DATA_CONFIG['data_path']
        
        df = fetcher.fetch_historical_data(
            symbol='EURUSD',
            timeframe='M5',
            start_date=DATA_CONFIG['start_date'],
            end_date=DATA_CONFIG['end_date'],
            output_file=output_file
        )
        
        if not df.empty:
            print(f"\n✅ 成功！数据已保存到: {output_file}")
            print(f"   时间范围: {df['datetime'].min()} 至 {df['datetime'].max()}")
            print(f"   K线数量: {len(df)}")
            return True
        else:
            print("\n⚠️ 未获取到数据")
            return False
            
    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        print("\n提示: 如果是ImportError，请运行: pip install MetaTrader5")
        return False


def download_from_histdata():
    """从HistData.com下载（手动流程）"""
    print("\n" + "="*80)
    print("从HistData.com手动下载数据")
    print("="*80)
    
    print("\n📝 步骤:")
    print("  1. 访问: https://www.histdata.com/download-free-forex-data/")
    print("  2. 选择:")
    print("     - Currency Pair: EUR/USD")
    print("     - Time Frame: M1 (可下载后转换为M5)")
    print("     - Year/Month: 选择需要的时间范围")
    print("  3. 下载ZIP文件并解压")
    print("  4. 将CSV文件移动到:")
    print(f"     {os.path.abspath(DATA_CONFIG['data_path'])}")
    print("\n  5. 确保CSV格式为:")
    print("     datetime,open,high,low,close,volume")
    
    print("\n💡 提示:")
    print("  - HistData提供的是M1数据，下载后可以用pandas重采样为M5")
    print("  - 数据是免费的，但需要注册账户")
    print("  - 建议下载最近6-12个月的数据用于回测")


def show_manual_import_guide():
    """显示手动导入指南"""
    print("\n" + "="*80)
    print("手动导入CSV数据")
    print("="*80)
    
    print("\n📄 CSV文件格式要求:")
    print("```")
    print("datetime,open,high,low,close,volume")
    print("2024-01-01 00:00:00,1.10000,1.10050,1.09950,1.10020,1000")
    print("2024-01-01 00:05:00,1.10020,1.10080,1.10010,1.10060,1200")
    print("...")
    print("```")
    
    print(f"\n📁 文件位置:")
    print(f"   {os.path.abspath(DATA_CONFIG['data_path'])}")
    
    print("\n✅ 推荐数据源:")
    print("  1. **HistData.com** - 免费M1数据")
    print("     https://www.histdata.com/")
    
    print("\n  2. **Dukascopy** - 免费Tick数据")
    print("     https://www.dukascopy.com/swiss/english/marketwatch/historical/")
    
    print("\n  3. **TrueFX** - 免费Tick数据")
    print("     https://www.truefx.com/")
    
    print("\n  4. **AlphaVantage** - 免费API（有限制）")
    print("     https://www.alphavantage.co/")


def main():
    """主函数"""
    print("\n" + "="*80)
    print(" "*20 + "EURUSD 5分钟数据下载工具")
    print("="*80)
    
    print(f"\n目标配置:")
    print(f"  品种: {DATA_CONFIG['symbol']}")
    print(f"  周期: {DATA_CONFIG['timeframe']}")
    print(f"  时间范围: {DATA_CONFIG['start_date']} 至 {DATA_CONFIG['end_date']}")
    print(f"  保存路径: {DATA_CONFIG['data_path']}")
    
    print("\n请选择数据源:")
    print("  1. OANDA API（推荐，需API密钥）")
    print("  2. MetaTrader 5（需安装MT5）")
    print("  3. HistData.com（免费，手动下载）")
    print("  4. 手动导入CSV文件")
    print("  5. 退出")
    
    choice = input("\n请输入选项 (1-5): ").strip()
    
    if choice == '1':
        success = download_with_oanda()
    elif choice == '2':
        success = download_with_mt5()
    elif choice == '3':
        download_from_histdata()
        success = False
    elif choice == '4':
        show_manual_import_guide()
        success = False
    elif choice == '5':
        print("退出")
        return
    else:
        print("⚠️ 无效选项")
        return
    
    if success:
        print("\n" + "="*80)
        print("✅ 数据准备完成！现在可以运行回测了:")
        print("   python run_backtest.py")
        print("="*80)
    else:
        print("\n💡 如需帮助，请查看文档或联系支持")


if __name__ == '__main__':
    main()
