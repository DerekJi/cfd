"""
UP/DOWN线自动识别模块
Range detection using Donchian Channel or Support/Resistance clustering
"""

import backtrader as bt
import numpy as np


class DonchianRangeDetector(bt.Indicator):
    """
    基于Donchian通道的UP/DOWN线识别
    
    Donchian Channel = N周期的最高价和最低价
    适合震荡行情的支撑压力位识别
    """
    
    lines = ('up_line', 'down_line', 'mid_line')
    params = (
        ('lookback', 20),  # 回看周期（20根K线 = 100分钟）
        ('update_freq', 5),  # 更新频率（每5根K线更新一次）
    )
    
    def __init__(self):
        # Donchian通道（使用过去N根K线，不包括当前K线）
        self.highest = bt.indicators.Highest(self.data.high(-1), period=self.params.lookback)
        self.lowest = bt.indicators.Lowest(self.data.low(-1), period=self.params.lookback)
        
        # UP/DOWN线
        self.lines.up_line = self.highest
        self.lines.down_line = self.lowest
        self.lines.mid_line = (self.lines.up_line + self.lines.down_line) / 2
        
        # 更新计数器
        self.update_counter = 0
    
    def next(self):
        """每根K线调用一次"""
        self.update_counter += 1
        
        # 每N根K线更新一次（可选优化）
        if self.update_counter % self.params.update_freq == 0:
            # 可以在这里添加额外的过滤逻辑
            pass


class SupportResistanceDetector:
    """
    基于局部高低点聚类的支撑压力位识别
    
    更接近人工画线逻辑，但计算复杂度较高
    """
    
    def __init__(self, data, lookback=100, cluster_tolerance=0.0005):
        """
        初始化支撑压力位检测器
        
        Args:
            data: 价格数据（DataFrame）
            lookback: 回看周期
            cluster_tolerance: 聚类容差（价格差异百分比）
        """
        self.data = data
        self.lookback = lookback
        self.cluster_tolerance = cluster_tolerance
    
    def find_local_extrema(self, window=5):
        """
        识别局部高点和低点
        
        Args:
            window: 窗口大小（两侧K线数量）
            
        Returns:
            highs: 局部高点列表 [(index, price), ...]
            lows: 局部低点列表 [(index, price), ...]
        """
        highs = []
        lows = []
        
        for i in range(window, len(self.data) - window):
            # 检查是否为局部高点
            left_high = all(self.data['high'].iloc[i] >= self.data['high'].iloc[i-j] 
                           for j in range(1, window+1))
            right_high = all(self.data['high'].iloc[i] >= self.data['high'].iloc[i+j] 
                            for j in range(1, window+1))
            if left_high and right_high:
                highs.append((self.data.index[i], self.data['high'].iloc[i]))
            
            # 检查是否为局部低点
            left_low = all(self.data['low'].iloc[i] <= self.data['low'].iloc[i-j] 
                          for j in range(1, window+1))
            right_low = all(self.data['low'].iloc[i] <= self.data['low'].iloc[i+j] 
                           for j in range(1, window+1))
            if left_low and right_low:
                lows.append((self.data.index[i], self.data['low'].iloc[i]))
        
        return highs, lows
    
    def cluster_levels(self, levels):
        """
        对价格水平进行聚类
        
        Args:
            levels: 价格列表
            
        Returns:
            clusters: 聚类中心列表
        """
        if not levels:
            return []
        
        prices = [price for _, price in levels]
        prices.sort()
        
        clusters = []
        current_cluster = [prices[0]]
        
        for price in prices[1:]:
            # 如果价格在容差范围内，加入当前聚类
            if abs(price - np.mean(current_cluster)) / np.mean(current_cluster) < self.cluster_tolerance:
                current_cluster.append(price)
            else:
                # 保存当前聚类的均值
                clusters.append(np.mean(current_cluster))
                current_cluster = [price]
        
        # 保存最后一个聚类
        if current_cluster:
            clusters.append(np.mean(current_cluster))
        
        return clusters
    
    def detect_range(self, current_idx):
        """
        检测当前的支撑压力区间
        
        Args:
            current_idx: 当前索引
            
        Returns:
            up_line: 压力位
            down_line: 支撑位
        """
        # 获取回看窗口数据
        start_idx = max(0, current_idx - self.lookback)
        window_data = self.data.iloc[start_idx:current_idx]
        
        # 临时更新数据视图
        old_data = self.data
        self.data = window_data
        
        # 识别局部极值
        highs, lows = self.find_local_extrema()
        
        # 恢复原数据
        self.data = old_data
        
        # 聚类
        resistance_levels = self.cluster_levels(highs)
        support_levels = self.cluster_levels(lows)
        
        # 选择最近的支撑和压力位
        current_price = window_data['close'].iloc[-1]
        
        up_line = min([r for r in resistance_levels if r > current_price], 
                     default=window_data['high'].max())
        down_line = max([s for s in support_levels if s < current_price], 
                       default=window_data['low'].min())
        
        return up_line, down_line


class AdaptiveRangeDetector(bt.Indicator):
    """
    自适应范围检测器
    
    结合Donchian通道和波动率调整
    """
    
    lines = ('up_line', 'down_line', 'mid_line', 'range_height')
    params = (
        ('lookback', 20),
        ('atr_period', 14),
        ('volatility_factor', 1.5),  # 波动率调整系数
    )
    
    def __init__(self):
        # Donchian通道基础
        self.highest = bt.indicators.Highest(self.data.high, period=self.params.lookback)
        self.lowest = bt.indicators.Lowest(self.data.low, period=self.params.lookback)
        
        # ATR用于波动率调整
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        
        # 计算UP/DOWN线
        self.lines.up_line = self.highest
        self.lines.down_line = self.lowest
        self.lines.mid_line = (self.lines.up_line + self.lines.down_line) / 2
        self.lines.range_height = self.lines.up_line - self.lines.down_line
    
    def next(self):
        """每根K线调用一次"""
        # 可以根据ATR动态调整区间范围
        # 如果波动率过大，可以扩大区间；波动率过小，可以缩小区间
        
        # 示例：如果区间高度小于2倍ATR，认为区间过窄，可能不适合交易
        min_range = 2 * self.atr[0]
        if self.lines.range_height[0] < min_range:
            # 标记为无效区间（可以在策略中检查）
            pass


if __name__ == '__main__':
    # 测试代码
    print("Range Detector Module - Ready")
    print("可用检测器:")
    print("  1. DonchianRangeDetector - Donchian通道法")
    print("  2. SupportResistanceDetector - 支撑压力位聚类法")
    print("  3. AdaptiveRangeDetector - 自适应范围检测法")
