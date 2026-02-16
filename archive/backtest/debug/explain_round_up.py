#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解释"强制Round up"机制

问题：103 units是多少手？被谁强制Round up到1000 units？
"""

print("="*80)
print("外汇手数换算标准")
print("="*80)
print("1 标准手 (Standard Lot) = 100,000 基础货币单位")
print("1 迷你手 (Mini Lot)     = 10,000 基础货币单位 = 0.1 标准手")
print("1 微型手 (Micro Lot)    = 1,000 基础货币单位 = 0.01 标准手")
print("1 纳米手 (Nano Lot)     = 100 基础货币单位 = 0.001 标准手")
print()

print("="*80)
print("USDJPY案例计算")
print("="*80)

# 实际参数
risk_amount = 20.0
stop_distance = 0.19362
entry_price = 141.842

print(f"风险金额: ${risk_amount:.2f}")
print(f"止损距离: {stop_distance:.5f} JPY")
print()

# 第1步：理论仓位计算
print("第1步：理论仓位计算（考虑3倍滑点保护）")
SLIPPAGE_PROTECTION = 3.0
theoretical_size = risk_amount / (stop_distance * SLIPPAGE_PROTECTION)
print(f"  size = {risk_amount} / ({stop_distance} × 3.0)")
print(f"  size = {theoretical_size:.2f} units")
print()

# 第2步：转换为手数
print("第2步：转换为手数")
theoretical_lots = theoretical_size / 100000
print(f"  lots = {theoretical_size:.2f} / 100,000")
print(f"  lots = {theoretical_lots:.6f} 标准手")
print()

# 换算为其他单位
print("  换算:")
print(f"    = {theoretical_lots * 10:.5f} 迷你手 (Mini Lot)")
print(f"    = {theoretical_lots * 100:.4f} 微型手 (Micro Lot)")
print(f"    = {theoretical_lots * 1000:.3f} 纳米手 (Nano Lot)")
print()

# 第3步：⚠️ 强制限制！
print("第3步：策略参数强制限制")
print("  代码位置: trend_filter_strategy_v1.py L414")
print("  关键代码:")
print("    lots = max(self.params.min_lot, min(lots, self.params.max_lot))")
print()

min_lot = 0.01  # 策略参数
max_lot = 10.0  # 策略参数

print(f"  参数设置:")
print(f"    min_lot = {min_lot} (最小0.01标准手)")
print(f"    max_lot = {max_lot} (最大10标准手)")
print()

actual_lots = max(min_lot, min(theoretical_lots, max_lot))
print(f"  执行:")
print(f"    lots = max({min_lot}, min({theoretical_lots:.6f}, {max_lot}))")
print(f"    lots = max({min_lot}, {theoretical_lots:.6f})")
print(f"    lots = {actual_lots} 标准手  ← ⚠️ 被强制提升！")
print()

# 第4步：最终仓位
print("第4步：最终仓位")
actual_size = actual_lots * 100000
print(f"  size = {actual_lots} × 100,000")
print(f"  size = {actual_size:.0f} units")
print()

# 对比
print("="*80)
print("对比分析")
print("="*80)
print(f"理论仓位: {theoretical_size:.2f} units ({theoretical_lots:.6f} 标准手)")
print(f"实际仓位: {actual_size:.0f} units ({actual_lots:.2f} 标准手)")
print(f"放大倍数: {actual_size / theoretical_size:.1f}x")
print()

# 风险对比
theoretical_risk = theoretical_size * stop_distance * SLIPPAGE_PROTECTION
actual_risk = actual_size * stop_distance * SLIPPAGE_PROTECTION

print(f"理论风险: ${theoretical_risk:.2f}")
print(f"实际风险: ${actual_risk:.2f}")
print(f"风险放大: {actual_risk / theoretical_risk:.1f}x")
print()

# 实际发生的滑点
actual_exit = 142.456
actual_move = actual_exit - entry_price
actual_loss = actual_size * actual_move

print("="*80)
print("实际交易结果 (2025-04-16)")
print("="*80)
print(f"入场价: {entry_price:.3f}")
print(f"止损价: {entry_price + stop_distance:.3f}")
print(f"实际平仓: {actual_exit:.3f}")
print(f"实际滑点: {actual_move:.3f} JPY ({actual_move/stop_distance:.2f}倍止损距离)")
print(f"实际亏损: ${actual_loss:.2f}")
print(f"理论亏损: ${risk_amount:.2f}")
print(f"亏损放大: {actual_loss / risk_amount:.1f}x")
print()

print("="*80)
print("结论")
print("="*80)
print("【被谁强制？】")
print("  → 策略参数 min_lot=0.01 (trend_filter_strategy_v1.py L51)")
print("  → 代码逻辑 max(0.01, theoretical_lots) (L414)")
print()
print("【为什么要限制？】")
print("  1. backtrader框架限制")
print("  2. 真实broker最小手数限制（通常0.01标准手）")
print("  3. 技术原因：太小的仓位无法执行")
print()
print("【问题根源】")
print("  当理论仓位 < 1000 units (0.01标准手)时")
print("  强制Round up导致实际风险 >> 理论风险")
print("  → 解决方案：跳过这种高风险交易（Bug #7修复）")
print("="*80)
