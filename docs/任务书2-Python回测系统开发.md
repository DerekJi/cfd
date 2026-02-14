# 任务书2：Python 回测系统开发

## 📋 项目概述

开发一个Python量化回测系统，自动识别震荡区间的UP/DOWN线，验证【半自动交易策略逻辑 V3.0】在历史数据中的表现。

---

## 🎯 核心目标

1. **自动化UP/DOWN识别**：使用技术指标自动识别支撑压力位
2. **完整回测**：在2年历史数据上验证策略有效性
3. **详细报告**：输出胜率、盈亏比、最大回撤等关键指标

---

## 📊 系统架构设计

### 技术栈选择
```
核心框架: Backtrader (v1.9.78+) 或 VectorBT (v0.26+)
数据源: OANDA API 或 MT5 历史数据
数据格式: EURUSD 5分钟K线，至少2年数据
编程语言: Python 3.9+
依赖库: pandas, numpy, matplotlib, ta-lib (可选)
```

### 项目目录结构
```
cfd/
├── backtest/
│   ├── data/
│   │   └── EURUSD_5m_2024-2026.csv
│   ├── strategies/
│   │   ├── range_breakout_v3.py      # 主策略类
│   │   └── range_detector.py         # UP/DOWN自动识别
│   ├── indicators/
│   │   ├── atr_buffer.py             # ATR + Buffer计算
│   │   └── state_machine.py          # 状态机逻辑
│   ├── utils/
│   │   ├── data_loader.py            # 数据加载
│   │   └── analyzers.py              # 自定义分析器
│   ├── config.py                     # 配置参数
│   ├── run_backtest.py               # 主运行脚本
│   └── requirements.txt              # 依赖清单
├── results/
│   ├── reports/                      # 回测报告
│   ├── charts/                       # 图表输出
│   └── logs/                         # 日志文件
└── docs/
    └── Python回测系统使用说明.md
```

---

## 🔍 核心功能需求

### 1. 自动识别UP/DOWN线

#### 方法1：Donchian Channel（推荐）
```python
"""
Donchian通道 = N周期的最高/最低价
适用于震荡区间识别
"""
lookback_period = 20  # 回看20根K线
UP = df['high'].rolling(lookback_period).max()
DOWN = df['low'].rolling(lookback_period).min()
```

**优点**：
- 简单直观，计算快速
- 适合震荡行情
- 自动适应波动范围

**参数可调**：
- `lookback_period`：20-50根K线（100-250分钟）

#### 方法2：支撑/压力位聚类（高级）
```python
"""
基于局部高低点聚类识别关键价位
更接近人工判断逻辑
"""
1. 识别局部高点和低点（ZigZag算法）
2. 对高点和低点进行价格聚类（K-Means）
3. 选择最近的聚类中心作为UP/DOWN
```

**优点**：
- 更接近人工划线逻辑
- 能识别真正的支撑压力位

**缺点**：
- 实现复杂
- 计算耗时

**推荐方案**：先用方法1验证，如果效果好，再尝试方法2优化

#### 方法3：混合方案（折中）
```python
"""
结合Donchian + Pivot Points
"""
donchian_up = df['high'].rolling(20).max()
pivot_resistance = (df['high'] + df['low'] + df['close']).shift(1) / 3
UP = (donchian_up + pivot_resistance) / 2  # 加权平均
```

### 2. 五步状态机实现

#### 状态管理器（StateMachine类）
```python
class RangeBreakoutStateMachine:
    """
    五步状态机核心逻辑
    """
    def __init__(self):
        self.state = 0  # 0:IDLE, 1:TOUCHING, 2:TOUCHED, 3:RETRACED, 4:POSITION
        self.touch_start_time = None
        self.peak_price = None
        self.dip_price = None
        self.entry_price = None
        self.stop_loss = None
        
    def update(self, bar_data, up, down, atr):
        """
        每根K线调用一次，更新状态
        """
        if self.state == 0:
            return self._check_idle(bar_data, up)
        elif self.state == 1:
            return self._check_touching(bar_data, up)
        # ... 其他状态
```

#### 关键参数设置
```python
CONFIRM_BARS = 1          # 30秒 ≈ 0.1根5分钟K线，向上取整为1根
BUFFER_MULTIPLIER = 0.2   # Buffer = 0.2 × ATR
ATR_PERIOD = 14           # ATR计算周期
MAX_WAIT_BARS = 6         # 30分钟 = 6根5分钟K线
RISK_PER_TRADE = 0.01     # 单笔风险1%
```

