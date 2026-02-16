# Backtest 目录结构说明

## 📁 目录组织

### 📝 根目录核心文件
```
backtest/
├── README.md                          📘 本说明文档
├── requirements.txt                   📦 Python依赖
├── config.py                          ⚙️ 主配置
├── config_trend_filter.py             ⚙️ 趋势策略配置
├── oanda_config_template.py           🔑 OANDA配置模板
├── run_trend_filter_backtest.py       ⭐ 主回测脚本
├── multi_symbol_test.py               ⭐ 多品种组合测试  
└── test_risk_allocation_fixed.py      ⭐ Blue Guardian测试
```

### 📂 子目录
- **strategies/** - 交易策略
  - `trend_filter_strategy_v1.py` - 趋势过滤突破策略v1.0（生产版本）

- **indicators/** - 技术指标
  - `trend_filter_fsm.py` - 趋势过滤状态机
  - `breakout_validator.py` - 突破验证器
  - `adx_indicator.py` - ADX趋势强度指标
  - `atr_buffer.py` - ATR动态止损
  - `state_machine.py` - 基础状态机

- **utils/** - 工具库
  - `forex_commission.py` - Forex盈亏计算修复（ForexCommissionInfo）
  - `data_loader.py` - 数据加载工具
  - `data_fetcher.py` - OANDA数据获取
  - `analyzers.py` - 回测分析器

- **tools/** - 数据工具
  - `download_data.py` - 通用数据下载脚本
  - `download_oanda.py` - OANDA数据下载
  - `download_multi_symbols.py` - 多品种数据批量下载
  - `convert_histdata.py` - HistData格式转换

- **tests/** - 单元测试（预留）

- **data/** - 历史数据（.gitignore，不提交）
  - `*.csv` - 价格数据文件  
  - `.gitkeep` - 保持目录结构

---

## 🚀 快速开始

### 1. 下载数据
```bash
# 下载单个品种
python tools/download_data.py

# 批量下载多个品种
python tools/download_multi_symbols.py
```

### 2. 运行回测
```bash
# 单品种回测
python run_trend_filter_backtest.py --symbol GBPUSD --risk 1.0

# 双品种组合（推荐）
python multi_symbol_test.py

# Blue Guardian完整测试
python test_risk_allocation_fixed.py --symbols GBPUSD,USDJPY --risk 1.0
```

### 3. 配置OANDA
```bash
# 复制模板
cp oanda_config_template.py oanda_config.py

# 编辑配置文件，填入API密钥
# 注意：oanda_config.py已在.gitignore中，不会被提交
```

---

## 📊 历史文件归档

已归档的文件位于 `../archive/backtest/`：
- `debug/` - 调试脚本（14个文件）
- `old_tests/` - 旧版测试和策略（15个文件）

---

## 📝 版本
- **v1.0.0** - 生产就绪版本
- **最后更新**: 2026-02-16
