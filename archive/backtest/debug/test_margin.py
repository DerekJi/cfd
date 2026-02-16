"""
快速测试USDJPY仓位计算
"""

# 测试配置
entry = 155.110
stop = 155.122
stop_dist = 0.012
risk_usd = 20.0  # 0.8% / 2品种
slippage = 3.0

print("=== 理论仓位计算 ===")
size_usd = risk_usd * entry / (stop_dist * slippage)
size_lots = size_usd / 100000

print(f"入场: {entry:.3f}")
print(f"止损: {stop:.3f}")
print(f"止损距离: {stop_dist:.4f} JPY ({stop_dist/entry*100:.2f}%)")
print(f"风险金额: ${risk_usd:.2f}")
print(f"滑点系数: {slippage}x")
print()
print(f"理论仓位 = ${risk_usd} × {entry:.3f} / ({stop_dist:.4f} × {slippage})")
print(f"         = {size_usd:.0f} USD")
print(f"         = {size_lots:.4f} 手")
print()

# 保证金计算
margin_rate = 0.0333  # 3.33%
leverage = 30
required_margin = size_usd * margin_rate

print(f"=== 保证金需求 ===")
print(f"名义价值: ${size_usd:.0f}")
print(f"杠杆: {leverage}:1")
print(f"保证金率: {margin_rate*100:.2f}%")
print(f"所需保证金: ${required_margin:.2f}")
print()

# 检查账户资金
account_balance = 2478.50  # 双品种各一半
print(f"=== 资金检查 ===")
print(f"账户余额: ${account_balance:.2f}")
print(f"所需保证金: ${required_margin:.2f}")
print(f"保证金占用: {required_margin/account_balance*100:.1f}%")

if required_margin > account_balance:
    print(f"❌ 保证金不足！需要${required_margin:.2f}，只有${account_balance:.2f}")
    max_size = account_balance / margin_rate
    max_lots = max_size / 100000
    print(f"   最大仓位: {max_size:.0f} USD = {max_lots:.4f} 手")
else:
    print(f"✅ 保证金充足，可以开{size_lots:.4f}手")

print()
print(f"=== 验证止损风险 ===")
actual_loss = size_usd * (stop_dist * slippage) / entry
print(f"亏损 = {size_usd:.0f} × {stop_dist * slippage:.4f} / {entry:.3f}")
print(f"     = ${actual_loss:.2f}")
print(f"目标风险: ${risk_usd:.2f}")
print(f"误差: {abs(actual_loss - risk_usd):.2f}")
