# Pine Script Indicator - Range Breakout V3.0

## 项目简介

这是一个基于五步状态机的TradingView Pine Script指标，用于识别区间突破后的回调入场机会。

## 核心功能

- ✅ 五步状态机可视化（IDLE → TOUCHING → TOUCHED → RETRACED → POSITION）
- ✅ 智能过滤假突破（30秒确认机制 + Buffer）
- ✅ 自动标记入场点和止损位
- ✅ 移动止损实时显示
- ✅ Alert报警功能
- ✅ 实时信息面板

## 文件结构

```
pine-scripts/
  └── range_breakout_indicator_v3.0.pine    # 主程序文件
docs/
  └── 使用说明-Range_Breakout_Indicator_V3.0.md    # 详细使用文档
  └── 任务书1-Pine Script Indicator开发.md    # 项目需求文档
```

## 快速开始

### 1. 安装指标

1. 登录TradingView
2. 打开Pine Editor
3. 复制`range_breakout_indicator_v3.0.pine`文件内容
4. 粘贴到Pine Editor并保存
5. 点击"Add to Chart"

### 2. 设置参数

**必填参数**：
- `UP线价格`：区间上沿（如1.0850）
- `DOWN线价格`：区间下沿（如1.0800）

**可选参数**：
- `突破确认秒数`：默认30秒
- `Buffer系数`：默认0.2倍ATR
- `ATR周期`：默认14
- `启用移动止损显示`：默认开启

### 3. 使用Bar Replay验证

1. 选择历史日期（如EURUSD 2024-01-15）
2. 设置UP/DOWN线
3. 启动Bar Replay逐K线回放
4. 观察信号准确性

## 信号说明

| 标记 | 含义 | 操作 |
|------|------|------|
| 🟡 黄色圆点 | 触碰中 | 等待确认 |
| ✓ 绿色箭头 | 突破确认 | 等待回调 |
| 🟠 橙色虚线 | Peak触发线 | 准备入场 |
| 🔺 BUY | 入场信号 | 考虑做多 |
| 🔻 EXIT | 出场信号 | 止损离场 |

## 适用场景

- **交易品种**：外汇货币对（EURUSD、GBPUSD等）
- **时间周期**：5分钟图（推荐）、15分钟图
- **交易方向**：做多（V3.0版本）
- **验证方式**：Bar Replay手动回测

## 技术实现亮点

1. **时间确认机制**：使用K线数量近似秒级时间判断
2. **状态持久化**：使用`var`关键字保持状态跨K线传递
3. **动态止损**：入场后根据新高自动调整止损位
4. **多重失效保护**：假突破、跌破中轴、超时失效

## 测试要求

- [ ] 基础功能测试（状态转换正确性）
- [ ] 边界情况测试（假突破、跌破中轴、超时）
- [ ] Bar Replay验证（至少10个案例）
- [ ] 多品种测试（EURUSD、GBPUSD、USDJPY）

## 完成标准

- [x] 所有5个状态都能正确识别和转换
- [x] 图表标记清晰可见，符合设计要求
- [x] 信息面板实时显示正确数据
- [x] 假突破和失效条件能正确触发
- [x] 使用说明文档完整

## 未来增强计划

- [ ] V4.0：增加做空逻辑（DOWN线突破监测）
- [ ] 多时间框架支持（15分钟、1小时图）
- [ ] 统计信息（信号数量、胜率统计）
- [ ] 自定义颜色方案

## 参考文档

- [任务书1-Pine Script Indicator开发.md](docs/任务书1-Pine%20Script%20Indicator开发.md)
- [使用说明-Range_Breakout_Indicator_V3.0.md](docs/使用说明-Range_Breakout_Indicator_V3.0.md)
- [半自动交易策略逻辑 V3.0.md](docs/半自动交易策略逻辑%20V3.0.md)

## 免责声明

本指标仅供学习和研究使用，不构成投资建议。交易有风险，投资需谨慎。

---

**开发日期**：2024-02  
**版本**：V3.0  
**使用技术**：Pine Script V5
