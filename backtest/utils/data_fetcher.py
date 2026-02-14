"""
真实数据获取工具
支持多种数据源：OANDA API、MetaTrader 5、Yahoo Finance、CSV导入
"""

import pandas as pd
import os
from datetime import datetime, timedelta
import time


class OANDADataFetcher:
    """
    OANDA API数据获取器
    
    需要安装: pip install oandapyV20
    """
    
    def __init__(self, api_key, account_id, environment='practice'):
        """
        初始化OANDA数据获取器
        
        Args:
            api_key: OANDA API密钥
            account_id: OANDA账户ID
            environment: 'practice' 或 'live'
        """
        try:
            import oandapyV20
            from oandapyV20 import API
            import oandapyV20.endpoints.instruments as instruments
            
            self.api_key = api_key
            self.account_id = account_id
            self.environment = environment
            
            # 初始化API客户端
            self.client = API(access_token=api_key, environment=environment)
            self.instruments = instruments
            
        except ImportError:
            raise ImportError("请安装 oandapyV20: pip install oandapyV20")
    
    def fetch_candles(self, instrument='EUR_USD', granularity='M5', 
                     start_date=None, end_date=None, count=5000):
        """
        获取K线数据
        
        Args:
            instrument: 交易品种（如 'EUR_USD'）
            granularity: 时间周期（M5=5分钟）
            start_date: 起始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            count: 数据条数（最大5000，当使用from/to时会被忽略）
            
        Returns:
            pandas.DataFrame: K线数据
        """
        params = {
            "granularity": granularity
        }
        
        # 注意：OANDA API不允许同时使用count和from/to参数
        if start_date:
            params["from"] = start_date + "T00:00:00Z"
        if end_date:
            params["to"] = end_date + "T23:59:59Z"
        
        # 只有在未指定时间范围时才使用count
        if not start_date and not end_date:
            params["count"] = count
        
        # 发起请求
        request = self.instruments.InstrumentsCandles(
            instrument=instrument,
            params=params
        )
        
        response = self.client.request(request)
        
        # 解析数据
        candles = []
        for candle in response['candles']:
            if candle['complete']:
                candles.append({
                    'datetime': pd.to_datetime(candle['time']),
                    'open': float(candle['mid']['o']),
                    'high': float(candle['mid']['h']),
                    'low': float(candle['mid']['l']),
                    'close': float(candle['mid']['c']),
                    'volume': int(candle['volume'])
                })
        
        df = pd.DataFrame(candles)
        print(f"✓ 从OANDA获取 {len(df)} 根K线")
        return df
    
    def fetch_historical_data(self, instrument='EUR_USD', granularity='M5',
                             start_date='2024-01-01', end_date='2026-02-15',
                             output_file=None):
        """
        获取历史数据（支持大量数据，自动分批）
        
        Args:
            instrument: 交易品种
            granularity: 时间周期
            start_date: 起始日期
            end_date: 结束日期
            output_file: 输出文件路径
            
        Returns:
            pandas.DataFrame: 完整的历史数据
        """
        print(f"开始获取 {instrument} {granularity} 数据...")
        print(f"时间范围: {start_date} 至 {end_date}")
        
        all_data = []
        current_date = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        batch_count = 0
        while current_date < end_dt:
            # 每次获取约7天的数据（5分钟周期，每天约288根K线）
            next_date = current_date + timedelta(days=7)
            if next_date > end_dt:
                next_date = end_dt
            
            try:
                df = self.fetch_candles(
                    instrument=instrument,
                    granularity=granularity,
                    start_date=current_date.strftime('%Y-%m-%d'),
                    end_date=next_date.strftime('%Y-%m-%d')
                )
                
                if not df.empty:
                    all_data.append(df)
                    batch_count += 1
                    print(f"  批次 {batch_count}: {current_date.date()} 至 {next_date.date()}, {len(df)} 根K线")
                
                # API限流：暂停1秒
                time.sleep(1)
                
            except Exception as e:
                print(f"  ⚠️ 获取失败: {e}")
            
            current_date = next_date + timedelta(days=1)
        
        # 合并所有数据
        if all_data:
            full_df = pd.concat(all_data, ignore_index=True)
            full_df = full_df.drop_duplicates(subset=['datetime']).sort_values('datetime')
            
            print(f"\n✓ 总共获取 {len(full_df)} 根K线")
            
            # 保存到文件
            if output_file:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                full_df.to_csv(output_file, index=False)
                print(f"✓ 数据已保存: {output_file}")
            
            return full_df
        else:
            print("⚠️ 未获取到任何数据")
            return pd.DataFrame()


