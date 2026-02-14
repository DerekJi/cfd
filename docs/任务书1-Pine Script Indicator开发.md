# 任务书1：Pine Script Indicator 开发

## 📋 项目概述

开发一个TradingView Pine Script指标，用于可视化【半自动交易策略逻辑 V3.0】中的五步状态机，辅助人工验证策略有效性。

---

## 🎯 核心目标

1. **状态机可视化**：在图表上清晰显示5个状态的转换过程
2. **信号标记**：自动标记潜在入场点和止损位
3. **手动验证**：配合TradingView的Bar Replay功能进行手动回测

---

## 📊 功能需求详细说明

### 1. 输入参数（Input Parameters）

```pinescript
// 用户输入参数
UP_line = input.float(0.0, "UP线价格（手动设置）", step=0.0001)
DOWN_line = input.float(0.0, "DOWN线价格（手动设置）", step=0.0001)
confirm_seconds = input.int(30, "突破确认秒数", minval=10, maxval=300)
buffer_multiplier = input.float(0.2, "Buffer系数（倍ATR）", step=0.1)
atr_length = input.int(14, "ATR周期", minval=5)
trailing_stop_enabled = input.bool(true, "启用移动止损显示")
```

### 2. 技术指标计算

- **ATR计算**：14周期ATR（可调）
- **Buffer计算**：`Buffer = ATR × 0.2`（可调）
- **区间中轴**：`MID = (UP + DOWN) / 2`

### 3. 五步状态机逻辑

#### 状态 0: IDLE（静默）
- **触发条件**：`close > UP`
- **动作**：记录`touch_start_time = time`，转入状态1
- **图表标记**：无

#### 状态 1: TOUCHING（触碰中）
- **维持条件**：`close > UP` 且持续时间 >= `confirm_seconds`秒
  - 计算方法：`(time - touch_start_time) >= confirm_seconds * 1000`（毫秒）
- **转入状态2条件**：满足维持条件
- **重置条件**：`close <= UP` → 回到状态0
- **图表标记**：在UP线上方显示黄色小圆点 ⚠️

#### 状态 2: TOUCHED_SUCCESS（有效突破）
- **记录**：`Peak_Price = highest(high, 触碰期间)`
- **转入状态3条件**：`close <= (UP - Buffer)`
- **图表标记**：
  - 在Peak_Price位置画绿色向上箭头 ✓
  - 在UP线位置画水平虚线

#### 状态 3: RETRACED（回落确认）
- **记录**：`Dip_Price = lowest(low, 回落期间)`
- **入场触发**：`close > Peak_Price`
- **失效条件**（任一满足则回到状态0）：
  1. `Dip_Price < MID`（跌破中轴）
  2. `close < UP`（假突破）
  3. 超过30分钟（6根5分钟K线）未触发入场
- **图表标记**：
  - 在Dip_Price位置画红色小圆圈（潜在止损位）
  - 在Peak_Price位置画橙色虚线（入场触发线）
  - 显示"等待入场"文字标签

#### 状态 4: POSITION（持仓管理）
- **入场标记**：在入场K线画大号绿色向上三角形 🔺 + "BUY"标签
- **初始止损**：`Stop_Loss = Dip_Price - (1 × ATR)` （模拟Spread）
- **移动止损**（可选显示）：
  - 每根K线收盘检查
  - 如果 `new_high = highest(high, 入场后K线数)` 创新高
  - 则 `Stop_Loss = new_high - (Entry_Price - Dip_Price)`
  - 绘制红色虚线逐步上移
- **出场标记**：
  - 如果`close < Stop_Loss`，画红色向下三角形 🔻 + "EXIT"标签

### 4. 图表可视化要求

#### 颜色方案
- **UP线**：蓝色实线（linewidth=2）
- **DOWN线**：红色实线（linewidth=2）
- **区间中轴**：灰色虚线（linewidth=1）
- **状态1**：黄色小圆点
- **状态2**：绿色箭头 + 绿色虚线
- **状态3**：橙色虚线 + 红色圆圈
- **状态4-入场**：绿色三角形 + 移动的红色止损线

#### 背景色标记（可选）
- 状态1（TOUCHING）：淡黄色背景
- 状态3（RETRACED）：淡橙色背景
- 状态4（POSITION）：淡绿色背景

