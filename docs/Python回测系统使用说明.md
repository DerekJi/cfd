# Python 回测系统使用说明

## 📋 项目简介

这是一个基于 Backtrader 框架的 CFD 交易回测系统，实现了【半自动交易策略逻辑 V3.0】中的五步状态机策略。

## 🚀 快速开始

### 1. 安装依赖

```bash
cd backtest
pip install -r requirements.txt
```

**注意**: TA-Lib 可选，如果安装失败可以跳过。

### 2. 运行回测

```bash
python run_backtest.py
```

首次运行会自动生成示例数据并进行回测。

## 📊 项目结构

```
backtest/
├── data/                    # 数据目录
│   └── EURUSD_5m_test.csv  # 示例数据（自动生成）
├── strategies/              # 策略模块
│   ├── range_detector.py   # UP/DOWN线识别
│   └── range_breakout_v3.py # 主策略类
├── indicators/              # 技术指标
│   ├── atr_buffer.py       # ATR + Buffer
│   └── state_machine.py    # 五步状态机
├── utils/                   # 工具模块
│   ├── data_loader.py      # 数据加载
│   └── analyzers.py        # 自定义分析器
├── config.py                # 配置参数
└── run_backtest.py          # 主运行脚本
```

## ⚙️ 配置参数

主要参数在 `config.py` 中配置：

### UP/DOWN 识别参数

```python
RANGE_DETECTION_CONFIG = {
    'method': 'donchian',       # 检测方法
    'lookback_period': 20,      # 回看周期（20根K线）
    'min_range_height': 0.0010, # 最小区间高度（10 pips）
}
```

### 策略参数

```python
STRATEGY_CONFIG = {
    'confirm_bars': 1,          # 突破确认K线数
    'max_wait_bars': 6,         # 最大等待时间（30分钟）
    'trailing_stop_enabled': True, # 是否启用移动止损
}
```

### ATR 参数

```python
ATR_CONFIG = {
    'period': 14,               # ATR周期
    'buffer_multiplier': 0.2,   # Buffer系数
}
```

## � 使用真实数据

### 快速获取数据

```bash
# 方式1：使用交互式下载工具
python download_data.py

# 方式2：从HistData.com手动下载后转换
python convert_histdata.py
```

详细指南请查看：[数据获取指南.md](数据获取指南.md)

### 数据格式

CSV 文件格式要求：

```csv
datetime,open,high,low,close,volume
2024-01-01 00:00:00,1.10000,1.10050,1.09950,1.10020,1000
2024-01-01 00:05:00,1.10020,1.10080,1.10010,1.10060,1200
...
```

### 配置数据路径

在 `config.py` 中修改：

```python
DATA_CONFIG = {
    'symbol': 'EURUSD',
    'timeframe': '5min',
    'start_date': '2024-01-01',
    'end_date': '2026-02-14',
    'data_path': './backtest/data/EURUSD_5m_2024-2026.csv',
}
```

### 运行真实数据回测

修改 `run_backtest.py` 最后一行：

```python
# 使用真实数据
run_backtest(use_sample_data=False)
```

## 🔍 五步状态机逻辑

### 状态 0: IDLE（静默）
- 等待价格突破 UP 线

### 状态 1: TOUCHING（触碰中）
- 价格持续在 UP 线上方
- 确认条件：保持 1 根完整 K 线以上

### 状态 2: TOUCHED_SUCCESS（有效突破）
- 记录 Peak 价格
- 等待回落到 UP - Buffer

### 状态 3: RETRACED（回落确认）
- 记录 Dip 价格
- 等待突破 Peak 价格入场
- 失效条件：
  - 跌破中轴
  - 假突破（跌破UP线）
  - 超时（30分钟）

### 状态 4: POSITION（持仓管理）
- 初始止损：Dip - ATR
- 移动止损：跟随最高价上移

## 📊 输出结果

### 终端输出

运行回测会在终端显示：
- 实时状态转换信息
- 入场/出场详情
- 策略统计指标

### 回测报告

自动保存在 `results/reports/` 目录下：
- 详细交易记录
- 每笔交易的盈亏
- 持仓时间统计

### 图表输出

Backtrader 自动生成可视化图表（需要matplotlib）。

## 🛠️ 调试和优化

### 启用调试模式

在策略参数中设置：

```python
cerebro.addstrategy(
    RangeBreakoutStrategy,
    debug=True  # 打印详细信息
)
```

### 参数优化

使用 Backtrader 的优化功能：

```python
cerebro.optstrategy(
    RangeBreakoutStrategy,
    lookback_period=range(10, 50, 5),
    buffer_multiplier=[0.1, 0.2, 0.3]
)
```

## 🐛 常见问题

### Q: TA-Lib 安装失败
A: TA-Lib 是可选依赖，不影响核心功能。可以跳过或参考官方文档安装。

### Q: 没有数据文件
A: 首次运行使用 `use_sample_data=True` 会自动生成示例数据。

### Q: 回测结果不理想
A: 
1. 检查数据质量和格式
2. 调整参数（lookback_period, buffer_multiplier）
3. 验证止损逻辑

### Q: 图表显示失败
A: 在非交互环境（如服务器）中，设置 `plot_results=False`。

## 📚 进一步学习

- [Backtrader 官方文档](https://www.backtrader.com/docu/)
- [策略逻辑文档](../docs/半自动交易策略逻辑%20V3.0.md)
- [任务书](../docs/任务书2-Python回测系统开发.md)

## 🤝 联系方式

如有问题，请查阅项目文档或提交 Issue。

---

**版本**: V3.0  
**最后更新**: 2026-02-14
