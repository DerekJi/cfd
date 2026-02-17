# CFD 实盘交易系统

自动化趋势过滤交易策略的 Python 实盘系统，支持 Oanda 平台，部署在 Azure Functions。

---

## 🎯 最新更新

### v1.0.3 (2026-02-18) - 🔥 紧急修复
**平仓逻辑修复** - 解决实盘环境中大量平仓失败的问题

**⚠️ 必须立即执行**：
1. 运行状态修复工具：`python -m live.fix_state --profile oanda_demo`
2. 重新部署 Azure Function
3. 验证日志中有 "持仓同步" 信息

📖 详细说明：[平仓逻辑修复-快速指南](docs/平仓逻辑修复-快速指南.md)

---

## 📋 版本历史

- **v1.0.3** (2026-02-18): 平仓逻辑修复，增加持仓同步机制 [详情](RELEASE_NOTES_v1.0.3.md)
- **v1.0.2** (2026-02-17): 多品种测试优化 [详情](archive/docs/多品种测试对比报告_v1.0.2.md)
- **v1.0.1** (2026-02-16): AUDJPY 仓位计算修复 [详情](archive/docs/BUG报告-AUDJPY交叉货币对仓位计算问题.md)
- **v1.0.0** (2026-02-15): 首个生产版本 [详情](RELEASE_NOTES_v1.0.0.md)

---

## 🏗️ 系统架构

```
实盘系统
├── live/                    # 实盘引擎
│   ├── engine.py           # 核心策略引擎
│   ├── cli.py              # 本地命令行工具
│   ├── fix_state.py        # 状态修复工具 (v1.0.3新增)
│   └── azure_function/     # Azure Functions部署
├── core/                    # 核心逻辑（回测和实盘共用）
│   ├── fsm.py              # 趋势过滤状态机
│   ├── indicators.py       # 技术指标
│   ├── position_sizer.py   # 仓位计算
│   └── risk_manager.py     # 风险管理
├── execution/               # 交易执行
│   ├── oanda_executor.py   # Oanda API集成
│   └── base.py             # 执行器基类
├── storage/                 # 状态存储
│   ├── azure_table.py      # Azure Table Storage
│   └── local_json.py       # 本地JSON存储
├── data/                    # 数据获取
│   └── oanda_candles.py    # Oanda K线数据
└── notification/            # 通知
    └── telegram.py          # Telegram机器人
```

---

## 🚀 快速开始

### 1. 环境准备

```bash
cd d:\source\cfd

# 安装依赖
pip install -r backtest/requirements.txt

# 配置环境变量
dcqSetSecrets default
```

### 2. 本地测试

```bash
# DRY_RUN 模式（不执行真实交易）
cd live
CFD_DRY_RUN=true python -m cli tick --profile oanda_demo

# 检查持仓状态
python -m fix_state --profile oanda_demo --dry-run
```

### 3. Azure 部署

```bash
# 部署到 Azure Functions
func azure functionapp publish <your-function-app-name>

# 查看日志
func azure functionapp logstream <your-function-app-name>
```

---

## 📚 核心文档

### 使用指南
- [实盘交易系统技术分析与实施计划](docs/实盘交易系统技术分析与实施计划.md)
- [Python回测系统使用说明](docs/Python回测系统使用说明.md)
- [OANDA配置指南](docs/OANDA配置指南.md)
- [多品种测试指南](docs/多品种测试指南.md)

### 维护工具
- [平仓逻辑修复-快速指南](docs/平仓逻辑修复-快速指南.md) ⚠️ v1.0.3必读
- [平仓逻辑修复说明](docs/平仓逻辑修复说明.md) - 详细分析

### 数据获取
- [数据获取指南](docs/数据获取指南.md)
- [真实数据快速入门](docs/真实数据快速入门.md)

---

## 🔧 配置说明

### Profile 配置

