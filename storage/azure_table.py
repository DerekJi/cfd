"""
Azure Table Storage 状态存储

生产环境使用 Azure Table Storage，本地开发使用 Azurite 模拟器。
连接字符串通过环境变量或构造参数传入，代码无需修改。

表结构:
  TradingState:
    PK=profile, RK=fsm_{symbol}  → FSM 状态
    PK=profile, RK=pos_{symbol}  → 持仓信息
    PK=profile, RK=daily_pnl     → 日内盈亏

  TradeHistory:
    PK=profile, RK={timestamp}_{symbol} → 交易记录

依赖: pip install azure-data-tables
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from storage.base import StateStorage

logger = logging.getLogger(__name__)

# Azurite 默认连接字符串
AZURITE_CONN_STRING = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/"
    "K1SZFPTOtr/KBHBeksoGMGw==;"
    "TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;"
)

TABLE_STATE = 'TradingState'
TABLE_HISTORY = 'TradeHistory'
TABLE_EXECUTION_LOGS = 'ExecutionLogs'


class AzureTableStorage(StateStorage):
    """
    Azure Table Storage 实现

    Args:
        connection_string: Azure Table 连接字符串 (None=使用 Azurite 默认)
    """

    def __init__(self, connection_string: Optional[str] = None):
        try:
            from azure.data.tables import TableServiceClient
        except ImportError:
            raise ImportError(
                "Azure Table SDK not installed. Run: pip install azure-data-tables"
            )

        conn_str = connection_string or AZURITE_CONN_STRING
        self._service = TableServiceClient.from_connection_string(conn_str)

        # 确保表存在
        self._ensure_table(TABLE_STATE)
        self._ensure_table(TABLE_HISTORY)
        self._ensure_table(TABLE_EXECUTION_LOGS)

    def _ensure_table(self, table_name: str):
        """创建表（如果不存在）"""
        try:
            self._service.create_table_if_not_exists(table_name)
        except Exception as e:
            logger.warning(f"Failed to create table {table_name}: {e}")

    def _get_table_client(self, table_name: str):
        return self._service.get_table_client(table_name)

    # ---- 通用读写 ----

    def _upsert(self, table: str, pk: str, rk: str, data: Dict[str, Any]):
        """写入或更新实体"""
        client = self._get_table_client(table)
        entity = {
            'PartitionKey': pk,
            'RowKey': rk,
            'data': json.dumps(data, ensure_ascii=False),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        client.upsert_entity(entity)

    def _get(self, table: str, pk: str, rk: str) -> Optional[Dict[str, Any]]:
        """读取实体"""
        client = self._get_table_client(table)
        try:
            entity = client.get_entity(partition_key=pk, row_key=rk)
            return json.loads(entity.get('data', '{}'))
        except Exception:
            return None

    def _delete(self, table: str, pk: str, rk: str):
        """删除实体"""
        client = self._get_table_client(table)
        try:
            client.delete_entity(partition_key=pk, row_key=rk)
        except Exception:
            pass  # 不存在则忽略

    # ---- FSM 状态 ----

    def save_fsm_state(self, profile: str, symbol: str, state: Dict[str, Any]) -> None:
        self._upsert(TABLE_STATE, profile, f'fsm_{symbol}', state)

    def load_fsm_state(self, profile: str, symbol: str) -> Optional[Dict[str, Any]]:
        return self._get(TABLE_STATE, profile, f'fsm_{symbol}')

    # ---- 持仓信息 ----

    def save_position(self, profile: str, symbol: str, position: Dict[str, Any]) -> None:
        self._upsert(TABLE_STATE, profile, f'pos_{symbol}', position)

    def load_position(self, profile: str, symbol: str) -> Optional[Dict[str, Any]]:
        return self._get(TABLE_STATE, profile, f'pos_{symbol}')

    def delete_position(self, profile: str, symbol: str) -> None:
        self._delete(TABLE_STATE, profile, f'pos_{symbol}')

    # ---- 日内盈亏 ----

    def save_daily_pnl(self, profile: str, data: Dict[str, Any]) -> None:
        self._upsert(TABLE_STATE, profile, 'daily_pnl', data)

    def load_daily_pnl(self, profile: str) -> Optional[Dict[str, Any]]:
        return self._get(TABLE_STATE, profile, 'daily_pnl')

    # ---- 交易记录 ----

    def append_trade_record(self, profile: str, record: Dict[str, Any]) -> None:
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        symbol = record.get('symbol', 'UNKNOWN')
        rk = f'{timestamp}_{symbol}'
        self._upsert(TABLE_HISTORY, profile, rk, record)

    def get_trade_records(
        self, profile: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取最近的交易记录 (按 RowKey 倒序)"""
        client = self._get_table_client(TABLE_HISTORY)
        try:
            query = f"PartitionKey eq '{profile}'"
            entities = list(client.query_entities(query))

            # 按 RowKey 倒序排列 (最新在前)
            entities.sort(key=lambda e: e.get('RowKey', ''), reverse=True)

            records = []
            for entity in entities[:limit]:
                data = json.loads(entity.get('data', '{}'))
                data['_row_key'] = entity.get('RowKey', '')
                data['_updated_at'] = entity.get('updated_at', '')
                records.append(data)

            return records
        except Exception as e:
            logger.error(f"Failed to get trade records: {e}")
            return []

    # ---- 半自动策略：观察列表 ----

    def save_watchlist(self, profile: str, items: List[Dict[str, Any]]) -> None:
        self._upsert(TABLE_STATE, profile, 'semi_watchlist', {'items': items})

    def load_watchlist(self, profile: str) -> List[Dict[str, Any]]:
        data = self._get(TABLE_STATE, profile, 'semi_watchlist')
        return data.get('items', []) if data else []

    # ---- 半自动策略：趋势激活池 ----

    def save_trend_pool(self, profile: str, items: List[Dict[str, Any]]) -> None:
        self._upsert(TABLE_STATE, profile, 'semi_trend_pool', {'items': items})

    def load_trend_pool(self, profile: str) -> List[Dict[str, Any]]:
        data = self._get(TABLE_STATE, profile, 'semi_trend_pool')
        return data.get('items', []) if data else []

    # ---- 半自动策略：待确认信号 ----

    def save_pending_signal(
        self, profile: str, symbol: str, signal: Dict[str, Any]
    ) -> None:
        self._upsert(TABLE_STATE, profile, f'semi_pending_{symbol}', signal)

    def load_pending_signal(
        self, profile: str, symbol: str
    ) -> Optional[Dict[str, Any]]:
        return self._get(TABLE_STATE, profile, f'semi_pending_{symbol}')

    def delete_pending_signal(self, profile: str, symbol: str) -> None:
        self._delete(TABLE_STATE, profile, f'semi_pending_{symbol}')

    # ---- 半自动策略：免打扰状态 ----

    def save_symbol_dnd(self, profile: str, symbol: str, expiry_iso: str) -> None:
        self._upsert(TABLE_STATE, profile, f'semi_dnd_{symbol}', {'expiry': expiry_iso})

    def load_symbol_dnd(self, profile: str, symbol: str) -> Optional[str]:
        data = self._get(TABLE_STATE, profile, f'semi_dnd_{symbol}')
        if not data:
            return None
        expiry = data.get('expiry')
        if expiry is None:
            return None
        # 检查是否已过期
        try:
            expiry_dt = datetime.fromisoformat(expiry)
            if expiry_dt <= datetime.now(timezone.utc):
                # 已过期，清理并返回 None
                self.clear_symbol_dnd(profile, symbol)
                return None
        except (ValueError, TypeError):
            return None
        return expiry

    def clear_symbol_dnd(self, profile: str, symbol: str) -> None:
        self._delete(TABLE_STATE, profile, f'semi_dnd_{symbol}')

    def save_global_dnd(self, profile: str, slots: List[Dict[str, Any]]) -> None:
        self._upsert(TABLE_STATE, profile, 'semi_dnd_global', {'slots': slots})

    def load_global_dnd(self, profile: str) -> List[Dict[str, Any]]:
        data = self._get(TABLE_STATE, profile, 'semi_dnd_global')
        return data.get('slots', []) if data else []
