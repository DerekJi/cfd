"""
突破有效性验证
Breakout Validation with momentum and volume confirmation
"""

import backtrader as bt


class BreakoutValidator(bt.Indicator):
    """
    突破有效性验证器
    
    真正的有效突破应该具有：
    1. 价格持续在突破位上方
    2. 波动率提升（ATR增加）
    3. 动能确认（连续K线突破）
    """
    
    lines = ('valid_breakout_up', 'valid_breakout_down', 'momentum')
    
    params = (
        ('atr_period', 14),
        ('momentum_bars', 3),  # 动能确认K线数
        ('atr_threshold', 1.2),  # ATR提升阈值（倍数）
    )
    
    def __init__(self):
        # ATR用于波动率确认
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        self.atr_sma = bt.indicators.SMA(self.atr, period=self.params.atr_period)
        
        # 动能指标：最近N根K线的收盘价变化
        self.momentum = self.data.close - self.data.close(-self.params.momentum_bars)
        self.lines.momentum = self.momentum
    
    def next(self):
        """验证突破有效性"""
        # 波动率是否提升
        atr_ratio = self.atr[0] / self.atr_sma[0] if self.atr_sma[0] > 0 else 1.0
        volatility_spike = atr_ratio >= self.params.atr_threshold
        
        # 动能是否为正
        positive_momentum = self.momentum[0] > 0
        
        # 有效突破信号
        self.lines.valid_breakout_up[0] = 1.0 if (volatility_spike and positive_momentum) else 0.0
        self.lines.valid_breakout_down[0] = 1.0 if (volatility_spike and not positive_momentum) else 0.0


class RangeQualityFilter(bt.Indicator):
    """
    震荡区间质量过滤器
    
    只在真正的震荡区间才允许交易
    """
    
    lines = ('is_ranging', 'range_quality')
    
    params = (
        ('lookback', 20),
        ('min_touches', 3),  # 最小触碰次数
        ('min_in_range_pct', 50),  # 最小区间内比例
        ('max_range_cv', 40),  # 最大区间变异系数
    )
    
    def __init__(self):
        # Donchian Channel
        self.up_line = bt.indicators.Highest(self.data.high(-1), period=self.params.lookback)
        self.down_line = bt.indicators.Lowest(self.data.low(-1), period=self.params.lookback)
        self.mid_line = (self.up_line + self.down_line) / 2
        self.range_width = self.up_line - self.down_line
        
        # 区间宽度稳定性
        self.range_sma = bt.indicators.SMA(self.range_width, period=self.params.lookback)
        self.range_std = bt.indicators.StdDev(self.range_width, period=self.params.lookback)
    
    def next(self):
        """评估区间质量"""
        # 计算触碰次数（过去lookback根K线）
        touch_count = 0
        in_range_count = 0
        
        for i in range(min(self.params.lookback, len(self.data))):
            high_i = self.data.high[-i]
            low_i = self.data.low[-i]
            up_i = self.up_line[-i]
            down_i = self.down_line[-i]
            
            # 触碰上下轨
            if high_i >= up_i * 0.999 or low_i <= down_i * 1.001:
                touch_count += 1
            
            # 在区间内
            if low_i >= down_i and high_i <= up_i:
                in_range_count += 1
        
        in_range_pct = (in_range_count / self.params.lookback * 100) if self.params.lookback > 0 else 0
        
        # 区间变异系数
        range_cv = (self.range_std[0] / self.range_sma[0] * 100) if self.range_sma[0] > 0 else 100
        
        # 质量评分（0-100）
        touch_score = min(touch_count / self.params.min_touches * 30, 30)
        range_score = min(in_range_pct / self.params.min_in_range_pct * 40, 40)
        stability_score = max(30 - range_cv, 0)
        
        quality = touch_score + range_score + stability_score
        
        # 是否合格
        is_ranging = (
            touch_count >= self.params.min_touches and
            in_range_pct >= self.params.min_in_range_pct and
            range_cv <= self.params.max_range_cv
        )
        
        self.lines.is_ranging[0] = 1.0 if is_ranging else 0.0
        self.lines.range_quality[0] = quality
