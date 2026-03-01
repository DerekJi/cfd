"""
半自动 EMA 趋势跟踪策略 — Telegram Bot 命令交互

SRP: 本模块只负责 Telegram 命令的接收、解析和回复；
     状态读写委托给 StateStorage，交易执行委托给 SemiAutoEngine。

命令表
------
/watch  add|remove|list  [SYMBOL]
/range  set|clear|list   [SYMBOL HIGH LOW]
/trend  long|short|clear|list  [SYMBOL EMA_PERIOD]
/dnd    15|30  SYMBOL
/dnd    global  add|remove|list|clear  [HH:MM HH:MM]
/set    ema_h1  P1 [P2 ...]
/set    ema_5m  P1 [P2 ...]
/open   [SYMBOL]
/cancel [SYMBOL]
/status
/close  all
/move   SYMBOL  NEW_SL
/order  list

安全校验:
  所有 handler 均检查 chat_id，非授权用户直接忽略。

与引擎集成:
  SemiAutoBot 构造时可传入 engine (SemiAutoEngine)，
  /open 和 /close 等命令会调用 engine 上的方法；
  engine 为 None 时，相关命令返回提示信息。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from storage.base import StateStorage
from strategies.semi_auto.state import (
    DndTimeSlot,
    TrendPoolItem,
    WatchlistItem,
)

if TYPE_CHECKING:
    from live.semi_auto_engine import SemiAutoEngine

logger = logging.getLogger(__name__)

# ─── 默认 EMA 扫描周期 ───────────────────────────────────────────────────────
DEFAULT_EMA_H1 = [21, 55, 200]
DEFAULT_EMA_5M = [10, 20, 50]

# 设置存储 key（存在 FSM 表里）
_SETTINGS_KEY = '__sa_settings__'


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _guard(authorized_chat_id: str):
    """装饰器：HTTP 安全守卫，只允许授权 chat_id。"""
    def decorator(handler: Callable):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if update.effective_chat is None:
                return
            if str(update.effective_chat.id) != str(authorized_chat_id):
                logger.warning(
                    f"Unauthorized access from chat_id={update.effective_chat.id}"
                )
                return
            await handler(update, context)
        wrapper.__name__ = handler.__name__
        return wrapper
    return decorator


def _args(update: Update) -> List[str]:
    """提取消息中命令后的参数列表（小写）。"""
    text = update.message.text or ''
    parts = text.split()
    return [p.lower() for p in parts[1:]] if len(parts) > 1 else []


async def _reply(update: Update, text: str) -> None:
    """发送 HTML 格式回复。"""
    await update.message.reply_text(text, parse_mode='HTML')


# ─────────────────────────────────────────────────────────────────────────────
# SemiAutoBot
# ─────────────────────────────────────────────────────────────────────────────

class SemiAutoBot:
    """
    半自动策略 Telegram Bot

    Parameters
    ----------
    bot_token : str
        Telegram Bot Token。
    authorized_chat_id : str
        授权 chat_id，仅响应此对话的命令；字符串格式。
    storage : StateStorage
        状态存储实例，用于读写 watchlist / trend pool / pending signal 等。
    profile : str
        当前运行的 Profile 名称（如 'oanda_demo'）。
    engine : SemiAutoEngine, optional
        半自动引擎引用；/open、/close、/move 命令需要此依赖。
        未传入时，收到这些命令会回复提示信息。
    """

    def __init__(
        self,
        *,
        bot_token: str,
        authorized_chat_id: str,
        storage: StateStorage,
        profile: str,
        engine: Optional['SemiAutoEngine'] = None,
    ):
        self._token = bot_token
        self._chat_id = str(authorized_chat_id)
        self._storage = storage
        self._profile = profile
        self._engine = engine

        self._app = self._build_app()

    # ─── Application 构建 ────────────────────────────────────────────────────

    def _build_app(self) -> Application:
        app = Application.builder().token(self._token).build()
        G = _guard(self._chat_id)

        app.add_handler(CommandHandler('watch',  G(self._cmd_watch)))
        app.add_handler(CommandHandler('range',  G(self._cmd_range)))
        app.add_handler(CommandHandler('trend',  G(self._cmd_trend)))
        app.add_handler(CommandHandler('dnd',    G(self._cmd_dnd)))
        app.add_handler(CommandHandler('set',    G(self._cmd_set)))
        app.add_handler(CommandHandler('open',   G(self._cmd_open)))
        app.add_handler(CommandHandler('cancel', G(self._cmd_cancel)))
        app.add_handler(CommandHandler('status', G(self._cmd_status)))
        app.add_handler(CommandHandler('close',  G(self._cmd_close)))
        app.add_handler(CommandHandler('move',   G(self._cmd_move)))
        app.add_handler(CommandHandler('order',  G(self._cmd_order)))
        app.add_handler(CommandHandler('help',   G(self._cmd_help)))
        return app

    # ─── 运行模式 ─────────────────────────────────────────────────────────────

    def run_polling(self) -> None:
        """
        本地轮询模式（开发调试用）。

        阻塞运行，Ctrl+C 退出。
        """
        logger.info("Starting Telegram bot in polling mode ...")
        self._app.run_polling(drop_pending_updates=True)

    async def process_update(self, update_dict: Dict[str, Any]) -> None:
        """
        Webhook 单次处理模式（Azure Function HTTP Trigger 用）。

        将 Telegram 推送的 JSON update 字典传入即可。
        """
        await self._app.initialize()
        update = Update.de_json(update_dict, self._app.bot)
        await self._app.process_update(update)

    def process_update_sync(self, update_dict: Dict[str, Any]) -> None:
        """
        Webhook 模式的同步包装（供非 async 调用方使用）。
        """
        asyncio.run(self.process_update(update_dict))

    # ─────────────────────────────────────────────────────────────────────────
    # /watch  add|remove|list  [SYMBOL]
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /watch add EUR_USD
        /watch remove EUR_USD
        /watch list
        """
        args = _args(update)
        if not args:
            await _reply(update, _HELP_WATCH)
            return

        sub = args[0]

        if sub == 'list':
            items = [WatchlistItem.from_dict(d)
                     for d in self._storage.load_watchlist(self._profile)]
            if not items:
                await _reply(update, "观察列表为空。")
                return
            lines = []
            for it in items:
                rng = f"  区间: [{it.range_low} – {it.range_high}]" if it.range_high else ""
                lines.append(f"• <b>{it.symbol}</b>{rng}")
            await _reply(update, "📋 <b>观察列表</b>\n" + "\n".join(lines))

        elif sub == 'add':
            if len(args) < 2:
                await _reply(update, "用法: /watch add SYMBOL"); return
            symbol = args[1].upper()
            items = [WatchlistItem.from_dict(d)
                     for d in self._storage.load_watchlist(self._profile)]
            if any(it.symbol == symbol for it in items):
                await _reply(update, f"{symbol} 已在观察列表中。"); return
            items.append(WatchlistItem(symbol=symbol))
            self._storage.save_watchlist(self._profile, [it.to_dict() for it in items])
            await _reply(update, f"✅ 已添加 <b>{symbol}</b> 到观察列表。")

        elif sub == 'remove':
            if len(args) < 2:
                await _reply(update, "用法: /watch remove SYMBOL"); return
            symbol = args[1].upper()
            items = [WatchlistItem.from_dict(d)
                     for d in self._storage.load_watchlist(self._profile)]
            new_items = [it for it in items if it.symbol != symbol]
            if len(new_items) == len(items):
                await _reply(update, f"{symbol} 不在观察列表中。"); return
            self._storage.save_watchlist(self._profile, [it.to_dict() for it in new_items])
            await _reply(update, f"✅ 已从观察列表移除 <b>{symbol}</b>。")

        else:
            await _reply(update, _HELP_WATCH)

    # ─────────────────────────────────────────────────────────────────────────
    # /range  set|clear|list  [SYMBOL HIGH LOW]
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_range(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /range set EUR_USD 1.1000 1.0800
        /range clear EUR_USD
        /range list
        """
        args = _args(update)
        if not args:
            await _reply(update, _HELP_RANGE); return

        sub = args[0]

        if sub == 'list':
            items = [WatchlistItem.from_dict(d)
                     for d in self._storage.load_watchlist(self._profile)]
            lines = [
                f"• <b>{it.symbol}</b>  [{it.range_low} – {it.range_high}]"
                for it in items if it.range_high is not None
            ]
            await _reply(update,
                "📐 <b>震荡区间</b>\n" + "\n".join(lines) if lines else "暂无震荡区间设置。")

        elif sub == 'set':
            if len(args) < 4:
                await _reply(update, "用法: /range set SYMBOL HIGH LOW"); return
            symbol = args[1].upper()
            try:
                high, low = float(args[2]), float(args[3])
            except ValueError:
                await _reply(update, "高/低价格必须是数字。"); return
            if high <= low:
                await _reply(update, "HIGH 必须大于 LOW。"); return
            items = [WatchlistItem.from_dict(d)
                     for d in self._storage.load_watchlist(self._profile)]
            found = False
            for it in items:
                if it.symbol == symbol:
                    it.range_high = high
                    it.range_low = low
                    found = True
            if not found:
                items.append(WatchlistItem(symbol=symbol, range_high=high, range_low=low))
            self._storage.save_watchlist(self._profile, [it.to_dict() for it in items])
            await _reply(update,
                f"✅ {symbol} 震荡区间: [{low} – {high}]（H1扫描将跳过区间内信号）")

        elif sub == 'clear':
            if len(args) < 2:
                await _reply(update, "用法: /range clear SYMBOL"); return
            symbol = args[1].upper()
            items = [WatchlistItem.from_dict(d)
                     for d in self._storage.load_watchlist(self._profile)]
            for it in items:
                if it.symbol == symbol:
                    it.range_high = None
                    it.range_low = None
            self._storage.save_watchlist(self._profile, [it.to_dict() for it in items])
            await _reply(update, f"✅ 已清除 {symbol} 的震荡区间。")

        else:
            await _reply(update, _HELP_RANGE)

    # ─────────────────────────────────────────────────────────────────────────
    # /trend  long|short|clear|list  [SYMBOL EMA_PERIOD]
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_trend(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /trend long EUR_USD 21
        /trend short EUR_USD 55
        /trend clear EUR_USD
        /trend list
        """
        args = _args(update)
        if not args:
            await _reply(update, _HELP_TREND); return

        sub = args[0]

        if sub == 'list':
            items = [TrendPoolItem.from_dict(d)
                     for d in self._storage.load_trend_pool(self._profile)]
            if not items:
                await _reply(update, "趋势激活池为空。"); return
            lines = []
            for it in items:
                arrow = '🔺' if it.direction == 'long' else '🔻'
                lines.append(
                    f"{arrow} <b>{it.symbol}</b>  H1-EMA{it.h1_ema_period}  "
                    f"({it.added_at[:10]})"
                )
            await _reply(update, "🏊 <b>趋势激活池</b>\n" + "\n".join(lines))

        elif sub in ('long', 'short'):
            if len(args) < 3:
                await _reply(update, f"用法: /trend {sub} SYMBOL EMA_PERIOD"); return
            symbol = args[1].upper()
            try:
                period = int(args[2])
            except ValueError:
                await _reply(update, "EMA周期必须是正整数。"); return
            items = [TrendPoolItem.from_dict(d)
                     for d in self._storage.load_trend_pool(self._profile)]
            # 同品种去重（覆盖旧条目）
            items = [it for it in items if it.symbol != symbol]
            items.append(TrendPoolItem(symbol=symbol, direction=sub, h1_ema_period=period))
            self._storage.save_trend_pool(self._profile, [it.to_dict() for it in items])
            arrow = '🔺' if sub == 'long' else '🔻'
            await _reply(update,
                f"{arrow} 已将 <b>{symbol}</b> 加入趋势池（{sub}，H1-EMA{period}）")

        elif sub == 'clear':
            if len(args) < 2:
                await _reply(update, "用法: /trend clear SYMBOL"); return
            symbol = args[1].upper()
            items = [TrendPoolItem.from_dict(d)
                     for d in self._storage.load_trend_pool(self._profile)]
            new_items = [it for it in items if it.symbol != symbol]
            self._storage.save_trend_pool(self._profile, [it.to_dict() for it in new_items])
            await _reply(update, f"✅ 已从趋势池移除 <b>{symbol}</b>。")

        else:
            await _reply(update, _HELP_TREND)

    # ─────────────────────────────────────────────────────────────────────────
    # /dnd  15|30  SYMBOL
    # /dnd  global  add|remove|list|clear  [HH:MM HH:MM]
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_dnd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /dnd 15 EUR_USD      — 品种免打扰 15 分钟
        /dnd 30 EUR_USD      — 品种免打扰 30 分钟
        /dnd global add 22:00 06:00
        /dnd global remove 22:00 06:00
        /dnd global list
        /dnd global clear
        """
        args = _args(update)
        if not args:
            await _reply(update, _HELP_DND); return

        sub = args[0]

        # 品种免打扰
        if sub in ('15', '30'):
            if len(args) < 2:
                await _reply(update, f"用法: /dnd {sub} SYMBOL"); return
            symbol = args[1].upper()
            minutes = int(sub)
            expiry = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
            self._storage.save_symbol_dnd(self._profile, symbol, expiry)
            await _reply(update,
                f"🔕 {symbol} 免打扰 {minutes} 分钟（至 {expiry[11:16]} UTC）")

        # 全局免打扰管理
        elif sub == 'global':
            if len(args) < 2:
                await _reply(update, _HELP_DND); return
            gsub = args[1]

            if gsub == 'list':
                slots = [DndTimeSlot(**d)
                         for d in self._storage.load_global_dnd(self._profile)]
                if not slots:
                    await _reply(update, "全局免打扰时段为空。"); return
                lines = [f"• {s.start} – {s.end} UTC" for s in slots]
                await _reply(update, "🌙 <b>全局免打扰时段</b>\n" + "\n".join(lines))

            elif gsub == 'clear':
                self._storage.save_global_dnd(self._profile, [])
                await _reply(update, "✅ 已清除所有全局免打扰时段。")

            elif gsub == 'add':
                if len(args) < 4:
                    await _reply(update, "用法: /dnd global add HH:MM HH:MM"); return
                try:
                    slot = DndTimeSlot(start=args[2], end=args[3])
                except ValueError as e:
                    await _reply(update, f"格式错误: {e}"); return
                slots = self._storage.load_global_dnd(self._profile)
                # 去重
                if slot.to_dict() not in slots:
                    slots.append(slot.to_dict())
                    self._storage.save_global_dnd(self._profile, slots)
                await _reply(update,
                    f"✅ 已添加全局免打扰: {slot.start} – {slot.end} UTC")

            elif gsub == 'remove':
                if len(args) < 4:
                    await _reply(update, "用法: /dnd global remove HH:MM HH:MM"); return
                target = DndTimeSlot(start=args[2], end=args[3]).to_dict()
                slots = self._storage.load_global_dnd(self._profile)
                new_slots = [s for s in slots if s != target]
                self._storage.save_global_dnd(self._profile, new_slots)
                await _reply(update,
                    f"✅ 已移除全局免打扰: {args[2]} – {args[3]} UTC")

            else:
                await _reply(update, _HELP_DND)
        else:
            await _reply(update, _HELP_DND)

    # ─────────────────────────────────────────────────────────────────────────
    # /set  ema_h1  P1 [P2 ...]
    # /set  ema_5m  P1 [P2 ...]
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /set ema_h1 21 55 200
        /set ema_5m 10 20 50
        """
        args = _args(update)
        if len(args) < 2:
            await _reply(update, _HELP_SET); return

        sub = args[0]
        if sub not in ('ema_h1', 'ema_5m'):
            await _reply(update, _HELP_SET); return

        try:
            periods = [int(p) for p in args[1:]]
        except ValueError:
            await _reply(update, "EMA 周期必须为正整数列表。"); return

        settings = self._load_settings()
        settings[sub] = periods
        self._save_settings(settings)

        if self._engine:
            if sub == 'ema_h1':
                self._engine.ema_h1_periods = periods
            else:
                self._engine.ema_5m_periods = periods

        await _reply(update,
            f"✅ {sub.upper()} 已更新为: EMA{', EMA'.join(str(p) for p in periods)}")

    # ─────────────────────────────────────────────────────────────────────────
    # /open  [SYMBOL]
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_open(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /open            — 开仓最新待确认信号
        /open EUR_USD    — 指定品种
        """
        if not self._engine:
            await _reply(update, "⚠️ 引擎未就绪，无法执行开仓。"); return

        args = _args(update)
        symbol: Optional[str] = args[0].upper() if args else None

        if symbol:
            sig_dict = self._storage.load_pending_signal(self._profile, symbol)
        else:
            # 取所有品种中第一个待确认信号
            pool = self._storage.load_trend_pool(self._profile)
            sig_dict = None
            for item in pool:
                s = self._storage.load_pending_signal(self._profile, item['symbol'])
                if s:
                    symbol = item['symbol']
                    sig_dict = s
                    break

        if not sig_dict:
            await _reply(update, "⚠️ 未找到待确认信号，请等待扫描触发。"); return

        await _reply(update,
            f"⏳ 正在执行 <b>{symbol}</b> 开仓...")

        result = await asyncio.get_event_loop().run_in_executor(
            None, self._engine.execute_open, symbol
        )

        if result.get('success'):
            await _reply(update,
                f"✅ <b>{symbol}</b> 开仓成功\n"
                f"方向: {result.get('side')}\n"
                f"成交价: {result.get('fill_price')}\n"
                f"仓位: {result.get('units')} units\n"
                f"止损: {result.get('stop_loss')}")
        else:
            await _reply(update,
                f"❌ 开仓失败: {result.get('error', '未知错误')}")

    # ─────────────────────────────────────────────────────────────────────────
    # /cancel  [SYMBOL]
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /cancel          — 取消所有待确认信号
        /cancel EUR_USD  — 取消指定品种信号
        """
        args = _args(update)

        if args:
            symbol = args[0].upper()
            self._storage.delete_pending_signal(self._profile, symbol)
            await _reply(update, f"✅ 已取消 <b>{symbol}</b> 的待确认信号。")
        else:
            # 取消所有
            pool = self._storage.load_trend_pool(self._profile)
            cleared = []
            for item in pool:
                s = item['symbol']
                sig = self._storage.load_pending_signal(self._profile, s)
                if sig:
                    self._storage.delete_pending_signal(self._profile, s)
                    cleared.append(s)
            if cleared:
                await _reply(update,
                    f"✅ 已取消以下品种的待确认信号: {', '.join(cleared)}")
            else:
                await _reply(update, "没有待确认信号。")

    # ─────────────────────────────────────────────────────────────────────────
    # /status
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示系统全状态快照。"""
        now = datetime.now(timezone.utc)

        # Watchlist
        watchlist = [WatchlistItem.from_dict(d)
                     for d in self._storage.load_watchlist(self._profile)]
        w_lines = []
        for it in watchlist:
            rng = f" [{it.range_low}–{it.range_high}]" if it.range_high else ""
            w_lines.append(f"  • {it.symbol}{rng}")

        # Trend pool
        trend_pool = [TrendPoolItem.from_dict(d)
                      for d in self._storage.load_trend_pool(self._profile)]
        t_lines = []
        for it in trend_pool:
            arrow = '🔺' if it.direction == 'long' else '🔻'
            t_lines.append(f"  {arrow} {it.symbol}  H1-EMA{it.h1_ema_period}")

        # Pending signals
        p_lines = []
        for it in trend_pool:
            sig = self._storage.load_pending_signal(self._profile, it.symbol)
            if sig:
                p_lines.append(
                    f"  ⚡ {it.symbol}  {sig['direction']}  "
                    f"Entry≈{sig['entry_price']:.5f}  "
                    f"SL={sig['stop_loss']:.5f}  "
                    f"{sig['position_size']} units"
                )

        # DND
        global_dnd = [DndTimeSlot(**d)
                      for d in self._storage.load_global_dnd(self._profile)]
        active_dnd = [s for s in global_dnd if s.is_active(now)]

        # Settings
        settings = self._load_settings()
        ema_h1 = settings.get('ema_h1', DEFAULT_EMA_H1)
        ema_5m = settings.get('ema_5m', DEFAULT_EMA_5M)

        lines = [
            f"📊 <b>半自动策略状态</b>  {now.strftime('%H:%M UTC')}",
            f"\n👁 <b>观察列表</b> ({len(watchlist)})",
        ]
        lines += w_lines or ["  (空)"]
        lines += [f"\n🏊 <b>趋势池</b> ({len(trend_pool)})"]
        lines += t_lines or ["  (空)"]
        if p_lines:
            lines += ["\n⚡ <b>待确认信号</b>"] + p_lines
        if active_dnd:
            lines.append(f"\n🔕 全局免打扰进行中: "
                         f"{', '.join(f'{s.start}-{s.end}' for s in active_dnd)}")
        lines.append(
            f"\n⚙️  H1-EMA: {ema_h1}  |  5M-EMA: {ema_5m}"
        )
        await _reply(update, "\n".join(lines))

    # ─────────────────────────────────────────────────────────────────────────
    # /close  all
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /close all  — 平掉所有持仓
        """
        args = _args(update)
        if not args or args[0] != 'all':
            await _reply(update, "用法: /close all"); return
        if not self._engine:
            await _reply(update, "⚠️ 引擎未就绪。"); return

        await _reply(update, "⏳ 正在平掉所有持仓...")
        result = await asyncio.get_event_loop().run_in_executor(
            None, self._engine.execute_close_all
        )
        closed = result.get('closed', [])
        errors = result.get('errors', [])
        msg = f"✅ 已平仓: {', '.join(closed)}" if closed else "没有持仓需要平仓。"
        if errors:
            msg += f"\n❌ 失败: {', '.join(errors)}"
        await _reply(update, msg)

    # ─────────────────────────────────────────────────────────────────────────
    # /move  SYMBOL  NEW_SL
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_move(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /move EUR_USD 1.0850  — 将 EUR_USD 止损移至 1.0850
        """
        args = _args(update)
        if len(args) < 2:
            await _reply(update, "用法: /move SYMBOL NEW_SL"); return
        if not self._engine:
            await _reply(update, "⚠️ 引擎未就绪。"); return

        symbol = args[0].upper()
        try:
            new_sl = float(args[1])
        except ValueError:
            await _reply(update, "NEW_SL 必须是数字。"); return

        result = await asyncio.get_event_loop().run_in_executor(
            None, self._engine.execute_move_sl, symbol, new_sl
        )
        if result.get('success'):
            await _reply(update,
                f"✅ {symbol} 止损已移至 {new_sl:.5f}")
        else:
            await _reply(update,
                f"❌ 移止损失败: {result.get('error', '未知错误')}")

    # ─────────────────────────────────────────────────────────────────────────
    # /order  list
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /order list  — 列出 OANDA 当前持仓
        """
        args = _args(update)
        if not args or args[0] != 'list':
            await _reply(update, "用法: /order list"); return
        if not self._engine:
            await _reply(update, "⚠️ 引擎未就绪。"); return

        result = await asyncio.get_event_loop().run_in_executor(
            None, self._engine.get_open_positions
        )
        positions = result.get('positions', [])
        if not positions:
            await _reply(update, "当前无持仓。"); return

        lines = ["📋 <b>当前持仓</b>"]
        for p in positions:
            arrow = '🔺' if p.get('side') == 'long' else '🔻'
            pnl = p.get('unrealized_pnl', 0)
            sign = '+' if pnl >= 0 else ''
            lines.append(
                f"{arrow} <b>{p.get('symbol')}</b>  "
                f"Units={p.get('units')}  "
                f"Entry={p.get('avg_price', '?')}  "
                f"PnL={sign}{pnl:.2f}"
            )
        await _reply(update, "\n".join(lines))

    # ─────────────────────────────────────────────────────────────────────────
    # /help
    # ─────────────────────────────────────────────────────────────────────────

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await _reply(update, _HELP_ALL)

    # ─── 内部：设置读写 ───────────────────────────────────────────────────────

    def _load_settings(self) -> Dict[str, Any]:
        raw = self._storage.load_fsm_state(self._profile, _SETTINGS_KEY)
        if raw is None:
            return {'ema_h1': DEFAULT_EMA_H1, 'ema_5m': DEFAULT_EMA_5M}
        return raw

    def _save_settings(self, settings: Dict[str, Any]) -> None:
        self._storage.save_fsm_state(self._profile, _SETTINGS_KEY, settings)

    # ─── 公开属性：供引擎在初始化时读取设置 ────────────────────────────────────

    def load_ema_settings(self):
        """返回 (h1_periods, 5m_periods)"""
        s = self._load_settings()
        return s.get('ema_h1', DEFAULT_EMA_H1), s.get('ema_5m', DEFAULT_EMA_5M)


# ─────────────────────────────────────────────────────────────────────────────
# 帮助文本常量
# ─────────────────────────────────────────────────────────────────────────────

_HELP_WATCH = (
    "<b>/watch</b>\n"
    "  add SYMBOL      — 添加到观察列表\n"
    "  remove SYMBOL   — 从观察列表移除\n"
    "  list            — 查看观察列表"
)
_HELP_RANGE = (
    "<b>/range</b>\n"
    "  set SYMBOL HIGH LOW  — 设置震荡区间\n"
    "  clear SYMBOL         — 清除震荡区间\n"
    "  list                 — 查看所有震荡区间"
)
_HELP_TREND = (
    "<b>/trend</b>\n"
    "  long SYMBOL EMA_PERIOD  — 添加多头趋势（绑定H1均线周期）\n"
    "  short SYMBOL EMA_PERIOD — 添加空头趋势\n"
    "  clear SYMBOL            — 移除品种\n"
    "  list                    — 查看趋势池"
)
_HELP_DND = (
    "<b>/dnd</b>\n"
    "  15|30 SYMBOL            — 品种免打扰 N 分钟\n"
    "  global add HH:MM HH:MM  — 添加全局静默时段\n"
    "  global remove HH:MM HH:MM\n"
    "  global list\n"
    "  global clear"
)
_HELP_SET = (
    "<b>/set</b>\n"
    "  ema_h1 P1 [P2 ...]  — 设置 H1 扫描 EMA 周期\n"
    "  ema_5m P1 [P2 ...]  — 设置 5M 扫描 EMA 周期"
)
_HELP_ALL = (
    "📖 <b>半自动策略命令</b>\n\n"
    + _HELP_WATCH + "\n\n"
    + _HELP_RANGE + "\n\n"
    + _HELP_TREND + "\n\n"
    + _HELP_DND   + "\n\n"
    + _HELP_SET   + "\n\n"
    "<b>信号</b>\n"
    "  /open [SYMBOL]    — 确认开仓\n"
    "  /cancel [SYMBOL]  — 取消信号\n\n"
    "<b>持仓</b>\n"
    "  /status           — 系统状态\n"
    "  /order list       — 当前持仓\n"
    "  /close all        — 平掉所有持仓\n"
    "  /move SYMBOL SL   — 移动止损"
)
