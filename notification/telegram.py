"""
Telegram 通知

开仓 / 平仓 / 风控告警 / 每日摘要通过 Telegram Bot 发送。
使用 httpx 同步 POST 到 sendMessage API。
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = 'https://api.telegram.org'


class TelegramNotifier:
    """
    Telegram 通知器

    用法:
        notifier = TelegramNotifier(bot_token="xxx", chat_id="yyy")
        notifier.notify_entry("GBP_USD", "long", 1.25520, 1.25120, 3000, 12.0, ...)
        notifier.notify_exit("GBP_USD", "long", 1.25520, 1.26120, 18.0, "4h25m", ...)
    """

    def __init__(self, bot_token: str, chat_id: str):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._client = httpx.Client(timeout=10.0)

    def _send(self, text: str) -> bool:
        """发送 HTML 格式消息"""
        try:
            resp = self._client.post(
                f'{TELEGRAM_API}/bot{self._bot_token}/sendMessage',
                json={
                    'chat_id': self._chat_id,
                    'text': text,
                    'parse_mode': 'HTML',
                },
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    # ----------------------------------------------------------------
    # 交易通知
    # ----------------------------------------------------------------

    def notify_entry(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        units: float,
        risk_amount: float,
        adx: float,
        ema200: float,
        profile: str,
    ) -> bool:
        """开仓通知"""
        arrow = '🔺' if side == 'long' else '🔻'
        direction = '开多' if side == 'long' else '开空'
        lots = units / 100_000

        text = (
            f"{arrow} <b>{direction} {symbol}</b>\n"
            f"入场: {entry_price:.5f}\n"
            f"止损: {stop_loss:.5f}\n"
            f"仓位: {lots:.2f} 手 ({units:.0f} units)\n"
            f"风险: ${risk_amount:.2f}\n"
            f"ADX: {adx:.1f} | EMA200: {ema200:.5f}\n"
            f"Profile: {profile}"
        )
        return self._send(text)

    def notify_exit(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        hold_time: str,
        reason: str,
        profile: str,
    ) -> bool:
        """平仓通知"""
        emoji = '✅' if pnl >= 0 else '❌'
        direction = '平多' if side == 'long' else '平空'
        sign = '+' if pnl >= 0 else ''

        text = (
            f"{emoji} <b>{direction} {symbol}</b>\n"
            f"入场: {entry_price:.5f} → 出场: {exit_price:.5f}\n"
            f"盈亏: {sign}${pnl:.2f} ({sign}{pnl_pct:.2f}%)\n"
            f"持仓: {hold_time}\n"
            f"原因: {reason}\n"
            f"Profile: {profile}"
        )
        return self._send(text)

    def notify_risk_alert(
        self,
        alert_type: str,
        message: str,
        profile: str,
    ) -> bool:
        """风控告警"""
        text = (
            f"⚠️ <b>风控告警 [{alert_type}]</b>\n"
            f"{message}\n"
            f"Profile: {profile}"
        )
        return self._send(text)

    def notify_daily_summary(
        self,
        profile: str,
        date_str: str,
        trades_today: int,
        daily_pnl: float,
        equity: float,
        drawdown_pct: float,
    ) -> bool:
        """每日摘要"""
        sign = '+' if daily_pnl >= 0 else ''
        emoji = '📈' if daily_pnl >= 0 else '📉'

        text = (
            f"{emoji} <b>日报 {date_str}</b>\n"
            f"交易: {trades_today} 笔\n"
            f"日盈亏: {sign}${daily_pnl:.2f}\n"
            f"权益: ${equity:.2f}\n"
            f"回撤: {drawdown_pct:.2f}%\n"
            f"Profile: {profile}"
        )
        return self._send(text)

    def notify_error(self, error_msg: str, profile: str) -> bool:
        """系统错误通知"""
        text = (
            f"🚨 <b>系统错误</b>\n"
            f"{error_msg}\n"
            f"Profile: {profile}"
        )
        return self._send(text)

    def send_photo(self, image_bytes: bytes, caption: str = '') -> bool:
        """
        发送图片消息（sendPhoto API）

        Parameters
        ----------
        image_bytes : bytes
            PNG/JPEG 格式的图像字节流，例如由 utils.chart_generator.generate_ema_chart() 返回。
        caption : str, optional
            图片说明文字，支持 HTML 格式，最多 1024 个字符。

        Returns
        -------
        bool
            发送成功返回 True，失败返回 False。
        """
        try:
            resp = self._client.post(
                f'{TELEGRAM_API}/bot{self._bot_token}/sendPhoto',
                data={
                    'chat_id': self._chat_id,
                    'caption': caption,
                    'parse_mode': 'HTML',
                },
                files={
                    'photo': ('chart.png', image_bytes, 'image/png'),
                },
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Telegram send_photo failed: {e}")
            return False

    def close(self):
        """关闭 HTTP 客户端"""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
