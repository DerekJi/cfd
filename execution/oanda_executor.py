"""
Oanda REST v20 交易执行器

API 文档: https://developer.oanda.com/rest-live-v20/order-ep/
"""

import logging
from typing import List

import httpx

from execution.base import (
    TradeExecutor,
    OrderResult,
    PositionInfo,
    AccountInfo,
)

logger = logging.getLogger(__name__)

OANDA_URLS = {
    'practice': 'https://api-fxpractice.oanda.com',
    'live': 'https://api-fxtrade.oanda.com',
}


class OandaExecutor(TradeExecutor):
    """
    Oanda REST v20 交易执行器

    职责: 下单、平仓、修改止损、查询账户/持仓
    行情数据由 OandaDataProvider 负责，不在此处理。

    Args:
        api_key: Oanda API Key
        account_id: Oanda Account ID (如 '101-011-38218532-001')
        environment: 'practice' 或 'live'
    """

    def __init__(self, api_key: str, account_id: str, environment: str = 'practice'):
        base_url = OANDA_URLS.get(environment)
        if not base_url:
            raise ValueError(f"Unknown environment: {environment}")

        self._account_id = account_id
        self._client = httpx.Client(
            base_url=base_url,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            timeout=30.0,
        )

    # ----------------------------------------------------------------
    # TradeExecutor 接口实现
    # ----------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        units: float,
        stop_loss: float,
    ) -> OrderResult:
        """
        市价下单 + 服务端止损

        Oanda units: 正数=买入, 负数=卖出
        """
        signed_units = str(int(units)) if side == 'buy' else str(-int(units))

        # 根据品种确定止损精度
        price_str = self._format_price(symbol, stop_loss)

        body = {
            'order': {
                'type': 'MARKET',
                'instrument': symbol,
                'units': signed_units,
                'stopLossOnFill': {
                    'price': price_str,
                },
            }
        }

        try:
            resp = self._client.post(
                f'/v3/accounts/{self._account_id}/orders',
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

            # 解析成交结果
            fill = data.get('orderFillTransaction', {})
            trade_opened = fill.get('tradeOpened', {})

            return OrderResult(
                success=True,
                order_id=fill.get('id'),
                trade_id=trade_opened.get('tradeID'),
                fill_price=float(fill.get('price', 0)),
                units=float(fill.get('units', 0)),
            )

        except httpx.HTTPStatusError as e:
            error_msg = e.response.text if e.response else str(e)
            logger.error(f"Oanda place_order failed: {error_msg}")
            return OrderResult(success=False, error=error_msg)
        except Exception as e:
            logger.error(f"Oanda place_order error: {e}")
            return OrderResult(success=False, error=str(e))

    def close_position(self, trade_id: str) -> OrderResult:
        """
        平仓 (关闭指定 trade)
        """
        try:
            resp = self._client.put(
                f'/v3/accounts/{self._account_id}/trades/{trade_id}/close',
                json={'units': 'ALL'},
            )
            resp.raise_for_status()
            data = resp.json()

            close_tx = data.get('orderFillTransaction', {})
            return OrderResult(
                success=True,
                order_id=close_tx.get('id'),
                trade_id=trade_id,
                fill_price=float(close_tx.get('price', 0)),
                units=float(close_tx.get('units', 0)),
            )

        except httpx.HTTPStatusError as e:
            error_msg = e.response.text if e.response else str(e)
            logger.error(f"Oanda close_position failed: {error_msg}")
            return OrderResult(success=False, error=error_msg)
        except Exception as e:
            logger.error(f"Oanda close_position error: {e}")
            return OrderResult(success=False, error=str(e))

    def modify_stop_loss(self, trade_id: str, new_price: float) -> bool:
        """
        修改止损价格

        Oanda 的止损是独立的 order，需要先找到关联的 SL order ID。
        简化方案: 用 trade 的 dependent orders 查找。
        """
        try:
            # 1. 获取 trade 详情，找到 stopLoss order ID
            resp = self._client.get(
                f'/v3/accounts/{self._account_id}/trades/{trade_id}',
            )
            resp.raise_for_status()
            trade_data = resp.json().get('trade', {})
            sl_order_id = trade_data.get('stopLossOrder', {}).get('id')

            if not sl_order_id:
                logger.warning(f"No stop loss order found for trade {trade_id}")
                return False

            # 2. 获取品种名以确定精度
            instrument = trade_data.get('instrument', '')
            price_str = self._format_price(instrument, new_price)

            # 3. 修改 SL order
            resp = self._client.put(
                f'/v3/accounts/{self._account_id}/orders/{sl_order_id}',
                json={
                    'order': {
                        'type': 'STOP_LOSS',
                        'tradeID': trade_id,
                        'price': price_str,
                    }
                },
            )
            resp.raise_for_status()
            logger.info(f"Stop loss modified: trade={trade_id}, price={price_str}")
            return True

        except Exception as e:
            logger.error(f"Oanda modify_stop_loss error: {e}")
            return False

    def get_account_info(self) -> AccountInfo:
        """获取账户摘要"""
        resp = self._client.get(
            f'/v3/accounts/{self._account_id}/summary',
        )
        resp.raise_for_status()
        acct = resp.json().get('account', {})

        return AccountInfo(
            balance=float(acct.get('balance', 0)),
            equity=float(acct.get('NAV', 0)),
            unrealized_pnl=float(acct.get('unrealizedPL', 0)),
            currency=acct.get('currency', 'USD'),
            margin_used=float(acct.get('marginUsed', 0)),
            margin_available=float(acct.get('marginAvailable', 0)),
        )

    def get_positions(self) -> List[PositionInfo]:
        """获取当前持仓"""
        resp = self._client.get(
            f'/v3/accounts/{self._account_id}/openTrades',
        )
        resp.raise_for_status()
        trades = resp.json().get('trades', [])

        positions = []
        for t in trades:
            units = float(t.get('currentUnits', 0))
            side = 'long' if units > 0 else 'short'
            sl_price = None
            sl_order = t.get('stopLossOrder', {})
            if sl_order:
                sl_price = float(sl_order.get('price', 0))

            positions.append(PositionInfo(
                position_id=t['id'],
                symbol=t.get('instrument', ''),
                side=side,
                units=abs(units),
                entry_price=float(t.get('price', 0)),
                unrealized_pnl=float(t.get('unrealizedPL', 0)),
                stop_loss=sl_price,
            ))

        return positions

    # ----------------------------------------------------------------
    # 辅助方法
    # ----------------------------------------------------------------

    @staticmethod
    def _format_price(instrument: str, price: float) -> str:
        """
        按品种精度格式化价格

        JPY 对: 3位小数 (如 156.123)
        其他:   5位小数 (如 1.25120)
        """
        if 'JPY' in instrument.upper():
            return f'{price:.3f}'
        return f'{price:.5f}'

    def close(self):
        """关闭 HTTP 客户端"""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
