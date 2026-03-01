"""
Phase 4 验证脚本 — 生成 K 线图并发送到 Telegram

运行方式:
    python tests/test_phase4_chart.py

环境变量（从 .env 或系统环境中读取）:
    CFD_TELEGRAM_BOT_TOKEN
    CFD_TELEGRAM_CHAT_ID

使用 backtest/data/EUR_USD_M5.csv 中的真实数据，取最近 100 根 K 线，
叠加 EMA10 / EMA20 / EMA50，并标注最后一根 K 线为 LONG 示例。
"""

import os
import sys

# 确保项目根目录在 PYTHONPATH 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from core.indicators import ema as calc_ema
from notification.telegram import TelegramNotifier
from utils.chart_generator import generate_ema_chart


# ─── 1. 读取真实数据 ────────────────────────────────────────────────────────
DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'backtest', 'data', 'EUR_USD_M5.csv',
)

print(f"[1] 加载数据: {DATA_FILE}")
df = pd.read_csv(DATA_FILE, parse_dates=['datetime'])
df = df.sort_values('datetime').reset_index(drop=True)
print(f"    总行数: {len(df)}")

# ─── 2. 计算 EMA ────────────────────────────────────────────────────────────
print("[2] 计算 EMA10 / EMA20 / EMA50 ...")
ema10  = calc_ema(df['close'], 10)
ema20  = calc_ema(df['close'], 20)
ema50  = calc_ema(df['close'], 50)

# ─── 3. 生成图表（取最近 100 根 K 线） ────────────────────────────────────
print("[3] 生成 K 线图 ...")

N = 100
latest = df.tail(N).reset_index(drop=True)
entry_price = float(latest['close'].iloc[-1])
stop_loss   = float(latest['low'].tail(10).min()) * 0.9999  # 示例止损

# ema10/20/50 are numpy arrays aligned to df; take the last N elements
image_bytes = generate_ema_chart(
    df=latest.set_index('datetime'),
    ema_dict={
        'EMA10':  (ema10[-N:], '#89b4fa'),   # 蓝
        'EMA20':  (ema20[-N:], '#fab387'),   # 橙
        'EMA50':  (ema50[-N:], '#cba6f7'),   # 紫
    },
    title='EUR_USD · Phase4 图表验证',
    entry_price=entry_price,
    stop_loss=stop_loss,
    direction='long',
    timeframe='M5',
    n_candles=N,
)
print(f"    图表大小: {len(image_bytes):,} bytes")

# ─── 4. 发送到 Telegram ────────────────────────────────────────────────────
bot_token = os.environ.get('CFD_TELEGRAM_BOT_TOKEN', '')
chat_id   = os.environ.get('CFD_TELEGRAM_CHAT_ID', '')

if not bot_token or not chat_id:
    print("[!] 未设置 CFD_TELEGRAM_BOT_TOKEN / CFD_TELEGRAM_CHAT_ID，跳过发送")
    print("    已将图表保存到 /tmp/phase4_test_chart.png")
    with open('/tmp/phase4_test_chart.png', 'wb') as f:
        f.write(image_bytes)
    sys.exit(0)

print(f"[4] 发送到 Telegram (chat_id={chat_id}) ...")
notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)

caption = (
    "<b>✅ Phase 4 图表验证</b>\n"
    "EUR/USD · M5 · 最近 100 根 K 线\n"
    "蓝=EMA10 · 橙=EMA20 · 紫=EMA50\n"
    "绿虚线=Entry · 红虚线=SL · ▲=LONG 标注"
)

ok = notifier.send_photo(image_bytes, caption=caption)
notifier.close()

if ok:
    print("[✓] 发送成功！请查看 Telegram 验证图表样式。")
else:
    print("[✗] 发送失败，请检查 Bot Token 和 Chat ID。")
    sys.exit(1)
