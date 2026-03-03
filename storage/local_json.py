"""
本地 JSON 文件状态存储 — 调试用

无需 Azure 依赖，数据保存在本地 JSON 文件中。
适合本地开发和 CLI 测试。
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from storage.base import StateStorage

logger = logging.getLogger(__name__)


class LocalJsonStorage(StateStorage):
    """
    本地 JSON 文件存储

    文件结构:
        {base_dir}/
          {profile}/
            fsm_{symbol}.json
            pos_{symbol}.json
            daily_pnl.json
            trade_history.json  (列表)

    Args:
        base_dir: 存储目录 (默认 ./local_state)
    """

    def __init__(self, base_dir: str = './local_state'):
        self._base_dir = base_dir

    def _get_path(self, profile: str, filename: str) -> str:
        """获取文件路径，自动创建目录"""
        dir_path = os.path.join(self._base_dir, profile)
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, filename)

    def _write_json(self, path: str, data: Any):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _read_json(self, path: str) -> Optional[Any]:
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    # ---- FSM 状态 ----

    def save_fsm_state(self, profile: str, symbol: str, state: Dict[str, Any]) -> None:
        path = self._get_path(profile, f'fsm_{symbol}.json')
        self._write_json(path, state)

    def load_fsm_state(self, profile: str, symbol: str) -> Optional[Dict[str, Any]]:
        path = self._get_path(profile, f'fsm_{symbol}.json')
        return self._read_json(path)

    # ---- 持仓信息 ----

    def save_position(self, profile: str, symbol: str, position: Dict[str, Any]) -> None:
        path = self._get_path(profile, f'pos_{symbol}.json')
        self._write_json(path, position)

    def load_position(self, profile: str, symbol: str) -> Optional[Dict[str, Any]]:
        path = self._get_path(profile, f'pos_{symbol}.json')
        return self._read_json(path)

    def delete_position(self, profile: str, symbol: str) -> None:
        path = self._get_path(profile, f'pos_{symbol}.json')
        if os.path.exists(path):
            os.remove(path)

    # ---- 日内盈亏 ----

    def save_daily_pnl(self, profile: str, data: Dict[str, Any]) -> None:
        path = self._get_path(profile, 'daily_pnl.json')
        self._write_json(path, data)

    def load_daily_pnl(self, profile: str) -> Optional[Dict[str, Any]]:
        path = self._get_path(profile, 'daily_pnl.json')
        return self._read_json(path)

    # ---- 交易记录 ----

    def append_trade_record(self, profile: str, record: Dict[str, Any]) -> None:
        path = self._get_path(profile, 'trade_history.json')
        records = self._read_json(path) or []
        record['_timestamp'] = datetime.now(timezone.utc).isoformat()
        records.append(record)
        self._write_json(path, records)

    def get_trade_records(
        self, profile: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        path = self._get_path(profile, 'trade_history.json')
        records = self._read_json(path) or []
        # 最新在前
        return list(reversed(records[-limit:]))

    # ---- 半自动策略：观察列表 ----

    def save_watchlist(self, profile: str, items: List[Dict[str, Any]]) -> None:
        path = self._get_path(profile, 'semi_watchlist.json')
        self._write_json(path, items)

    def load_watchlist(self, profile: str) -> List[Dict[str, Any]]:
        path = self._get_path(profile, 'semi_watchlist.json')
        return self._read_json(path) or []

    # ---- 半自动策略：趋势激活池 ----

    def save_trend_pool(self, profile: str, items: List[Dict[str, Any]]) -> None:
        path = self._get_path(profile, 'semi_trend_pool.json')
        self._write_json(path, items)

    def load_trend_pool(self, profile: str) -> List[Dict[str, Any]]:
        path = self._get_path(profile, 'semi_trend_pool.json')
        return self._read_json(path) or []

    # ---- 半自动策略：待确认信号 ----

    def save_pending_signal(
        self, profile: str, symbol: str, signal: Dict[str, Any]
    ) -> None:
        path = self._get_path(profile, f'semi_pending_{symbol}.json')
        self._write_json(path, signal)

    def load_pending_signal(
        self, profile: str, symbol: str
    ) -> Optional[Dict[str, Any]]:
        path = self._get_path(profile, f'semi_pending_{symbol}.json')
        return self._read_json(path)

    def delete_pending_signal(self, profile: str, symbol: str) -> None:
        path = self._get_path(profile, f'semi_pending_{symbol}.json')
        if os.path.exists(path):
            os.remove(path)

    # ---- 半自动策略：免打扰状态 ----

    def save_symbol_dnd(self, profile: str, symbol: str, expiry_iso: str) -> None:
        path = self._get_path(profile, f'semi_dnd_{symbol}.json')
        self._write_json(path, {'expiry': expiry_iso})

    def load_symbol_dnd(self, profile: str, symbol: str) -> Optional[str]:
        path = self._get_path(profile, f'semi_dnd_{symbol}.json')
        data = self._read_json(path)
        if not data:
            return None
        expiry = data.get('expiry')
        if expiry is None:
            return None
        # 检查是否已过期
        try:
            expiry_dt = datetime.fromisoformat(expiry)
            if expiry_dt <= datetime.now(timezone.utc):
                # 已过期，清理文件并返回 None
                self.clear_symbol_dnd(profile, symbol)
                return None
        except (ValueError, TypeError):
            return None
        return expiry

    def clear_symbol_dnd(self, profile: str, symbol: str) -> None:
        path = self._get_path(profile, f'semi_dnd_{symbol}.json')
        if os.path.exists(path):
            os.remove(path)

    def save_global_dnd(self, profile: str, slots: List[Dict[str, Any]]) -> None:
        path = self._get_path(profile, 'semi_dnd_global.json')
        self._write_json(path, slots)

    def load_global_dnd(self, profile: str) -> List[Dict[str, Any]]:
        path = self._get_path(profile, 'semi_dnd_global.json')
        return self._read_json(path) or []

    # ---- 交易事件日志 ----

    def log_trade_event(self, profile: str, event: Dict[str, Any]) -> None:
        """
        追加到 trade_events.jsonl 文件（JSON Lines 格式）。

        每行一条事件，方便 grep / jq 等工具检索。
        """
        path = self._get_path(profile, 'trade_events.jsonl')
        event['logged_at'] = datetime.now(timezone.utc).isoformat()
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
