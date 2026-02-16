"""
反向突破策略测试
Fade Strategy: 利用假突破，反向入场
"""

# 策略逻辑：
# 1. 检测到突破UP线 → 不做多，而是等待回落
# 2. 如果价格回落到UP线以下 → 说明是假突破，做空
# 3. 止损设在突破后的peak价格
# 4. 目标是回到mid_line或down_line

# 理论依据：
# - 假突破率68.5%意味着大部分突破都会失败
# - 失败的突破往往会快速回落到区间内
# - 这是典型的"震荡行情回归均值"特征

# 参数配置建议：
FADE_STRATEGY_CONFIG = {
    'enable_fade': True,  # 启用反向策略
    'wait_bars_after_breakout':  3,  # 突破后等待3根K线
    'fade_entry_threshold': 0.5,  # 回落到UP线以下50%Buffer时入场
    'fade_stop_multiplier': 1.5,  # 止损=Peak + 1.5×ATR
    'fade_target': 'mid_line',  # 目标价位：mid_line或down_line
}

# 实现流程：
# - State 1 (IDLE): 检测突破
# - State 2 (BREAKOUT_WATCH): 突破后观察，记录peak
# - State 3 (FADE_SIGNAL): 价格回落到入场阈值
# - State 4 (FADE_POSITION): 持有反向仓位

print("""
💡 策略切换建议：

当前策略(突破做多)：
- 胜率: 34.3%
- 盈亏比: 1.73
- 假突破率: 68.5%

建议测试反向策略(假突破做空):
- 理论胜率: ~65-70%（接近假突破率）
- 盈亏比可能降低（均值回归空间有限）
- 更适合震荡市场

具体实现：
1. 修改state_machine.py，添加FADE模式
2. 或单独创建fade_strategy.py
3. 对比两种策略在同一数据上的表现

是否要实现反向策略进行对比测试？
""")