### 3. 状态转换详细逻辑

#### 状态0 → 状态1（IDLE → TOUCHING）
```python
def _check_idle(self, bar, up):
    if bar['close'] > up:
        self.touch_start_time = bar['time']
        self.state = 1
        return 'TOUCHING'
    return 'IDLE'
```

#### 状态1 → 状态2 或 回到状态0
```python
def _check_touching(self, bar, up):
    bars_elapsed = self._bars_since_touch_start(bar)
    
    # 重置条件：价格跌回UP之下
    if bar['close'] <= up:
        self.state = 0
        return 'RESET_TO_IDLE'
    
    # 确认条件：保持1根完整K线以上
    if bars_elapsed >= self.CONFIRM_BARS:
        self.peak_price = self._get_peak_during_touch()
        self.state = 2
        return 'TOUCHED_SUCCESS'
    
    return 'TOUCHING'
```

#### 状态2 → 状态3（TOUCHED → RETRACED）
```python
def _check_touched(self, bar, up, buffer):
    if bar['close'] <= (up - buffer):
        self.dip_price = bar['low']  # 开始记录回落低点
        self.retraced_start_time = bar['time']
        self.state = 3
        return 'RETRACED'
    # 持续更新peak_price
    self.peak_price = max(self.peak_price, bar['high'])
    return 'TOUCHED_SUCCESS'
```

#### 状态3 → 状态4 或 回到状态0
```python
def _check_retraced(self, bar, up, down):
    mid = (up + down) / 2
    bars_waited = self._bars_since_retraced_start(bar)
    
    # 失效条件1：跌破中轴
    if self.dip_price < mid:
        self.state = 0
        return 'FAILED_BELOW_MID'
    
    # 失效条件2：假突破（重新跌破UP）
    if bar['close'] < up:
        self.state = 0
        return 'FAILED_FAKE_BREAKOUT'
    
    # 失效条件3：超时30分钟
    if bars_waited > self.MAX_WAIT_BARS:
        self.state = 0
        return 'FAILED_TIMEOUT'
    
    # 入场触发：突破Peak_Price
    if bar['close'] > self.peak_price:
        self.entry_price = bar['close']
        self.stop_loss = self.dip_price - self._calculate_spread()
        self.state = 4
        return 'ENTRY_LONG'
    
    # 持续更新dip_price
    self.dip_price = min(self.dip_price, bar['low'])
    return 'RETRACED'
```

#### 状态4（POSITION持仓管理）
```python
def _check_position(self, bar):
    # 检查止损
    if bar['close'] < self.stop_loss:
        exit_price = bar['close']
        pnl = self._calculate_pnl(self.entry_price, exit_price)
        self.state = 0
        return 'EXIT_STOP_LOSS', pnl
    
    # 移动止损
    fixed_stop_distance = self.entry_price - self.stop_loss
    new_high = bar['high']
    if new_high > self.peak_price:
        self.peak_price = new_high
        new_stop = new_high - fixed_stop_distance
        if new_stop > self.stop_loss:
            self.stop_loss = new_stop
    
    return 'POSITION_HOLDING', None
```

### 4. 仓位计算

```python
def calculate_position_size(account_equity, entry_price, stop_loss, risk_percent=0.01):
    """
    根据账户净值和风险百分比计算仓位
    
    Args:
        account_equity: 账户净值（美元）
        entry_price: 入场价格
        stop_loss: 止损价格
        risk_percent: 单笔风险百分比（默认1%）
    
    Returns:
        units: OANDA单位数
    """
    risk_amount = account_equity * risk_percent  # 例如 $10000 * 0.01 = $100
    stop_distance = abs(entry_price - stop_loss)  # 例如 0.0030
    position_size = risk_amount / stop_distance   # $100 / 0.0030 = 33,333 units
    return int(position_size)
```

### 5. 回测引擎配置

