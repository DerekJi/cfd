#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证滑点保护修复的效果"""

# 验证修改后的仓位计算
risk_amount = 20.0  # (5000 * 0.8% / 2 symbols)
stop_distance = 0.19362  # 实际止损距离

print("="*80)
print("滑点保护修复验证")
print("="*80)
print()

# 原仓位计算（bug版本）
old_size = risk_amount / stop_distance
old_lots = old_size / 100000
old_lots_final = max(0.01, old_lots)
old_size_final = old_lots_final * 100000

print('原计算（无滑点保护）:')
print(f'  理论仓位: {old_size:.2f} units')
print(f'  手数: {old_lots:.5f} → {old_lots_final:.2f} (最小0.01)')
print(f'  最终仓位: {old_size_final:.0f} units')
print(f'  理论最大亏损: ${old_size_final * stop_distance:.2f}')
print()

# 新仓位计算（添加3倍滑点保护）
SLIPPAGE_PROTECTION = 3.0
new_size = risk_amount / (stop_distance * SLIPPAGE_PROTECTION)
new_lots = new_size / 100000
new_lots_final = max(0.01, new_lots)
new_size_final = new_lots_final * 100000

print('新计算（3倍滑点保护）:')
print(f'  理论仓位: {new_size:.2f} units')
print(f'  手数: {new_lots:.5f} → {new_lots_final:.2f} (最小0.01)')
print(f'  最终仓位: {new_size_final:.0f} units')
print(f'  保守最大亏损（3倍距离）: ${new_size_final * stop_distance * 3:.2f}')
print()

# 实际滑点情况（2025-04-17 00:00 K线）
actual_move = 142.456 - 141.842
print('实际滑点情况 (2025-04-16交易):')
print(f'  入场价: 141.842')
print(f'  止损价: 142.040')
print(f'  平仓价: 142.456 (K线收盘价)')
print(f'  价格波动: {actual_move:.3f} 日元')
print(f'  理论止损距离: {stop_distance:.3f} 日元')
print(f'  实际滑点倍数: {actual_move / stop_distance:.2f}x')
print()

print('亏损对比:')
print(f'  原仓位({old_size_final:.0f} units)的亏损: ${old_size_final * actual_move:.2f}  ← 实际发生')
print(f'  新仓位({new_size_final:.0f} units)的亏损: ${new_size_final * actual_move:.2f}  ← 修复后')
print()

reduction_percent = (1 - new_size_final / old_size_final) * 100
print(f'仓位缩减: {reduction_percent:.1f}%')
print(f'风险降低: ${old_size_final * actual_move - new_size_final * actual_move:.2f}')
print()

print("结论:")
if new_size_final * actual_move <= 50:
    print(f"  ✅ 修复后风险${new_size_final * actual_move:.2f} ≤ $50 (Blue Guardian限制)")
else:
    print(f"  ❌ 修复后风险${new_size_final * actual_move:.2f} > $50 (仍超限！)")
    
print("="*80)
