#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试市场开盘时段过滤功能
"""

from datetime import datetime, timedelta

def is_market_open_session(dt):
    """
    检查当前时间是否在市场开盘高波动时段（禁止交易）
    
    悉尼开盘: 07:00 Sydney = 21:00 UTC (标准时间) 或 20:00 UTC (夏令时)
    东京开盘: 09:00 Tokyo = 00:00 UTC
    
    禁止交易窗口：开盘前后15分钟
    """
    # 获取UTC时间的小时和分钟
    hour = dt.hour
    minute = dt.minute
    time_minutes = hour * 60 + minute  # 转换为分钟数（0-1439）
    
    # 东京开盘时段: 00:00 UTC (23:45-00:15)
    tokyo_open = 0  # 00:00的分钟数
    if (time_minutes >= tokyo_open - 15 and time_minutes <= tokyo_open + 15) or \
       (time_minutes >= 1440 - 15):  # 跨日情况：23:45-23:59
        return True, "东京开盘"
    
    # 悉尼开盘时段: 21:00 UTC 标准时间 (20:45-21:15)
    # 简化处理：全年使用21:00（实际需根据夏令时调整）
    sydney_open = 21 * 60  # 21:00的分钟数 = 1260
    if time_minutes >= sydney_open - 15 and time_minutes <= sydney_open + 15:
        return True, "悉尼开盘"
    
    return False, None

print("="*80)
print("市场开盘时段过滤测试")
print("="*80)
print()

# 测试案例
test_cases = [
    # 东京开盘时段
    datetime(2025, 4, 16, 23, 44),  # 东京开盘前16分钟 - 允许
    datetime(2025, 4, 16, 23, 45),  # 东京开盘前15分钟 - 禁止
    datetime(2025, 4, 16, 23, 55),  # 东京开盘前5分钟 - 禁止
    datetime(2025, 4, 17, 0, 0),    # 东京开盘时刻 - 禁止 ⭐
    datetime(2025, 4, 17, 0, 10),   # 东京开盘后10分钟 - 禁止
    datetime(2025, 4, 17, 0, 15),   # 东京开盘后15分钟 - 禁止
    datetime(2025, 4, 17, 0, 16),   # 东京开盘后16分钟 - 允许
    
    # 悉尼开盘时段
    datetime(2025, 4, 16, 20, 44),  # 悉尼开盘前16分钟 - 允许
    datetime(2025, 4, 16, 20, 45),  # 悉尼开盘前15分钟 - 禁止
    datetime(2025, 4, 16, 21, 0),   # 悉尼开盘时刻 - 禁止
    datetime(2025, 4, 16, 21, 15),  # 悉尼开盘后15分钟 - 禁止
    datetime(2025, 4, 16, 21, 16),  # 悉尼开盘后16分钟 - 允许
    
    # 正常交易时段
    datetime(2025, 4, 16, 10, 0),   # 正常时段
    datetime(2025, 4, 16, 15, 30),  # 正常时段
    datetime(2025, 4, 16, 22, 55),  # ⭐ USDJPY那笔交易的入场时间 - 允许
]

print(f"{'时间 (UTC)':<25} | {'状态':<8} | 原因")
print("-" * 80)

for dt in test_cases:
    is_blocked, session = is_market_open_session(dt)
    status = "🚫 禁止" if is_blocked else "✅ 允许"
    reason = session if is_blocked else "正常交易时段"
    
    # 特别标注USDJPY交易时间
    marker = " ⭐ USDJPY入场" if dt.hour == 22 and dt.minute == 55 else ""
    marker = " ⭐ USDJPY平仓" if dt.hour == 0 and dt.minute == 0 else marker
    
    print(f"{dt.strftime('%Y-%m-%d %H:%M'):<25} | {status:<8} | {reason}{marker}")

print()
print("="*80)
print("关键发现")
print("="*80)
print("✅ USDJPY入场时间 (22:55 UTC) 不在禁止时段")
print("🚫 USDJPY平仓时间 (00:00 UTC) 在东京开盘时段 - 如果是这时想开仓会被阻止")
print()
print("时间窗口:")
print("  东京开盘禁止时段: 23:45 - 00:15 UTC (±15分钟)")
print("  悉尼开盘禁止时段: 20:45 - 21:15 UTC (±15分钟)")
print()
print("实施效果:")
print("  - 防止在亚洲市场开盘时的高波动时段开仓")
print("  - 避免类似USDJPY $614跳空亏损的情况")
print("  - 已持仓不受影响，只限制新开仓")
print("="*80)
