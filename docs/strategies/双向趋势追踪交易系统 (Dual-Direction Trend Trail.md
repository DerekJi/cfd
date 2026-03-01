# 双向趋势追踪交易系统 (Dual-Direction Trend Trailing System)

## 1. 策略概览

本策略是一个基于 **EMA 穿越**、**分形支撑/阻力**以及**动态追踪止损**的 CFD 交易系统 。它通过识别短期均线对长期趋势的回归与突破，并结合成交量验证来捕捉动量转折点 。

## 2. 核心参数设置

* **快线 (Fast EMA)**: 5 周期 
* **慢线 (Slow EMA)**: 20 周期 
* **基线 (Base EMA)**: 200 周期 (用于过滤大趋势方向) 
* **成交量均线**: 10 周期 (默认倍数 1.1) 
* **ATR 周期**: 14 周期 (用于波动率补偿与止损计算) 

## 3. 入场逻辑

系统采用“组合 K 线”逻辑，将当前 K 线与前一根 K 线合并视为一个整体（Merged Candle） 。

### 多头入场 (Long)

* **趋势条件**: 均线组（EMA5 和 EMA20）必须运行在基线 EMA200 之上 。
* **穿越条件**: 组合 K 线的收盘价高于 EMA5 和 EMA20 的最大值，且其最低价低于这两者的最小值 。
* **形态条件**: 组合 K 线为阳线（收盘价 > 开盘价） 。
* **过滤条件**: 若开启成交量检测，当前成交量需大于成交量均线的 1.1 倍 。
* **初始止损**: 设置为“最近的分形低点”减去 0.5 倍 ATR 。

### 空头入场 (Short)

* **趋势条件**: 均线组（EMA5 和 EMA20）必须运行在基线 EMA200 之下 。
* **穿越条件**: 组合 K 线的收盘价低于 EMA5 和 EMA20 的最小值，且其最高价高于这两者的最大值 。
* **形态条件**: 组合 K 线为阴线（收盘价 < 开盘价） 。
* **过滤条件**: 满足成交量倍数要求 。
* **初始止损**: 设置为“最近的分形高点”加上 0.5 倍 ATR 。

---

## 4. 动态止损与持仓管理

策略将止损管理分为两个核心阶段：

### 阶段一：保本探测 (Breakeven)

* **触发条件**: 当价格向盈利方向波动，且浮盈超过入场时的 1.0 倍 ATR 时 。
* **动作**: 将止损位移至“入场价 + 利润缓冲（0.1 * ATR）” 。此步骤旨在抵消点差并确保订单进入无风险状态。

### 阶段二：趋势护航 (Trailing)

当订单已经完成保本后，止损位将按以下逻辑动态更新：

* **多头追踪**: 止损位取“当前止损”、“EMA20 - 0.5 * ATR”以及“价格回撤追踪”三者的最大值 。
* **空头追踪**: 止损位取“当前止损”、“EMA20 + 0.5 * ATR”以及“价格回撤追踪”三者的最小值 。
* **更新规则**: 只有当计算出的新止损位比旧止损位更优时（且超过最小变动阈值），才会执行修改指令 。

---

## 5. 策略伪代码 (系统实现版)

```csharp
// 基于 Pine Script 逻辑的 C# 伪代码实现

config = {
    checkVolume: false,
    volMult: 1.1,
    fastLen: 5,
    slowLen: 20,
    baseLen: 200,
    atrLen: 14
}

Function OnBarUpdate() {
    // 指标计算
    ema5 = EMA(fastLen);
    ema20 = EMA(slowLen);
    ema200 = EMA(baseLen);
    atr = ATR(atrLen);
    
    // 组合 K 线逻辑 (Merged Candle)
    mergedLow = Min(Low[0], Low[1]);
    mergedHigh = Max(High[0], High[1]);
    mergedOpen = Open[1];
    mergedClose = Close[0];
    
    // EMA 边界计算
    lowerEma = Min(ema5[0], ema20[0], ema5[1], ema20[1]);
    upperEma = Max(ema5[0], ema20[0], ema5[1], ema20[1]);
    
    volCond = !config.checkVolume || (Volume[0] > SMA(Volume, 10) * config.volMult);

    // 多头信号检测
    if (position == null && lowerEma > ema200 && mergedClose > upperEma && mergedLow < lowerEma && mergedClose > mergedOpen && volCond) {
        if (latestFractalLow != null) {
            position.entry = mergedClose;
            position.stopLoss = latestFractalLow - 0.5 * atr;
            position.trailingDist = position.entry - position.stopLoss;
            position.atrAtEntry = atr;
            OpenLong();
        }
    }

    // 空头信号检测
    if (position == null && upperEma < ema200 && mergedClose < lowerEma && mergedHigh > upperEma && mergedClose < mergedOpen && volCond) {
        if (latestFractalHigh != null) {
            position.entry = mergedClose;
            position.stopLoss = latestFractalHigh + 0.5 * atr;
            position.trailingDist = position.stopLoss - position.entry;
            position.atrAtEntry = atr;
            OpenShort();
        }
    }
}

Function UpdateTrailingStopOnTick() {
    if (position == null) return;

    currentBid = Symbol.Bid;
    currentAsk = Symbol.Ask;
    spread = | currentAsk - currentBid |;

    if (position.IsLong) { // 多单逻辑
        isSafe = position.stopLoss >= position.entry;
        newSL = position.stopLoss;

        if (!isSafe) {
            // 浮盈达标，移动至保本位
            if (currentBid - position.entry >= position.atrAtEntry) {
                newSL = position.entry + spread + (0.1 * position.atrAtEntry);
            }
        } else {
            // 综合 EMA 保护和固定间距追踪
            targetSL = Max(ema20 - (0.5 * atr), currentBid - position.trailingDist);
            if (targetSL > position.stopLoss) newSL = targetSL;
        }
        
        if (newSL > position.stopLoss + (Symbol.Point * 5)) ModifySL(newSL);
    } 
    else { // 空单逻辑
        isSafe = position.stopLoss <= position.entry;
        newSL = position.stopLoss;

        if (!isSafe) {
            // 浮盈达标，移动至保本位
            if (position.entry - currentAsk >= position.atrAtEntry) {
                newSL = position.entry - spread - (0.1 * position.atrAtEntry);
            }
        } else {
            targetSL = Min(ema20 + (0.5 * atr), currentAsk + position.trailingDist);
            if (targetSL < position.stopLoss) newSL = targetSL;
        }

        if (newSL < position.stopLoss - (Symbol.Point * 5)) ModifySL(newSL);
    }
}

```