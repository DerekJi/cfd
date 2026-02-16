"""
多品种数据下载脚本

从OANDA下载多个货币对/商品的历史数据
用于多品种回测测试
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置UTF-8编码
if sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from utils.data_fetcher import OANDADataFetcher
from oanda_config import OANDA_API_KEY, OANDA_ACCOUNT_ID, OANDA_ENVIRONMENT


# 要下载的品种列表
INSTRUMENTS = {
    'GBP_USD': {
        'description': 'GBP/USD - 英镑/美元',
        'pip_value': 0.0001
    },
    'EUR_USD': {
        'description': 'EUR/USD - 欧元/美元',
        'pip_value': 0.0001
    },
    'XAU_USD': {
        'description': 'XAU/USD - 黄金',
        'pip_value': 0.01
    },
    'XAG_USD': {
        'description': 'XAG/USD - 白银',
        'pip_value': 0.001
    },
    'USD_JPY': {
        'description': 'USD/JPY - 美元/日元',
        'pip_value': 0.01
    },
    'AUD_USD': {
        'description': 'AUD/USD - 澳元/美元',
        'pip_value': 0.0001
    },
}


def download_all_instruments(
    start_date='2025-02-02',
    end_date='2026-02-11',
    granularity='M5'
):
    """
    下载所有品种的历史数据
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        granularity: 时间周期 (M5=5分钟)
    """
    
    print("="*80)
    print("                   多品种数据下载工具")
    print("="*80)
    print()
    print(f"时间范围: {start_date} ~ {end_date}")
    print(f"时间周期: {granularity}")
    print(f"品种数量: {len(INSTRUMENTS)}")
    print()
    print("="*80)
    print()
    
    # 初始化下载器
    try:
        fetcher = OANDADataFetcher(
            api_key=OANDA_API_KEY,
            account_id=OANDA_ACCOUNT_ID,
            environment=OANDA_ENVIRONMENT
        )
        print("✓ OANDA连接成功")
        print()
    except Exception as e:
        print(f"❌ OANDA连接失败: {e}")
        print()
        print("请检查:")
        print("  1. oanda_config.py 中的API密钥是否正确")
        print("  2. 网络连接是否正常")
        print("  3. OANDA服务是否可用")
        print("  4. 是否已安装 oandapyV20: pip install oandapyV20")
        return
    
    # 下载每个品种
    success_count = 0
    failed_count = 0
    
    for instrument, config in INSTRUMENTS.items():
        print(f"\n{'='*80}")
        print(f"下载: {instrument} - {config['description']}")
        print(f"{'='*80}")
        
        output_file = f"./data/{instrument}_M5.csv"
        
        try:
            print(f"  正在下载...")
            df = fetcher.fetch_historical_data(
                instrument=instrument,
                start_date=start_date,
                end_date=end_date,
                granularity=granularity
            )
            
            # 保存数据
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            df.to_csv(output_file, index=True)
            
            print(f"  ✓ 下载成功: {len(df)} 根K线")
            print(f"  ✓ 保存位置: {output_file}")
            success_count += 1
            
        except Exception as e:
            print(f"  ❌ 下载失败: {e}")
            failed_count += 1
    
    print(f"\n\n{'='*80}")
    print("                        下载汇总")
    print("="*80)
    print()
    print(f"  成功: {success_count}/{len(INSTRUMENTS)}")
    print(f"  失败: {failed_count}/{len(INSTRUMENTS)}")
    print()
    
    if success_count > 0:
        print("✅ 数据下载完成！可以运行多品种测试:")
        print("   python multi_symbol_test.py")
    
    print()


def download_single_instrument(instrument, start_date, end_date, granularity='M5'):
    """
    下载单个品种数据
    
    Args:
        instrument: 品种代码 (如 'EUR_USD')
        start_date: 开始日期
        end_date: 结束日期
        granularity: 时间周期
    """
    print(f"下载 {instrument}...")
    
    fetcher = OANDADataFetcher(
        api_key=OANDA_API_KEY,
        account_id=OANDA_ACCOUNT_ID,
        environment=OANDA_ENVIRONMENT
    )
    
    df = fetcher.fetch_historical_data(
        instrument=instrument,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity
    )
    
    output_file = f"./data/{instrument}_{granularity}.csv"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    df.to_csv(output_file, index=True)
    
    print(f"✓ 保存到: {output_file}")
    print(f"✓ 数据量: {len(df)} 根K线")


if __name__ == '__main__':
    # 下载所有品种
    download_all_instruments(
        start_date='2025-02-02',
        end_date='2026-02-11',
        granularity='M5'
    )
