"""下载AUDUSD M5数据"""
import sys
import os
import codecs

# Set UTF-8 encoding for Windows console output
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from datetime import datetime, timedelta
from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles
import time

# OANDA配置
OANDA_TOKEN = "your_token_here"  # 需要从环境变量或配置文件读取
OANDA_ACCOUNT = "101-004-29061915-001"

def download_audusd_data():
    """下载AUDUSD M5数据（批量下载，避免超时）"""
    
    # 时间范围：1年数据
    end_date = datetime(2026, 2, 11, 23, 55)
    start_date = datetime(2025, 2, 2, 22, 0)
    
    print(f"下载AUDUSD数据: {start_date} → {end_date}")
    
    # 批量下载，每次7天
    batch_days = 7
    current_start = start_date
    all_data = []
    batch_count = 0
    
    api = API(access_token=OANDA_TOKEN)
    
    while current_start < end_date:
        current_end = min(current_start + timedelta(days=batch_days), end_date)
        
        batch_count += 1
        print(f"\n批次 {batch_count}: {current_start} → {current_end}")
        
        params = {
            "granularity": "M5",
            "from": current_start.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
            "to": current_end.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
        }
        
        try:
            req = InstrumentsCandles(instrument="AUD_USD", params=params)
            response = api.request(req)
            
            candles = response.get('candles', [])
            print(f"  获取 {len(candles)} 根K线")
            
            if candles:
                for candle in candles:
                    if candle['complete']:
                        all_data.append({
                            'time': candle['time'],
                            'open': float(candle['mid']['o']),
                            'high': float(candle['mid']['h']),
                            'low': float(candle['mid']['l']),
                            'close': float(candle['mid']['c']),
                            'volume': int(candle['volume'])
                        })
            
            # 延迟避免限流
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  ❌ 批次下载失败: {e}")
            # 继续下载下一批次
            
        current_start = current_end
    
    if not all_data:
        print("\n❌ 未获取到数据")
        return False
    
    # 转换为DataFrame
    df = pd.DataFrame(all_data)
    df['time'] = pd.to_datetime(df['time'])
    df = df.sort_values('time')
    
    # 去重
    df = df.drop_duplicates(subset=['time'], keep='first')
    
    # 保存
    output_path = './data/AUD_USD_M5.csv'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    
    print(f"\n✅ 数据已保存: {output_path}")
    print(f"   总K线数: {len(df)}")
    print(f"   时间范围: {df['time'].min()} → {df['time'].max()}")
    print(f"   价格范围: {df['close'].min():.5f} → {df['close'].max():.5f}")
    
    return True

if __name__ == '__main__':
    # 从环境变量读取token
    token = os.environ.get('OANDA_TOKEN')
    if token:
        OANDA_TOKEN = token
    else:
        print("⚠️ 未设置OANDA_TOKEN环境变量")
        print("使用方法: export OANDA_TOKEN='your_token'")
        sys.exit(1)
    
    success = download_audusd_data()
    sys.exit(0 if success else 1)
