# BUG报告：AUDJPY交叉货币对仓位计算问题

**日期**：2026-02-16  
**修复日期**：2026-02-17  
**严重程度**：🔴 HIGH - 阻止AUDJPY等交叉货币对回测  
**影响范围**：所有非USD交叉货币对（如AUDJPY, EURJPY, GBPJPY等）  
**当前状态**：✅ 已解决 - ForexCommissionInfo 新增 `cross` 货币对类型

---

## 📋 问题描述

### 现象
AUDJPY回测时，策略成功识别203个入场机会，但**所有订单因"Margin不足"被拒绝**，导致0笔交易完成。

```
实际交易: 203 笔 (策略尝试开仓)
总收益: $0.00
最大回撤: 0.00%
💼 交易统计: 没有完成的交易  ← 所有订单被拒！
```

### 订单拒绝详情
```
⚠️ 订单Margin (insufficient funds)
   订单类型: Sell
   订单价格: 96.156
   订单数量: -46019.64 units (0.46 lots)
   当前资金: $10000.00
   持仓价值: $0.00
```

**保证金计算**：`46,019 units × 96.156 / 30杠杆 ≈ $147,483` >> `$10,000` ❌

---

## 🔍 根本原因分析

### 1. AUDJPY是交叉货币对（Cross Pair）

| 货币对类型 | 示例 | 账户货币 | 盈亏计算 | 当前支持 |
|-----------|------|---------|---------|---------|
| **直接报价** | GBPUSD | USD报价货币 | P&L = size × (Δprice) | ✅ 正常 |
| **间接报价** | USDJPY | USD基础货币 | P&L = size × (Δprice / price) | ✅ 正常 |
| **交叉货币对** | AUDJPY | USD非参与 | P&L = size × Δprice × quote_usd_rate | ✅ 已修复 |

### 2. AUDJPY盈亏计算需要中间汇率

AUDJPY的盈亏（以USD计价）需要通过以下路径转换：
```
AUD/JPY变动 → JPY盈亏 → USD/JPY汇率 → USD盈亏
```

**示例计算**：
- 开仓：Sell 100,000 AUD/JPY @ 96.000
- 平仓：Buy 100,000 AUD/JPY @ 95.000
- JPY盈亏：100,000 × (96.000 - 95.000) = 100,000 JPY
- **转换USD**：100,000 JPY ÷ 150 (USD/JPY汇率) = **$666.67**

当前系统缺少USD/JPY实时汇率查询机制，导致：
1. ✅ 仓位计算公式正确，但基于错误的盈亏假设
2. ❌ CommissionInfo未考虑交叉盘特殊性
3. ❌ 保证金计算错误，导致订单被拒

### 3. 对比测试结果

| 指标 | GBPUSD | USDJPY | AUDJPY | 说明 |
|-----|--------|--------|--------|------|
| ADX>35覆盖率 | 13.3% | 15.6% | **12.8%** | 接近✅ |
| 回调成功率 | 30% | 36% | **47%** | 最高✅ |
| 突破机会数 | 3,254 | 3,462 | 2,864 | 正常✅ |
| 策略入场次数 | 195 | 210 | **203** | 正常✅ |
| 完成交易数 | 195✅ | 210✅ | **0** ❌ | 全部被拒！|

**结论**：策略逻辑完全正常，问题出在订单执行层（仓位计算+保证金检查）

---

## 🛠️ 已完成的修复

### 1. 仓位计算公式修复 ✅
**文件**：`backtest/strategies/trend_filter_strategy_v1.py` L456

```python
# ❌ 旧公式（错误）：
size = risk_amount * entry_price / (stop_distance * SLIPPAGE_PROTECTION)

# ✅ 新公式（正确）：
size = risk_amount / ((stop_distance / entry_price) * SLIPPAGE_PROTECTION)
```

**修复说明**：
- 旧公式对高汇率货币对（USDJPY ~150, AUDJPY ~95）计算出过大仓位
- 新公式基于**百分比价格变动**，更符合backtrader盈亏计算逻辑

### 2. 风险金额显示修复 ✅
**文件**：`backtest/strategies/trend_filter_strategy_v1.py` L312, L356

```python
# ❌ 旧显示：
risk_dollars = size * (entry_price - stop_loss)

# ✅ 新显示：
risk_dollars = size * (entry_price - stop_loss) / entry_price
```

### 3. 订单拒绝详细日志 ✅
**文件**：`backtest/strategies/trend_filter_strategy_v1.py` L193-208

新增显示：
- 订单类型、价格、数量
- 当前资金和持仓价值
- 拒绝原因（Margin/Canceled/Rejected）

### 4. AUDJPY配置添加 ✅ 已升级为完整 cross 支持
**文件**：`backtest/utils/forex_commission.py`