class MT5DataFetcher:
    """
    MetaTrader 5 数据获取器
    
    需要安装: pip install MetaTrader5
    需要在Windows上安装MT5终端
    """
    
    def __init__(self):
        """初始化MT5连接"""
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
            
            # 初始化MT5连接
            if not mt5.initialize():
                raise Exception("MT5初始化失败")
            
            print("✓ MT5连接成功")
            
        except ImportError:
            raise ImportError("请安装 MetaTrader5: pip install MetaTrader5")
    
    def fetch_historical_data(self, symbol='EURUSD', timeframe='M5',
                             start_date='2024-01-01', end_date='2026-02-15',
                             output_file=None):
        """
        从MT5获取历史数据
        
        Args:
            symbol: 交易品种
            timeframe: 时间周期（M5, M15, H1等）
            start_date: 起始日期
            end_date: 结束日期
            output_file: 输出文件路径
            
        Returns:
            pandas.DataFrame: 历史数据
        """
        # 时间周期映射
        timeframe_map = {
            'M1': self.mt5.TIMEFRAME_M1,
            'M5': self.mt5.TIMEFRAME_M5,
            'M15': self.mt5.TIMEFRAME_M15,
            'M30': self.mt5.TIMEFRAME_M30,
            'H1': self.mt5.TIMEFRAME_H1,
            'H4': self.mt5.TIMEFRAME_H4,
            'D1': self.mt5.TIMEFRAME_D1,
        }
        
        tf = timeframe_map.get(timeframe, self.mt5.TIMEFRAME_M5)
        
        # 转换日期
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        print(f"从MT5获取 {symbol} {timeframe} 数据...")
        
        # 获取数据
        rates = self.mt5.copy_rates_range(symbol, tf, start_dt, end_dt)
        
        if rates is None or len(rates) == 0:
            print(f"⚠️ 未获取到数据: {self.mt5.last_error()}")
            return pd.DataFrame()
        
        # 转换为DataFrame
        df = pd.DataFrame(rates)
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df = df[['datetime', 'open', 'high', 'low', 'close', 'tick_volume']]
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        
        print(f"✓ 获取 {len(df)} 根K线")
        
        # 保存到文件
        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            df.to_csv(output_file, index=False)
            print(f"✓ 数据已保存: {output_file}")
        
        return df
    
    def __del__(self):
        """关闭MT5连接"""
        if hasattr(self, 'mt5'):
            self.mt5.shutdown()


class YahooFinanceDataFetcher:
    """
    Yahoo Finance数据获取器（仅支持日线以上周期）
    
    需要安装: pip install yfinance
    """
    
    def __init__(self):
        """初始化Yahoo Finance"""
        try:
            import yfinance as yf
            self.yf = yf
        except ImportError:
            raise ImportError("请安装 yfinance: pip install yfinance")
    
    def fetch_historical_data(self, symbol='EURUSD=X', start_date='2024-01-01',
                             end_date='2026-02-15', interval='1d', output_file=None):
        """
        从Yahoo Finance获取历史数据
        
        注意：Yahoo Finance不提供外汇的分钟级数据
        
        Args:
            symbol: 交易品种（外汇格式：EURUSD=X）
            start_date: 起始日期
            end_date: 结束日期
            interval: 时间周期（1d, 1wk, 1mo）
            output_file: 输出文件路径
            
        Returns:
            pandas.DataFrame: 历史数据
        """
        print(f"从Yahoo Finance获取 {symbol} 数据...")
        print("⚠️ 注意：Yahoo Finance仅提供日线及以上周期数据")
        
        ticker = self.yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date, interval=interval)
        
        if df.empty:
            print("⚠️ 未获取到数据")
            return pd.DataFrame()
        
        # 重置索引并重命名列
        df = df.reset_index()
        df.columns = [col.lower() for col in df.columns]
        df.rename(columns={'date': 'datetime'}, inplace=True)
        df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
        
        print(f"✓ 获取 {len(df)} 根K线")
        
        # 保存到文件
        if output_file:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            df.to_csv(output_file, index=False)
            print(f"✓ 数据已保存: {output_file}")
        
        return df


def download_sample_data_from_github():
    """
    从GitHub下载示例数据（备用方案）
    """
    print("从GitHub下载示例数据...")
    print("⚠️ 此功能需要网络连接")
    
    # 这里可以添加从公开数据源下载的逻辑
    # 例如：https://www.histdata.com/ 提供免费的外汇历史数据
    
    print("提示：您可以手动从以下网站下载数据：")
    print("  1. HistData.com - https://www.histdata.com/download-free-forex-data/")
    print("  2. Dukascopy - https://www.dukascopy.com/swiss/english/marketwatch/historical/")
    print("  3. TrueFX - https://www.truefx.com/")


if __name__ == '__main__':
    print("="*80)
    print(" "*25 + "数据获取工具")
    print("="*80)
    print("\n可用的数据源:")
    print("  1. OANDA API - 需要API密钥（支持5分钟数据）")
    print("  2. MetaTrader 5 - 需要安装MT5终端（支持所有周期）")
    print("  3. Yahoo Finance - 免费（仅支持日线数据）")
    print("  4. 手动下载 - 从HistData.com等网站下载")
    print("\n" + "="*80)