```python
# Backtrader策略框架
class RangeBreakoutStrategy(bt.Strategy):
    params = (
        ('lookback_period', 20),
        ('confirm_bars', 1),
        ('buffer_multiplier', 0.2),
        ('atr_period', 14),
        ('max_wait_bars', 6),
        ('risk_per_trade', 0.01),
        ('initial_capital', 10000),
    )
    
    def __init__(self):
        self.state_machine = RangeBreakoutStateMachine()
        self.atr = bt.indicators.ATR(period=self.params.atr_period)
        self.up_line = self.data.high.rolling(self.params.lookback_period).max()
        self.down_line = self.data.low.rolling(self.params.lookback_period).min()
    
    def next(self):
        # 每根K线调用
        current_bar = {
            'time': self.data.datetime.datetime(0),
            'open': self.data.open[0],
            'high': self.data.high[0],
            'low': self.data.low[0],
            'close': self.data.close[0],
        }
        
        buffer = self.atr[0] * self.params.buffer_multiplier
        signal = self.state_machine.update(
            current_bar, 
            self.up_line[0], 
            self.down_line[0], 
            self.atr[0]
        )
        
        if signal == 'ENTRY_LONG' and not self.position:
            size = calculate_position_size(
                self.broker.getvalue(),
                self.data.close[0],
                self.state_machine.stop_loss,
                self.params.risk_per_trade
            )
            self.buy(size=size)
        
        elif signal[0] == 'EXIT_STOP_LOSS' and self.position:
            self.close()
```

---

## 📈 回测指标和报告

### 1. 核心指标
```python
# 需要输出的关键指标
metrics = {
    '总交易次数': total_trades,
    '胜率': win_rate,                    # 盈利交易 / 总交易
    '平均盈亏比': avg_win / avg_loss,    # R倍数
    '总收益率': total_return_pct,        # (期末-期初) / 期初
    '最大回撤': max_drawdown_pct,        # 最大资金回撤百分比
    '夏普比率': sharpe_ratio,           # (年化收益 - 无风险利率) / 年化波动率
    '盈利因子': profit_factor,          # 总盈利 / 总亏损
    '平均持仓时间': avg_holding_bars,   # K线数量
    '失效信号数': failed_signals,       # 状态3失效次数
}
```

### 2. 按失效原因分类统计
```python
failure_analysis = {
    '跌破中轴失效': count_below_mid,
    '假突破失效': count_fake_breakout,
    '超时失效': count_timeout,
    '总失效次数': total_failures,
    '失效率': total_failures / (total_trades + total_failures)
}
```

### 3. 可视化图表

#### 必需图表
1. **资金曲线图**（Equity Curve）
   - X轴：日期
   - Y轴：账户净值
   - 标注：每笔交易的入场/出场点

2. **回撤曲线图**（Drawdown Chart）
   - 显示历史最大回撤位置
   - 标注回撤持续时间

3. **交易分布图**
   - 柱状图：盈利交易 vs 亏损交易
   - 显示盈亏比分布

4. **月度收益表**（Monthly Returns Heatmap）
   - 行：年份
   - 列：月份
   - 颜色：收益率（绿色盈利，红色亏损）

#### 可选图表
5. **状态转换流程图**
   - 显示各状态之间的转换次数
   - Sankey图或流程图

6. **典型案例回放**
   - 选择3-5个典型交易
   - 绘制详细的K线图 + 状态标注

---

## 🛠️ 实现步骤

### Phase 1: 环境搭建（1-2小时）
```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 下载历史数据
python utils/data_loader.py --pair EURUSD --timeframe 5m --start 2024-01-01 --end 2026-01-01
```

### Phase 2: 核心逻辑开发（4-6小时）
1. 实现`state_machine.py`（状态机核心）
2. 实现`range_detector.py`（UP/DOWN识别）
3. 实现`range_breakout_v3.py`（主策略类）

### Phase 3: 回测运行（1小时）
1. 配置参数（`config.py`）
2. 运行`run_backtest.py`
3. 验证是否有语法错误

### Phase 4: 结果分析和优化（2-3小时）
1. 查看回测报告
2. 参数敏感性测试
3. 优化关键参数

---

## 📦 可交付成果

### 代码文件
- [ ] 所有`.py`文件（按目录结构组织）
- [ ] `requirements.txt`（依赖清单）
- [ ] `config.py`（可配置参数）
- [ ] `README.md`（快速上手指南）

### 数据文件
- [ ] `EURUSD_5m_2024-2026.csv`（至少2年数据）
- [ ] 数据说明文档（字段含义、时区等）

### 回测报告
- [ ] `backtest_report.html`（交互式HTML报告）
- [ ] `performance_summary.txt`（纯文本总结）
- [ ] `equity_curve.png`（资金曲线图）
- [ ] `monthly_returns.png`（月度收益图）
- [ ] `trade_analysis.csv`（每笔交易详细记录）

