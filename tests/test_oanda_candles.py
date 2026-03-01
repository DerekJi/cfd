"""
OandaDataProvider 单元测试

测试范围：
  - get_candles(): 正常解析、空数据、不完整K线过滤
  - get_multi_timeframe(): 多周期批量拉取、列格式一致性、周期键正确

使用 unittest.mock 模拟 HTTP 请求，不需要真实 API Key。
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data.oanda_candles import OandaDataProvider


# ─────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def _make_candle(time_str: str, o: str, h: str, l: str, c: str, complete: bool = True) -> dict:
    """构造 Oanda API 单根 K 线数据"""
    return {
        'time': time_str,
        'complete': complete,
        'volume': 100,
        'mid': {'o': o, 'h': h, 'l': l, 'c': c},
    }


def _make_response(candles: list) -> MagicMock:
    """构造 httpx Response Mock"""
    resp = MagicMock()
    resp.json.return_value = {'candles': candles}
    resp.raise_for_status = MagicMock()
    return resp


EXPECTED_COLUMNS = {'datetime', 'open', 'high', 'low', 'close', 'volume'}


# ─────────────────────────────────────────────────────────────────────────────
# get_candles 测试
# ─────────────────────────────────────────────────────────────────────────────

class TestGetCandles:

    def _make_provider(self) -> OandaDataProvider:
        with patch('httpx.Client'):
            return OandaDataProvider(api_key='test_key', environment='practice')

    def test_returns_dataframe_with_correct_columns(self):
        """正常情况下返回包含所有必要列的 DataFrame"""
        provider = self._make_provider()
        candles = [
            _make_candle('2026-01-01T00:00:00Z', '1.1000', '1.1050', '1.0990', '1.1020'),
            _make_candle('2026-01-01T01:00:00Z', '1.1020', '1.1080', '1.1010', '1.1060'),
        ]
        provider._client.get.return_value = _make_response(candles)

        df = provider.get_candles('EUR_USD', granularity='H1', count=2)

        assert isinstance(df, pd.DataFrame)
        assert EXPECTED_COLUMNS.issubset(set(df.columns))
        assert len(df) == 2

    def test_datetime_column_is_parsed(self):
        """datetime 列应被解析为 pandas Timestamp 类型"""
        provider = self._make_provider()
        candles = [
            _make_candle('2026-01-01T00:00:00Z', '1.1000', '1.1050', '1.0990', '1.1020'),
        ]
        provider._client.get.return_value = _make_response(candles)

        df = provider.get_candles('EUR_USD', granularity='H1', count=1)

        assert pd.api.types.is_datetime64_any_dtype(df['datetime'])

    def test_incomplete_candles_are_filtered(self):
        """未完成（complete=False）的K线应被过滤掉"""
        provider = self._make_provider()
        candles = [
            _make_candle('2026-01-01T00:00:00Z', '1.1000', '1.1050', '1.0990', '1.1020', complete=True),
            _make_candle('2026-01-01T01:00:00Z', '1.1020', '1.1080', '1.1010', '1.1060', complete=False),
        ]
        provider._client.get.return_value = _make_response(candles)

        df = provider.get_candles('EUR_USD', granularity='H1', count=2)

        assert len(df) == 1

    def test_empty_candles_returns_empty_dataframe(self):
        """Oanda 返回空K线时应返回空 DataFrame"""
        provider = self._make_provider()
        provider._client.get.return_value = _make_response([])

        df = provider.get_candles('EUR_USD', granularity='H1', count=200)

        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert EXPECTED_COLUMNS.issubset(set(df.columns))

    def test_numeric_columns_are_float(self):
        """price 列应为 float 类型"""
        provider = self._make_provider()
        candles = [
            _make_candle('2026-01-01T00:00:00Z', '1.1000', '1.1050', '1.0990', '1.1020'),
        ]
        provider._client.get.return_value = _make_response(candles)

        df = provider.get_candles('EUR_USD', granularity='H1', count=1)

        for col in ('open', 'high', 'low', 'close'):
            assert pd.api.types.is_float_dtype(df[col]), f"{col} should be float"


# ─────────────────────────────────────────────────────────────────────────────
# get_multi_timeframe 测试
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMultiTimeframe:

    def _make_provider(self) -> OandaDataProvider:
        with patch('httpx.Client'):
            return OandaDataProvider(api_key='test_key', environment='practice')

    def _h1_candles(self) -> list:
        return [
            _make_candle('2026-01-01T00:00:00Z', '1.1000', '1.1050', '1.0990', '1.1020'),
            _make_candle('2026-01-01T01:00:00Z', '1.1020', '1.1080', '1.1010', '1.1060'),
        ]

    def _m5_candles(self) -> list:
        return [
            _make_candle('2026-01-01T00:00:00Z', '1.1000', '1.1010', '1.0998', '1.1005'),
            _make_candle('2026-01-01T00:05:00Z', '1.1005', '1.1015', '1.1002', '1.1012'),
            _make_candle('2026-01-01T00:10:00Z', '1.1012', '1.1020', '1.1008', '1.1018'),
        ]

    def test_returns_dict_with_all_requested_granularities(self):
        """返回值应包含所有请求的周期键"""
        provider = self._make_provider()
        # 第一次调用返回 H1，第二次返回 M5
        provider._client.get.side_effect = [
            _make_response(self._h1_candles()),
            _make_response(self._m5_candles()),
        ]

        result = provider.get_multi_timeframe('EUR_USD', granularities=['H1', 'M5'], count=200)

        assert 'H1' in result
        assert 'M5' in result

    def test_each_value_is_dataframe(self):
        """每个周期的值都应是 DataFrame"""
        provider = self._make_provider()
        provider._client.get.side_effect = [
            _make_response(self._h1_candles()),
            _make_response(self._m5_candles()),
        ]

        result = provider.get_multi_timeframe('EUR_USD', granularities=['H1', 'M5'], count=200)

        for key, df in result.items():
            assert isinstance(df, pd.DataFrame), f"{key} should be DataFrame"

    def test_both_timeframes_have_same_columns(self):
        """H1 和 M5 的列格式应完全一致"""
        provider = self._make_provider()
        provider._client.get.side_effect = [
            _make_response(self._h1_candles()),
            _make_response(self._m5_candles()),
        ]

        result = provider.get_multi_timeframe('EUR_USD', granularities=['H1', 'M5'], count=200)

        assert set(result['H1'].columns) == set(result['M5'].columns)
        assert EXPECTED_COLUMNS.issubset(set(result['H1'].columns))

    def test_row_counts_match_available_complete_candles(self):
        """每个周期的行数应与实际完整K线数量匹配"""
        provider = self._make_provider()
        provider._client.get.side_effect = [
            _make_response(self._h1_candles()),   # 2 根
            _make_response(self._m5_candles()),   # 3 根
        ]

        result = provider.get_multi_timeframe('EUR_USD', granularities=['H1', 'M5'], count=200)

        assert len(result['H1']) == 2
        assert len(result['M5']) == 3

    def test_single_granularity(self):
        """只传一个周期时也应正常工作"""
        provider = self._make_provider()
        provider._client.get.side_effect = [
            _make_response(self._h1_candles()),
        ]

        result = provider.get_multi_timeframe('EUR_USD', granularities=['H1'], count=200)

        assert list(result.keys()) == ['H1']
        assert len(result['H1']) == 2

    def test_empty_granularities_returns_empty_dict(self):
        """传入空列表时应返回空字典"""
        provider = self._make_provider()

        result = provider.get_multi_timeframe('EUR_USD', granularities=[], count=200)

        assert result == {}

    def test_calls_get_candles_once_per_granularity(self):
        """应为每个周期调用一次 HTTP 请求"""
        provider = self._make_provider()
        provider._client.get.side_effect = [
            _make_response(self._h1_candles()),
            _make_response(self._m5_candles()),
        ]

        provider.get_multi_timeframe('EUR_USD', granularities=['H1', 'M5'], count=200)

        assert provider._client.get.call_count == 2