#### 信息面板
在图表右上角显示当前状态：
```
当前状态: IDLE / TOUCHING / TOUCHED / RETRACED / POSITION
Peak Price: 1.0850
Dip Price: 1.0820
ATR: 0.0015
Buffer: 0.0003
```

---

## 🛠️ 技术实现要点

### 关键难点和解决方案

#### 1. 时间判断（30秒确认）
Pine Script 5分钟图特点：
- 每根K线代表 300 秒
- 无法获取K线内的秒级数据

**解决方案**：
```pinescript
// 使用K线数量近似
// 30秒 ≈ 0.1根5分钟K线
// 实际操作：要求至少保持1根完整K线
confirm_bars = math.ceil(confirm_seconds / 300)
```

#### 2. 状态持久化
使用`var`关键字保持状态：
```pinescript
var int state = 0  // 0=IDLE, 1=TOUCHING, 2=TOUCHED, 3=RETRACED, 4=POSITION
var float peak_price = na
var float dip_price = na
var int touch_start_bar = na
```

#### 3. 手动设置UP/DOWN线
两种方式二选一：
- **方式1**：在Input中手动输入价格（本方案采用）
- **方式2**：使用TradingView的水平线绘图功能（需要Pine Script v5的line API）

---

## 📦 可交付成果

### 文件清单
1. `range_breakout_indicator_v3.0.pine` - 主程序文件
2. `使用说明.md` - 详细使用文档，包含：
   - 如何在TradingView中加载脚本
   - 如何设置UP/DOWN线
   - 如何使用Bar Replay进行手动回测
   - 信号解读指南
   - 常见问题FAQ

### 测试要求
1. **基础功能测试**：
   - 在EURUSD 5分钟图上加载
   - 设置UP=1.0850, DOWN=1.0800
   - 验证状态转换是否正确

2. **边界情况测试**：
   - 测试"假突破"防御（状态3回落破UP）
   - 测试"跌破中轴"失效逻辑
   - 测试30分钟超时机制

3. **Bar Replay验证**：
   - 选择2024年某一天的EURUSD行情
   - 手动设置UP/DOWN
   - 逐K线回放，验证信号准确性

---

## 📈 使用场景示例

### 场景1：标准突破-回踩-入场
```
1. 价格突破UP线（1.0850）
2. 保持30秒以上 → 黄点变绿箭头
3. 回落至1.0835 → 显示橙色虚线+红圈
4. 再次突破绿色Peak线 → BUY信号
5. 移动止损逐步上移
```

### 场景2：假突破被过滤
```
1. 价格突破UP线
2. 仅保持20秒 → 黄点消失
3. 回落到UP之下 → 状态重置为IDLE
4. 避免了错误入场
```

---

## 🎓 参考资料

### Pine Script学习资源
- TradingView Pine Script 文档：https://www.tradingview.com/pine-script-docs/
- 状态机实现参考：https://www.tradingview.com/script/xxx（如有）

### 策略原始文档
- 参考文件：`半自动交易策略逻辑 V3.0.md`
- 重点章节：第二章（五步状态机）

---

## ⚠️ 重要提示

1. **这是Indicator而非Strategy**：
   - 不会自动下单
   - 不能在Strategy Tester中运行
   - 仅用于信号提示和手动验证

2. **免费版TradingView限制**：
   - 一个图表最多3个指标
   - 无法自动化回测
   - 需要配合Bar Replay手动验证

3. **UP/DOWN线设置**：
   - 需要根据当天行情人工判断
   - 建议每天开盘前设置一次
   - 可参考15分钟或1小时图的关键支撑/压力位

---

## ✅ 完成标准

- [ ] 所有5个状态都能正确识别和转换
- [ ] 图表标记清晰可见，符合设计要求
- [ ] 信息面板实时显示正确数据
- [ ] 假突破和失效条件能正确触发
- [ ] 使用说明文档完整，包含截图示例
- [ ] 在EURUSD 5分钟图上至少验证10个案例

---

## 🚀 可选增强功能（如有时间）

1. **多时间框架支持**：
   - 增加15分钟、1小时图支持
   - 自动调整confirm_seconds参数

2. **Alert报警功能**：
   - 状态1→2：提醒"关注突破"
   - 状态3→4：提醒"入场信号触发"

3. **统计信息**：
   - 显示当日触发的信号数量
   - 显示当前持仓的浮动盈亏

4. **做空逻辑**：
   - 增加对DOWN线的突破监测
   - 实现完整的双向交易信号