### 文档
- [ ] `Python回测系统使用说明.md`
  - 环境安装步骤
  - 如何运行回测
  - 如何调整参数
  - 如何解读报告
  - 常见问题FAQ

---

## ✅ 验证标准

### 功能验证
- [ ] 状态机能正确识别所有5个状态
- [ ] UP/DOWN线动态变化合理
- [ ] 入场和止损价格计算正确
- [ ] 仓位计算符合1%风险要求

### 性能验证
- [ ] 2年数据（约210,000根K线）在10分钟内完成回测
- [ ] 内存占用 < 2GB
- [ ] 无内存泄漏或崩溃

### 结果验证
- [ ] 至少产生50笔交易（平均每月2笔）
- [ ] 胜率在40%-60%之间（合理范围）
- [ ] 平均盈亏比 > 1.5（说明策略有潜力）
- [ ] 最大回撤 < 30%（可接受范围）

---

## 🎓 技术参考

### Backtrader文档
- 官方文档：https://www.backtrader.com/docu/
- 自定义指标：https://www.backtrader.com/docu/inddev/
- 策略开发：https://www.backtrader.com/docu/strategy/

### 数据获取
- OANDA API：https://developer.oanda.com/
- MT5 Python：https://www.mql5.com/en/docs/python_metatrader5

### 量化策略参考
- QuantConnect论坛：https://www.quantconnect.com/forum
- 震荡突破策略：搜索"Range Breakout Strategy backtest"

---

## 🚀 可选增强功能

### 1. 参数优化
```python
# 使用网格搜索找到最优参数
param_grid = {
    'lookback_period': [15, 20, 25, 30],
    'buffer_multiplier': [0.1, 0.2, 0.3],
    'confirm_bars': [1, 2],
}
# 输出：最优参数组合 + 各参数的敏感性分析
```

### 2. Walk-Forward测试
```python
# 避免过拟合
# 在2024年数据上优化参数
# 在2025年数据上验证效果
```

### 3. 蒙特卡洛模拟
```python
# 随机打乱交易顺序1000次
# 验证策略稳健性
# 计算95%置信区间的收益范围
```

### 4. 做空逻辑
```python
# 增加突破DOWN线的做空逻辑
# 实现完整的双向交易系统
```

### 5. 多品种测试
```python
# 在GBPUSD, USDJPY, XAUUSD上测试
# 验证策略的普适性
```

---

## ⚠️ 关键注意事项

1. **数据质量**：
   - 确保数据无缺失、无重复
   - 检查是否有异常跳价（Flash Crash）
   - 时区统一（最好用UTC）

2. **过拟合风险**：
   - 不要过度优化参数
   - 使用Walk-Forward验证
   - 保持策略逻辑简单

3. **现实因素**：
   - 要考虑点差（spread）：EURUSD约0.8-1.5点
   - 要考虑滑点（slippage）：快速行情可能1-2点
   - 回测盈利 ≠ 实盘盈利

4. **与Pine Script版本对比**：
   - Python的自动UP/DOWN vs Pine的人工设置
   - 对比两者的胜率差异
   - 评估人工判断的价值

---

## 📊 参数建议范围

基于策略逻辑，以下是合理的参数范围：

| 参数 | 默认值 | 合理范围 | 备注 |
|-----|-------|---------|------|
| lookback_period | 20 | 15-50 | 太小跟随噪音，太大滞后 |
| confirm_bars | 1 | 1-2 | 5分钟图不宜过大 |
| buffer_multiplier | 0.2 | 0.1-0.5 | 波动大时可增加 |
| atr_period | 14 | 10-20 | 标准ATR周期 |
| max_wait_bars | 6 | 4-10 | 20-50分钟 |
| risk_per_trade | 0.01 | 0.005-0.02 | 0.5%-2% |

---

## 🎯 预期结果（基准）

基于震荡突破策略的一般表现，预期指标：

```
胜率: 45-55%        （震荡突破策略典型胜率）
盈亏比: 1.5-2.5     （止损固定，盈利移动止损）
年化收益: 15-30%    （1%风险下）
最大回撤: 15-25%    （连续亏损时）
夏普比率: 0.8-1.5   （>1即可接受）
```

如果实际结果显著偏离，需要检查：
1. 数据质量问题
2. 代码逻辑错误
3. 参数设置不当
4. 策略逻辑可能需要调整
