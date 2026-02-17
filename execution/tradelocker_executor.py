"""
TradeLocker 交易执行器 (Blue Guardian 实盘)

仅负责交易执行 (开仓/平仓/止损)，不获取行情数据。
行情数据统一由 OandaDataProvider 提供（避免 TradeLocker 限流）。

依赖: pip install tradelocker
SDK 文档: https://github.com/nickmccullum/tradelocker-python
"""

import logging
from typing import List

from execution.base import (
    TradeExecutor,
    OrderResult,
    PositionInfo,
    AccountInfo,
)

logger = logging.getLogger(__name__)


class TradeLockerExecutor(TradeExecutor):
    """
    TradeLocker 交易执行器

    ⚠️ 注意:
      - 只用于交易操作 (开仓/平仓/修改止损)
      - 不拉取行情数据 (TradeLocker 限流风险)
      - 行情数据走 OandaDataProvider

    Args:
        email: TradeLocker 账户邮箱
        password: TradeLocker 账户密码
        server: TradeLocker 服务器名 (如 'OSP-DEMO')
        environment: TradeLocker 环境 URL
    """

    def __init__(
        self,
        email: str,
        password: str,
        server: str,
        environment: str = 'https://live.tradelocker.com',
    ):
        try:
            from tradelocker import TLAPI
        except ImportError:
            raise ImportError(
                "TradeLocker SDK not installed. Run: pip install tradelocker"
            )

        self._tl = TLAPI(
            environment=environment,
            username=email,
            password=password,
            server=server,
        )
        self._instrument_cache = {}  # symbol → instrument_id 缓存

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

        TradeLocker 下单用手数 (lots), 非 units。
        units / 100000 = lots
        """
        try:
            instrument_id = self._get_instrument_id(symbol)
            if not instrument_id:
                return OrderResult(
                    success=False,
                    error=f"Unknown symbol: {symbol}",
                )

            lots = units / 100000.0
            tl_side = side.lower()  # 'buy' or 'sell'

            order_id = self._tl.create_order(
                instrument_id,
                quantity=lots,
                side=tl_side,
                type_='market',
                stop_loss=stop_loss,
                stop_loss_type='absolute',
            )

            if order_id:
                logger.info(
                    f"TradeLocker order placed: {symbol} {side} {lots:.2f} lots, SL={stop_loss}"
                )
                return OrderResult(
                    success=True,
                    order_id=str(order_id),
                )
            else:
                return OrderResult(success=False, error="Order creation returned None")

        except Exception as e:
            logger.error(f"TradeLocker place_order error: {e}")
            return OrderResult(success=False, error=str(e))

    def close_position(self, trade_id: str) -> OrderResult:
        """平仓"""
        try:
            self._tl.close_position(position_id=int(trade_id))
            logger.info(f"TradeLocker position closed: {trade_id}")
            return OrderResult(success=True, trade_id=trade_id)
        except Exception as e:
            logger.error(f"TradeLocker close_position error: {e}")
            return OrderResult(success=False, error=str(e))

    def modify_stop_loss(self, trade_id: str, new_price: float) -> bool:
        """
        修改止损价格

        TradeLocker SDK 的 modify 需要通过 position 的 order ID。
        简化: 获取 position 信息后修改关联的 SL order。
        """
        try:
            # TradeLocker SDK 可能需要用 modify_order 接口
            # 具体方法取决于 SDK 版本，这里做最佳尝试
            positions = self._tl.get_all_positions()
            if positions is None or positions.empty:
                logger.warning("No positions found for stop loss modification")
                return False

            # 查找匹配的持仓
            pos = positions[positions['id'] == int(trade_id)]
            if pos.empty:
                logger.warning(f"Position {trade_id} not found")
                return False

            # 尝试使用 SDK 修改止损
            # 注意: TradeLocker SDK 的 API 可能不直接支持修改止损
            # 实际实现需要根据 SDK 版本确认可用方法
            logger.warning(
                f"TradeLocker modify_stop_loss: SDK support TBD. "
                f"trade_id={trade_id}, new_price={new_price}"
            )
            return False

        except Exception as e:
            logger.error(f"TradeLocker modify_stop_loss error: {e}")
            return False

    def get_account_info(self) -> AccountInfo:
        """获取账户信息"""
        try:
            state = self._tl.get_account_state()
            # TradeLocker 返回格式可能包含:
            # accountBalance, todayGross, todayNet, openGrossPnL etc.
            if isinstance(state, dict):
                return AccountInfo(
                    balance=float(state.get('accountBalance', 0)),
                    equity=float(state.get('accountBalance', 0))
                           + float(state.get('openGrossPnL', 0)),
                    unrealized_pnl=float(state.get('openGrossPnL', 0)),
                    currency='USD',
                )
            else:
                logger.warning(f"Unexpected account state format: {type(state)}")
                return AccountInfo(balance=0, equity=0, currency='USD')
        except Exception as e:
            logger.error(f"TradeLocker get_account_info error: {e}")
            return AccountInfo(balance=0, equity=0, currency='USD')

    def get_positions(self) -> List[PositionInfo]:
        """获取当前持仓"""
        try:
            positions_df = self._tl.get_all_positions()
            if positions_df is None or positions_df.empty:
                return []

            result = []
            for _, row in positions_df.iterrows():
                qty = float(row.get('qty', 0))
                side = 'long' if row.get('side', '').lower() == 'buy' else 'short'

                result.append(PositionInfo(
                    position_id=str(row.get('id', '')),
                    symbol=str(row.get('tradableInstrumentId', '')),
                    side=side,
                    units=qty * 100000,  # lots → units
                    entry_price=float(row.get('avgPrice', 0)),
                    unrealized_pnl=float(row.get('unrealizedPl', 0)),
                ))

            return result
        except Exception as e:
            logger.error(f"TradeLocker get_positions error: {e}")
            return []

    # ----------------------------------------------------------------
    # 辅助方法
    # ----------------------------------------------------------------

    def _get_instrument_id(self, symbol: str) -> int:
        """
        通过品种名获取 TradeLocker instrument ID

        缓存结果避免重复查询。
        """
        if symbol in self._instrument_cache:
            return self._instrument_cache[symbol]

        try:
            instrument_id = self._tl.get_instrument_id_from_symbol_name(symbol)
            if instrument_id:
                self._instrument_cache[symbol] = instrument_id
            return instrument_id
        except Exception as e:
            logger.error(f"Failed to resolve instrument ID for {symbol}: {e}")
            return None
