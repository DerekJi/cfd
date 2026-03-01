#!/bin/bash

# 定义品种列表
SYMBOLS="XAUUSD XAGUSD"
# SYMBOLS="GBPUSD EURUSD USDJPY AUDJPY XAUUSD XAGUSD"

echo "--- 开始回测任务 ---"

for s in $SYMBOLS; do
    # 打印品种名，不换行
    printf "%-10s: " "$s"
    
    # 执行 Python 脚本并过滤结果
    # 使用 grep --color=never 确保在某些终端下输出纯文本
    python backtest/run_dual_direction_backtest.py --symbol "$s" --no-debug
done

echo "--- 回测结束 ---"