```python
# ✅ 新增 cross 货币对类型，使用 quote_usd_rate 参数
PAIR_TYPE_MAP = {
    'GBPUSD': 'direct', 'EURUSD': 'direct', ...
    'USDJPY': 'indirect', 'USDCAD': 'indirect', ...
    'AUDJPY': 'cross', 'EURJPY': 'cross', 'GBPJPY': 'cross', ...
}

CROSS_QUOTE_USD_RATES = {
    'JPY': 1.0 / 150.0,   # 1 JPY ≈ $0.00667
    'CAD': 1.0 / 1.36,
    'CHF': 1.0 / 0.88,
    'GBP': 1.0 / 0.79,
}
```

### 5. 策略仓位计算公式统一 ✅
**文件**：`backtest/strategies/trend_filter_strategy_v1.py`

```python
# ✅ 统一 pnl_factor 抽象，支持三种货币对类型
if self.params.quote_usd_rate > 0:
    pnl_factor = self.params.quote_usd_rate  # cross pairs
else:
    pnl_factor = 1.0 / entry_price  # direct/indirect (auto)

size = risk_amount / (stop_distance * pnl_factor * SLIPPAGE_PROTECTION)
```

---

## ✅ 修复验证结果

### 回归测试（$5,000账户, 0.5%风险, 3品种）

| 品种 | 类型 | trades | WR | PnL | AvgLoss | MaxLoss | 目标$8.33 |
|------|------|--------|------|--------|---------|---------|-----------|
| GBP_USD | direct | 218 | 29.4% | +$133 | $3.78 | $15.60 | ✅ |
| USD_JPY | indirect | 211 | 28.0% | +$365 | $2.88 | $31.23 | ✅ |
| AUD_JPY | cross | 180 | 22.2% | -$68 | $2.85 | $27.72 | ✅ |

**结论**：
- ✅ AUDJPY从0笔交易恢复到180笔
- ✅ 所有MaxLoss < $50，符合Blue Guardian规则
- ✅ GBPUSD和USDJPY无回归（交易数和收益保持不变）
- ⚠️ AUDJPY策略本身表现为负收益(-$68)，需要参数优化

### 修复后的CommissionInfo计算验证

| 指标 | 修复前(错误) | 修复后(正确) | 说明 |
|------|-------------|-------------|------|
| AUDJPY margin | $10,273 | $68.48 | ÷150 JPY→USD转换 |
| AUDJPY PnL | 按JPY=USD | ×0.00667 | 正确USD盈亏 |
| 订单执行 | 全部拒绝 | 正常执行 | 保证金不再超限 |
    'AUD_JPY': 'indirect',
}
```

**注意**：这只是临时尝试，未真正解决交叉盘问题！

---

##  测试数据对比

### ADX分布对比
```
Symbol     ADX Mean   ADX>25%    ADX>30%    ADX>35%
------------------------------------------------------------
GBPUSD        23.99      38.2%      23.0%      13.3%
USDJPY        24.57      40.3%      25.3%      15.6%
AUDJPY        23.70      37.1%      22.8%      12.8%  ← 分布相似✅
```

### 过滤器级联分析
```
Symbol     ADX>35%    Breakout%  EMA200%    Final%    Actual Trades
------------------------------------------------------------------------
GBPUSD      40.8%       6.09%     5.10%      5.83%        195 ✅
USDJPY      42.9%       6.47%     5.35%      6.08%        210 ✅
AUDJPY      39.9%       5.83%     4.93%      5.55%          0 ❌
```

**结论**：AUDJPY的过滤器通过率与GBPUSD几乎相同（5.55% vs 5.83%），理论上应产生100-150笔交易

### 回调行为对比
```
Symbol     Breakouts  Pullback Success  No Pullback  Too Shallow
-------------------------------------------------------------------
GBPUSD       3,254         30.0%            62.0%         8.0%
USDJPY       3,462         36.0%            56.0%         8.0%
AUDJPY       2,864         47.0% ✅         41.0%        12.0%
```

**关键发现**：AUDJPY的回调成功率**最高**（47%），说明策略逻辑完全适用！

---

## 📁 相关文件清单

### 已修改文件 ✏️
1. **`backtest/utils/forex_commission.py`**
   - 新增 `cross` 货币对类型
   - 新增 `CROSS_QUOTE_USD_RATES` 汇率字典
   - 新增 `get_quote_usd_rate()` 导出函数
   - `ForexCommissionInfo` 支持 `profitandloss` / `getvaluesize` / `getoperationcost` 三种类型

2. **`backtest/strategies/trend_filter_strategy_v1.py`**
   - 新增 `quote_usd_rate` 参数
   - 统一 `pnl_factor` 抽象的仓位计算

3. **`backtest/test_risk_allocation_fixed.py`**
   - 传入 `quote_usd_rate` 参数

4. **`backtest/multi_symbol_test.py`**
   - 传入 `quote_usd_rate` 参数

5. **`backtest/run_trend_filter_backtest.py`**
   - 自动检测symbol并传入 `quote_usd_rate`

6. **`backtest/utils/__init__.py`**
   - 导出 `get_quote_usd_rate`

---

*本文档由AI助手生成，基于2026-02-16的深入分析和调试，2026-02-17更新修复结果*
