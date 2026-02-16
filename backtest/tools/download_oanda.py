"""
使用OANDA API下载数据的便捷脚本
"""

import sys
import os

# 修复Windows终端编码问题
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.data_fetcher import OANDADataFetcher
from config import DATA_CONFIG


def download_with_config():
    """使用配置文件下载数据"""
    
    print("="*80)
    print(" "*20 + "OANDA数据下载（使用配置文件）")
    print("="*80)
    
    # 尝试导入配置
    try:
        import oanda_config
        api_key = oanda_config.OANDA_API_KEY
        account_id = oanda_config.OANDA_ACCOUNT_ID
        environment = oanda_config.OANDA_ENVIRONMENT
        download_config = oanda_config.DOWNLOAD_CONFIG
        
        if api_key == "your-api-key-here":
            print("\n❌ 请先配置API密钥！")
            print("\n步骤:")
            print("  1. 复制 oanda_config_template.py 为 oanda_config.py")
            print("  2. 编辑 oanda_config.py，填入你的API密钥")
            print("  3. 重新运行此脚本")
            return False
        
    except ImportError:
        print("\n❌ 配置文件不存在！")
        print("\n步骤:")
        print("  1. 复制 oanda_config_template.py 为 oanda_config.py")
        print("     Windows: copy oanda_config_template.py oanda_config.py")
        print("     Linux/Mac: cp oanda_config_template.py oanda_config.py")
        print("  2. 编辑 oanda_config.py，填入你的API密钥")
        print("  3. 重新运行此脚本")
        return False
    
    print(f"\n配置信息:")
    print(f"  环境: {environment}")
    print(f"  品种: {download_config['instrument']}")
    print(f"  周期: {download_config['granularity']}")
    print(f"  时间范围: {download_config['start_date']} 至 {download_config['end_date']}")
    print(f"  API密钥: {'*' * 20}{api_key[-8:] if len(api_key) > 8 else '***'}")
    
    confirm = input("\n确认下载？(y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        return False
    
    try:
        # 初始化获取器
        print("\n连接OANDA API...")
        fetcher = OANDADataFetcher(api_key, account_id, environment)
        
        # 下载数据
        output_file = DATA_CONFIG['data_path']
        
        print("\n开始下载数据...")
        print("提示: 这可能需要几分钟时间，请耐心等待...")
        
        df = fetcher.fetch_historical_data(
            instrument=download_config['instrument'],
            granularity=download_config['granularity'],
            start_date=download_config['start_date'],
            end_date=download_config['end_date'],
            output_file=output_file
        )
        
        if not df.empty:
            print("\n" + "="*80)
            print("✅ 下载成功！")
            print("="*80)
            print(f"数据文件: {output_file}")
            print(f"时间范围: {df['datetime'].min()} 至 {df['datetime'].max()}")
            print(f"K线数量: {len(df):,}")
            print(f"数据大小: {os.path.getsize(output_file) / (1024*1024):.2f} MB")
            
            print("\n下一步:")
            print("  1. 验证数据: python test_data.py")
            print("  2. 运行回测: python run_backtest.py")
            print("="*80)
            return True
        else:
            print("\n⚠️ 未获取到数据")
            return False
            
    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        print("\n可能的原因:")
        print("  1. API密钥无效或已过期")
        print("  2. 账户ID错误（可以留空）")
        print("  3. 网络连接问题")
        print("  4. 日期范围超出限制")
        print("\n请检查配置并重试")
        return False


def download_interactive():
    """交互式下载（直接输入API密钥）"""
    
    print("="*80)
    print(" "*20 + "OANDA数据下载（交互式）")
    print("="*80)
    
    print("\n请输入配置信息:")
    api_key = input("API密钥: ").strip()
    
    if not api_key:
        print("❌ API密钥不能为空")
        return False
    
    account_id = input("账户ID（可选，按Enter跳过）: ").strip()
    environment = input("环境 [practice/live]（默认: practice）: ").strip() or 'practice'
    
    # 时间范围
    print(f"\n数据时间范围（默认: {DATA_CONFIG['start_date']} 至 {DATA_CONFIG['end_date']}）")
    start_date = input(f"起始日期（按Enter使用默认）: ").strip() or DATA_CONFIG['start_date']
    end_date = input(f"结束日期（按Enter使用默认）: ").strip() or DATA_CONFIG['end_date']
    
    try:
        # 初始化获取器
        print("\n连接OANDA API...")
        fetcher = OANDADataFetcher(api_key, account_id, environment)
        
        # 下载数据
        output_file = DATA_CONFIG['data_path']
        
        print("\n开始下载数据...")
        print("提示: 这可能需要几分钟时间，请耐心等待...")
        
        df = fetcher.fetch_historical_data(
            instrument='EUR_USD',
            granularity='M5',
            start_date=start_date,
            end_date=end_date,
            output_file=output_file
        )
        
        if not df.empty:
            print("\n" + "="*80)
            print("✅ 下载成功！")
            print("="*80)
            print(f"数据文件: {output_file}")
            print(f"时间范围: {df['datetime'].min()} 至 {df['datetime'].max()}")
            print(f"K线数量: {len(df):,}")
            
            print("\n下一步:")
            print("  1. 验证数据: python test_data.py")
            print("  2. 运行回测: python run_backtest.py")
            print("="*80)
            return True
        else:
            print("\n⚠️ 未获取到数据")
            return False
            
    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        return False


def main():
    """主函数"""
    print("\n选择下载方式:")
    print("  1. 使用配置文件（推荐，安全）")
    print("  2. 交互式输入（快速）")
    print("  3. 退出")
    
    choice = input("\n请选择 (1-3): ").strip()
    
    if choice == '1':
        success = download_with_config()
    elif choice == '2':
        success = download_interactive()
    elif choice == '3':
        print("退出")
        return
    else:
        print("❌ 无效选项")
        return
    
    if success:
        print("\n💡 提示: 可以保存配置文件以便下次使用")


if __name__ == '__main__':
    # 检查依赖
    try:
        import oandapyV20
    except ImportError:
        print("❌ 缺少依赖包！")
        print("\n请安装: pip install oandapyV20")
        sys.exit(1)
    
    main()
