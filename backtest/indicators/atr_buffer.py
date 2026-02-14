"""
ATR和Buffer计算指标
"""

import backtrader as bt


class ATRBuffer(bt.Indicator):
    """
    ATR + Buffer 计算指标
    
    Buffer = ATR × buffer_multiplier
    用于确定回落幅度的阈值
    """
    
    lines = ('atr', 'buffer')
    params = (
        ('period', 14),  # ATR计算周期
        ('buffer_multiplier', 0.2),  # Buffer系数
    )
    
    def __init__(self):
        # 计算ATR
        self.lines.atr = bt.indicators.ATR(
            self.data,
            period=self.params.period
        )
        
        # 计算Buffer
        self.lines.buffer = self.lines.atr * self.params.buffer_multiplier
    
    def next(self):
        """每根K线调用一次"""
        pass  # 计算已在__init__中完成


class SpreadSimulator(bt.Indicator):
    """
    点差模拟器
    
    用于在回测中模拟真实交易的点差成本
    """
    
    lines = ('spread',)
    params = (
        ('spread_pips', 1.0),  # 点差（pips）
        ('pip_value', 0.0001),  # 1 pip的价值（对于EURUSD为0.0001）
    )
    
    def __init__(self):
        self.lines.spread = self.params.spread_pips * self.params.pip_value
    
    def next(self):
        """每根K线调用一次"""
        pass


class VolatilityAdjuster(bt.Indicator):
    """
    波动率调整器
    
    根据市场波动率动态调整参数
    """
    
    lines = ('volatility_ratio', 'adjusted_buffer')
    params = (
        ('atr_period', 14),
        ('atr_reference_period', 50),  # 参考ATR周期（用于标准化）
        ('buffer_multiplier', 0.2),
    )
    
    def __init__(self):
        # 当前ATR
        self.current_atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        
        # 参考ATR（更长周期，用于衡量"正常"波动率）
        self.reference_atr = bt.indicators.SMA(
            bt.indicators.ATR(self.data, period=self.params.atr_period),
            period=self.params.atr_reference_period
        )
        
        # 波动率比率（当前波动率 / 正常波动率）
        self.lines.volatility_ratio = self.current_atr / self.reference_atr
        
        # 调整后的Buffer
        self.lines.adjusted_buffer = (
            self.lines.volatility_ratio * 
            self.current_atr * 
            self.params.buffer_multiplier
        )
    
    def next(self):
        """每根K线调用一次"""
        pass


if __name__ == '__main__':
    print("ATR Buffer Indicator - Ready")
    print("可用指标:")
    print("  1. ATRBuffer - ATR和Buffer计算")
    print("  2. SpreadSimulator - 点差模拟")
    print("  3. VolatilityAdjuster - 波动率调整")
