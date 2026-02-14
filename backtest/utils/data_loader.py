"""
数据加载模块
Data loading utilities for backtest system
"""

import pandas as pd
import backtrader as bt
from datetime import datetime
import os


class CSVDataLoader:
    """CSV数据加载器"""
    
    def __init__(self, filepath, symbol='EURUSD'):
        """
        初始化数据加载器
        
        Args:
            filepath: CSV文件路径
            symbol: 交易品种
        """
        self.filepath = filepath
        self.symbol = symbol
        self.data = None
    
    def load_data(self, start_date=None, end_date=None):
        """
        加载CSV数据
        
        Args:
            start_date: 起始日期 (格式: 'YYYY-MM-DD')
            end_date: 结束日期 (格式: 'YYYY-MM-DD')
            
        Returns:
            pandas.DataFrame: 加载的数据
        """
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"数据文件不存在: {self.filepath}")
        
        # 读取CSV文件
        # 期望格式: datetime,open,high,low,close,volume
        df = pd.read_csv(self.filepath, parse_dates=['datetime'], index_col='datetime')
        
        # 确保列名小写
        df.columns = [col.lower() for col in df.columns]
        
        # 日期过滤
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]
        
        self.data = df
        print(f"✓ 数据加载成功: {len(df)} 根K线")
        print(f"  时间范围: {df.index[0]} 至 {df.index[-1]}")
        print(f"  数据列: {list(df.columns)}")
        
        return df
    
    def to_backtrader_feed(self):
        """
        转换为Backtrader数据源
        
        Returns:
            bt.feeds.PandasData: Backtrader数据源
        """
        if self.data is None:
            raise ValueError("请先调用 load_data() 加载数据")
        
        data_feed = bt.feeds.PandasData(
            dataname=self.data,
            datetime=None,  # 使用索引作为日期
            open='open',
            high='high',
            low='low',
            close='close',
            volume='volume',
            openinterest=-1  # 不使用未平仓量
        )
        
        return data_feed
    
    def validate_data(self):
        """验证数据完整性"""
        if self.data is None:
            raise ValueError("请先加载数据")
        
        issues = []
        
        # 检查缺失值
        if self.data.isnull().any().any():
            issues.append("数据包含缺失值")
        
        # 检查价格逻辑
        invalid_hl = (self.data['high'] < self.data['low']).sum()
        if invalid_hl > 0:
            issues.append(f"{invalid_hl} 根K线的最高价低于最低价")
        
        invalid_oc = ((self.data['open'] > self.data['high']) | 
                      (self.data['open'] < self.data['low'])).sum()
        if invalid_oc > 0:
            issues.append(f"{invalid_oc} 根K线的开盘价超出高低价范围")
        
        if issues:
            print("⚠️ 数据验证发现问题:")
            for issue in issues:
                print(f"  - {issue}")
            return False
        else:
            print("✓ 数据验证通过")
            return True


class OANDADataLoader:
    """OANDA数据加载器（用于实时数据或API数据）"""
    
    def __init__(self, api_key, account_id, environment='practice'):
        """
        初始化OANDA数据加载器
        
        Args:
            api_key: OANDA API密钥
            account_id: OANDA账户ID
            environment: 'practice' 或 'live'
        """
        self.api_key = api_key
        self.account_id = account_id
        self.environment = environment
        # TODO: 实现OANDA API数据获取
        raise NotImplementedError("OANDA数据加载器待实现")


def create_sample_data(filepath, num_bars=1000):
    """
    创建示例数据用于测试
    
    Args:
        filepath: 保存路径
        num_bars: K线数量
    """
    import numpy as np
    
    # 生成模拟的EURUSD 5分钟数据
    dates = pd.date_range(start='2024-01-01', periods=num_bars, freq='5min')
    
    # 生成震荡突破模式的价格数据
    np.random.seed(42)
    base_price = 1.1000
    
    # 创建多个震荡区间和突破
    prices = []
    current_price = base_price
    
    for i in range(num_bars):
        # 每200根K线切换一次模式
        phase = (i // 200) % 3
        
        if phase == 0:  # 震荡阶段
            # 在区间内震荡
            range_center = current_price
            range_width = 0.0030  # 30 pips 区间
            noise = np.random.randn() * 0.0001
            current_price = range_center + np.sin(i * 0.1) * range_width/2 + noise
            
        elif phase == 1:  # 上涨突破
            # 逐步突破区间
            current_price += 0.00005 + np.random.randn() * 0.00002
            
        else:  # 回落阶段
            # 小幅回落
            current_price -= 0.00003 + np.random.randn() * 0.00002
        
        prices.append(current_price)
    
    prices = np.array(prices)
    
    # 生成OHLC
    data = pd.DataFrame({
        'datetime': dates,
        'open': prices + np.random.randn(num_bars) * 0.00002,
        'high': prices + np.abs(np.random.randn(num_bars) * 0.00005),
        'low': prices - np.abs(np.random.randn(num_bars) * 0.00005),
        'close': prices,
        'volume': np.random.randint(100, 1000, num_bars)
    })
    
    # 确保价格逻辑正确
    data['high'] = data[['open', 'high', 'close']].max(axis=1)
    data['low'] = data[['open', 'low', 'close']].min(axis=1)
    
    # 保存
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    data.to_csv(filepath, index=False)
    print(f"✓ 示例数据已创建: {filepath}")
    print(f"  K线数量: {num_bars}")
    print(f"  时间范围: {dates[0]} 至 {dates[-1]}")


if __name__ == '__main__':
    # 测试数据加载器
    test_file = './backtest/data/EURUSD_5m_test.csv'
    
    # 创建示例数据
    create_sample_data(test_file, num_bars=1000)
    
    # 加载数据
    loader = CSVDataLoader(test_file)
    df = loader.load_data()
    loader.validate_data()
    
    print("\n数据预览:")
    print(df.head())