```python
# config/profiles.py
ProfileConfig(
    profile_name="oanda_demo",           # Profile名称
    account_size=10000,                  # 账户规模
    risk_per_trade_pct=1.0,             # 单笔交易风险（账户的%）
    
    # 执行器配置
    oanda_api_key="xxx",                 # Oanda API Key
    oanda_account_id="xxx",              # Oanda Account ID
    oanda_environment="practice",        # practice 或 live
    
    # 品种配置
    symbols=[
        SymbolConfig("EUR_USD", 1.12, 0.0001, 100000),
        SymbolConfig("GBP_USD", 1.28, 0.0001, 100000),
        # ...
    ],
    
    # 通知配置
    enable_telegram=True,
    telegram_bot_token="xxx",
    telegram_chat_id="xxx",
)
```

---

## ⚙️ 策略参数

### 趋势过滤策略
- **UP/DOWN 线周期**: 20
- **EMA 周期**: 50, 200
- **ADX 阈值**: 25
- **回踩等待**: 最多 20 根K线

### 风险管理
- **单笔风险**: 1% 账户
- **最大持仓**: 3个品种
- **止损方式**: 服务端挂单（开仓时自动设置）
- **移动止损**: EMA50 动态追踪

---

## 🛠️ 维护工具

### 状态修复工具 (v1.0.3新增)

修复 Storage 和 FSM 状态不一致的问题：

```bash
# 检查状态
python -m live.fix_state --profile oanda_demo --dry-run

# 执行修复
python -m live.fix_state --profile oanda_demo
```

**使用场景**：
- 平台自动止损/止盈后的状态同步
- 手动开仓/平仓后的记录清理
- 故障恢复后的一致性检查

---

## 📊 监控与日志

### Azure Functions 日志

```bash
# 实时日志流
func azure functionapp logstream <your-function-app-name>

# Azure Portal
Function App → Monitor → Logs
```

### 关键日志

**正常执行**：
```
[INFO] 持仓同步开始: 实盘持仓 1 个
[INFO] EUR_USD bar=2026-02-18T10:05:00Z close=1.08500 ADX=28.5 ATR=0.00125
[INFO] 持仓同步完成
```

**异常情况**：
```
[WARNING] EUR_USD: 检测到持仓 12345 已被平台自动平仓（止损/止盈），清理Storage记录并重置FSM状态
[ERROR] EUR_USD: 实盘有持仓但Storage无记录！建议人工检查
```

---

## 🧪 测试

### 回测系统

```bash
cd backtest

# 单品种回测
python run_trend_filter_backtest.py

# 多品种回测
python multi_symbol_test.py
```

### 本地集成测试

```bash
cd live

# 模拟一次tick
CFD_DRY_RUN=true python -m cli tick --profile oanda_demo

# 查看结果
cat ../logs/live_engine.log
```

---

## ⚠️ 重要提醒

### v1.0.3 升级必读
1. ✅ **必须运行状态修复工具** - 清理不一致的FSM状态
2. ✅ **必须重新部署** - 应用新的持仓同步逻辑
3. ✅ **验证日志** - 确认"持仓同步"功能正常

### 日常运维
- 每日检查 Azure Functions 执行日志
- 定期运行状态修复工具（建议每周）
- 监控 Telegram 通知，异常时及时处理
- 备份 Azure Table Storage 数据

---

## 🐛 已知问题

### v1.0.3 已修复
- ✅ 平仓失败（重复平仓已被平台自动平掉的持仓）
- ✅ FSM 状态不同步（平台平仓后代码状态未更新）
- ✅ 无法开新仓（FSM 卡在 POSITION 状态）

### 待优化
- [ ] 增加健康检查 HTTP endpoint
- [ ] 定期自动状态校验
- [ ] 增强异常告警

---

## 📞 支持与反馈

遇到问题时：
1. 查看 [平仓逻辑修复-快速指南](docs/平仓逻辑修复-快速指南.md)
2. 检查 Azure Functions 日志
3. 运行 `fix_state.py --dry-run` 检查状态
4. 查看 [Release Notes](RELEASE_NOTES_v1.0.3.md)

---

## 📜 免责声明

本系统仅供学习和研究使用，不构成投资建议。交易有风险，投资需谨慎。

---

**当前版本**: v1.0.3  
**最后更新**: 2026-02-18  
**开发语言**: Python 3.11+  
**部署平台**: Azure Functions (Python)
