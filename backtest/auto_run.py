"""
自动化运行脚本：下载数据 + 回测
无需交互确认，直接执行
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
import pandas as pd


def download_data_auto():
    """自动下载数据（无交互）"""
    
    print("="*80)
    print(" "*25 + "自动化数据下载")
    print("="*80)
    
    # 导入配置
    try:
        import oanda_config
        api_key = oanda_config.OANDA_API_KEY
        account_id = oanda_config.OANDA_ACCOUNT_ID
        environment = oanda_config.OANDA_ENVIRONMENT
        download_config = oanda_config.DOWNLOAD_CONFIG
        
        if api_key == "your-api-key-here":
            print("\n❌ 请先配置API密钥！")
            return False
        
    except ImportError:
        print("\n❌ 配置文件不存在！")
        return False
    
    print(f"\n配置信息:")
    print(f"  环境: {environment}")
    print(f"  品种: {download_config['instrument']}")
    print(f"  周期: {download_config['granularity']}")
    print(f"  时间范围: {download_config['start_date']} 至 {download_config['end_date']}")
    print(f"  API密钥: {'*' * 20}{api_key[-10:]}")
    
    # 连接OANDA
    try:
        fetcher = OANDADataFetcher(
            api_key=api_key,
            account_id=account_id,
            environment=environment
        )
        print("\n✓ 连接OANDA API成功")
    except Exception as e:
        print(f"\n❌ 连接失败: {e}")
        return False
    
    # 下载数据
    print("\n开始下载数据...")
    print("提示: 这可能需要几分钟时间，请耐心等待...\n")
    
    # 确保数据目录存在
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    output_file = os.path.join(
        data_dir,
        f"{download_config['instrument']}_{download_config['granularity']}.csv"
    )
    
    try:
        df = fetcher.fetch_historical_data(
            instrument=download_config['instrument'],
            granularity=download_config['granularity'],
            start_date=download_config['start_date'],
            end_date=download_config['end_date'],
            output_file=output_file
        )
        
        if df is not None and not df.empty:
            print(f"\n✓ 数据下载完成！")
            print(f"  文件: {output_file}")
            print(f"  数据量: {len(df)} 根K线")
            print(f"  时间范围: {df['datetime'].min()} 至 {df['datetime'].max()}")
            return True
        else:
            print("\n❌ 未获取到数据")
            return False
            
    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        return False


def run_backtest_auto():
    """自动运行回测（无交互）"""
    
    print("\n" + "="*80)
    print(" "*25 + "运行回测系统")
    print("="*80 + "\n")
    
    try:
        # 导入回测模块
        from run_backtest import run_backtest
        
        # 运行回测（使用真实数据）
        run_backtest(use_sample_data=False)
        
        print("\n✓ 回测完成！")
        return True
        
    except Exception as e:
        print(f"\n❌ 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主流程"""
    
    print("\n" + "="*80)
    print(" "*20 + "自动化交易系统测试")
    print("="*80)
    print("\n步骤 1/2: 下载历史数据")
    print("步骤 2/2: 运行回测系统\n")
    
    # 检查依赖
    try:
        import oandapyV20
        import backtrader
    except ImportError as e:
        print(f"❌ 缺少依赖包: {e}")
        print("\n请安装:")
        print("  pip install oandapyV20 backtrader")
        return
    
    # Step 1: 下载数据
    download_success = download_data_auto()
    
    if not download_success:
        print("\n⚠️ 数据下载失败，无法继续回测")
        return
    
    # Step 2: 运行回测
    print("\n" + "-"*80)
    backtest_success = run_backtest_auto()
    
    # 总结
    print("\n" + "="*80)
    print(" "*30 + "完成")
    print("="*80)
    
    if download_success and backtest_success:
        print("\n✓ 所有步骤执行成功！")
        print("\n下一步:")
        print("  - 查看回测报告和图表")
        print("  - 分析交易记录")
        print("  - 调整策略参数")
    else:
        print("\n⚠️ 部分步骤执行失败，请检查错误信息")


if __name__ == '__main__':
    main()
