"""
ADX (Average Directional Index) 指标

ADX用于衡量趋势的强度（不区分方向）
- ADX > 25: 强趋势
- ADX < 20: 弱趋势/震荡
"""

import backtrader as bt


class ADX(bt.Indicator):
    """
    ADX指标：衡量趋势强度
    
    计算步骤：
    1. 计算+DM和-DM（方向性移动）
    2. 计算TR（真实波幅）
    3. 计算+DI和-DI（方向指标）
    4. 计算DX（方向指数）
    5. 计算ADX（DX的移动平均）
    """
    
    lines = ('adx', 'plus_di', 'minus_di')
    params = (
        ('period', 14),  # ADX周期
    )
    
    def __init__(self):
        # 使用backtrader内置的ADX指标
        adx_indicator = bt.indicators.DirectionalMovementIndex(
            self.data,
            period=self.params.period
        )
        
        # 映射到我们的lines
        self.lines.adx = adx_indicator.adx
        self.lines.plus_di = adx_indicator.plusDI
        self.lines.minus_di = adx_indicator.minusDI
    
    def next(self):
        """每根K线调用一次"""
        pass  # 计算已在__init__中完成


class ADXTrendFilter(bt.Indicator):
    """
    基于ADX的趋势过滤器
    
    提供趋势强度判断和方向判断
    """
    
    lines = ('is_strong_trend', 'is_uptrend', 'is_downtrend')
    params = (
        ('period', 14),  # ADX周期
        ('threshold', 25),  # ADX阈值（大于此值才认为是强趋势）
    )
    
    def __init__(self):
        # ADX指标
        self.adx = ADX(self.data, period=self.params.period)
        
        # 趋势强度判断
        self.lines.is_strong_trend = self.adx.adx > self.params.threshold
        
        # 趋势方向判断
        # +DI > -DI 表示上升趋势
        # -DI > +DI 表示下降趋势
        self.lines.is_uptrend = (
            (self.adx.adx > self.params.threshold) & 
            (self.adx.plus_di > self.adx.minus_di)
        )
        self.lines.is_downtrend = (
            (self.adx.adx > self.params.threshold) & 
            (self.adx.minus_di > self.adx.plus_di)
        )
    
    def next(self):
        """每根K线调用一次"""
        pass  # 计算已在__init__中完成
