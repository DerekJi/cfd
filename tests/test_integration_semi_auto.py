"""
集成测试 — 半自动 EMA 趋势跟踪策略 Phase 1-3

测试跨模块协作：
  1. 信号生成管线：模拟 K 线 → EMA 扫描 → 止损计算 → 保存 PendingSignal
  2. 完整 DND 生命周期：写入 → 过期自清理 → 未过期保持
  3. DndTimeSlot.is_active()：普通时段、跨凌晨时段、边界值
  4. Watchlist / TrendPool 管理工作流
  5. WatchlistItem 新增的区间一致性校验（bug fix 验证）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from strategies.ema_scanner import (
    check_ema_crossover,
    check_3bar_breakout,
    calculate_stop_loss,
)
from strategies.semi_auto.state import (
    WatchlistItem,
    TrendPoolItem,
    PendingSignal,
    DndTimeSlot,
)
from storage.local_json import LocalJsonStorage


# ─────────────────────────────────────────────────────────────────────
# 共用 Fixture
# ─────────────────────────────────────────────────────────────────────

PROFILE = "integration_profile"
EURUSD = "EUR_USD"


@pytest.fixture
def storage(tmp_path):
    return LocalJsonStorage(base_dir=str(tmp_path))


def _make_kline_df(closes, highs=None, lows=None) -> pd.DataFrame:
    """构造标准 K 线 DataFrame"""
    closes = np.array(closes, dtype=float)
    n = len(closes)
    if highs is None:
        highs = closes + 0.001
    if lows is None:
        lows = closes - 0.001
    return pd.DataFrame({
        'datetime': pd.date_range('2026-01-01', periods=n, freq='5min'),
        'open': closes,
        'high': np.array(highs, dtype=float),
        'low': np.array(lows, dtype=float),
        'close': closes,
        'volume': np.ones(n, dtype=int),
    })


# ─────────────────────────────────────────────────────────────────────
# 1. 信号生成管线集成测试
#    OandaDataProvider(mock) → EMA 扫描 → 止损计算 → 保存 PendingSignal
# ─────────────────────────────────────────────────────────────────────

class TestSignalPipeline:
    """
    模拟从获取多周期 K 线到生成并持久化 PendingSignal 的完整流程。
    """

    def _build_m5_df_with_long_crossover(self) -> pd.DataFrame:
        """
        构造包含有效做多穿越的 5M K 线：
          - 200 根稳定在 1.0000（EMA 收敛）
          - 最后两根：0.9990（下方）→ 1.0250（充分向上穿越）
          - high 设高于前3根最高价，确保 3-bar-breakout 通过
        """
        base = 1.0000
        closes = [base] * 200 + [0.9990, 1.0250]
        highs = [base + 0.001] * 200 + [0.9991, 1.0260]
        lows  = [base - 0.001] * 200 + [0.9980, 1.0240]
        return _make_kline_df(closes, highs, lows)

    def test_long_signal_pipeline(self, storage):
        """做多信号：EMA 穿越 + 3K突破 + 止损计算 + 保存 PendingSignal"""
        df = self._build_m5_df_with_long_crossover()

        # ── Phase 2: EMA 扫描 ─────────────────────────────────────────
        atr_val = 0.010  # 模拟 ATR
        direction = 'long'

        crossover = check_ema_crossover(
            df, ema_periods=[20], atr_val=atr_val, direction=direction
        )
        assert crossover, "应检测到做多有效穿越"

        breakout = check_3bar_breakout(df, direction=direction)
        assert breakout, "当前K线高于前3根最高价，应通过突破过滤"

        stop_loss = calculate_stop_loss(df, direction=direction, buffer_pips=0.0005)
        assert stop_loss is not None
        # 止损必须低于当前价格
        current_price = float(df['close'].iloc[-1])
        assert stop_loss < current_price, f"做多止损({stop_loss})应低于当前价({current_price})"

        # ── Phase 3: 构建并保存 PendingSignal ─────────────────────────
        position_size = 10000  # 模拟仓位
        signal = PendingSignal(
            symbol=EURUSD,
            direction=direction,
            entry_price=current_price,
            stop_loss=stop_loss,
            position_size=position_size,
        )
        storage.save_pending_signal(PROFILE, EURUSD, signal.to_dict())

        # ── 验证加载 ───────────────────────────────────────────────────
        loaded = storage.load_pending_signal(PROFILE, EURUSD)
        assert loaded is not None
        restored = PendingSignal.from_dict(loaded)
        assert restored.symbol == EURUSD
        assert restored.direction == 'long'
        assert restored.entry_price == pytest.approx(current_price)
        assert restored.stop_loss == pytest.approx(stop_loss)
        assert restored.position_size == position_size

    def test_short_signal_pipeline(self, storage):
        """做空信号：EMA 穿越 + 3K突破 + 止损计算 + 保存 PendingSignal"""
        base = 1.0000
        closes = [base] * 200 + [1.0010, 0.9750]
        highs  = [base + 0.001] * 200 + [1.0020, 0.9760]
        lows   = [base - 0.001] * 200 + [1.0000, 0.9740]
        df = _make_kline_df(closes, highs, lows)

        atr_val = 0.010
        direction = 'short'

        crossover = check_ema_crossover(df, ema_periods=[20], atr_val=atr_val, direction=direction)
        assert crossover, "应检测到做空有效穿越"

        breakout = check_3bar_breakout(df, direction=direction)
        assert breakout, "当前K线低于前3根最低价，应通过突破过滤"

        stop_loss = calculate_stop_loss(df, direction=direction, buffer_pips=0.0005)
        assert stop_loss is not None
        current_price = float(df['close'].iloc[-1])
        assert stop_loss > current_price, f"做空止损({stop_loss})应高于当前价({current_price})"

        signal = PendingSignal(
            symbol=EURUSD,
            direction=direction,
            entry_price=current_price,
            stop_loss=stop_loss,
            position_size=5000,
        )
        storage.save_pending_signal(PROFILE, EURUSD, signal.to_dict())

        loaded = storage.load_pending_signal(PROFILE, EURUSD)
        assert loaded is not None
        restored = PendingSignal.from_dict(loaded)
        assert restored.direction == 'short'
        assert restored.stop_loss > restored.entry_price

    def test_signal_cancel_workflow(self, storage):
        """信号取消流程：保存 → 取消（删除）→ 再次加载为 None"""
        sig = PendingSignal(
            symbol=EURUSD, direction='long',
            entry_price=1.10, stop_loss=1.08, position_size=1000,
        )
        storage.save_pending_signal(PROFILE, EURUSD, sig.to_dict())
        assert storage.load_pending_signal(PROFILE, EURUSD) is not None

        # 用户执行 /cancel
        storage.delete_pending_signal(PROFILE, EURUSD)
        assert storage.load_pending_signal(PROFILE, EURUSD) is None

    def test_multi_timeframe_data_format_consistency(self):
        """
        验证 get_multi_timeframe 返回的两个周期数据格式兼容 EMA 扫描器。
        通过 mock provider 验证格式约定。
        """
        from data.oanda_candles import OandaDataProvider

        def _candle_row(t, o, h, l, c):
            return {'time': t, 'complete': True, 'volume': 10,
                    'mid': {'o': str(o), 'h': str(h), 'l': str(l), 'c': str(c)}}

        h1_resp = MagicMock()
        h1_resp.raise_for_status = MagicMock()
        h1_resp.json.return_value = {'candles': [
            _candle_row(f'2026-01-01T0{i}:00:00Z', 1.1+i*0.001, 1.101+i*0.001,
                        1.099+i*0.001, 1.1005+i*0.001)
            for i in range(5)
        ]}
        m5_resp = MagicMock()
        m5_resp.raise_for_status = MagicMock()
        m5_resp.json.return_value = {'candles': [
            _candle_row(f'2026-01-01T00:{i*5:02d}:00Z', 1.1, 1.101, 1.099, 1.1005)
            for i in range(10)
        ]}

        with patch('httpx.Client'):
            provider = OandaDataProvider(api_key='test', environment='practice')
        provider._client.get.side_effect = [h1_resp, m5_resp]

        result = provider.get_multi_timeframe(EURUSD, granularities=['H1', 'M5'], count=200)

        required_cols = {'datetime', 'open', 'high', 'low', 'close', 'volume'}
        assert required_cols.issubset(set(result['H1'].columns))
        assert required_cols.issubset(set(result['M5'].columns))
        assert set(result['H1'].columns) == set(result['M5'].columns), \
            "H1 和 M5 的列结构应完全一致"


# ─────────────────────────────────────────────────────────────────────
# 2. DND 生命周期集成测试（bug fix 验证）
# ─────────────────────────────────────────────────────────────────────

class TestDndLifecycle:

    def test_expired_dnd_returns_none_and_cleans_up(self, storage):
        """过期的 DND 条目：load 应返回 None，并自动清理文件"""
        past = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        storage.save_symbol_dnd(PROFILE, EURUSD, past)

        # load 应识别已过期并返回 None
        result = storage.load_symbol_dnd(PROFILE, EURUSD)
        assert result is None, f"过期 DND 应返回 None，实际返回: {result!r}"

        # 过期后再次 load 也是 None（文件已被清理）
        result2 = storage.load_symbol_dnd(PROFILE, EURUSD)
        assert result2 is None

    def test_future_dnd_is_preserved(self, storage):
        """未过期的 DND：load 应返回原始 expiry 字符串"""
        future = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        storage.save_symbol_dnd(PROFILE, EURUSD, future)

        result = storage.load_symbol_dnd(PROFILE, EURUSD)
        assert result == future

    def test_dnd_expiry_boundary(self, storage):
        """刚好过期（expiry == now - 1秒）：应返回 None"""
        just_expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        storage.save_symbol_dnd(PROFILE, EURUSD, just_expired)
        assert storage.load_symbol_dnd(PROFILE, EURUSD) is None

    def test_dnd_15min_workflow(self, storage):
        """模拟 /dnd 15 指令：写入 15 分钟免打扰，然后验证未过期"""
        expiry = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        storage.save_symbol_dnd(PROFILE, EURUSD, expiry)

        loaded = storage.load_symbol_dnd(PROFILE, EURUSD)
        assert loaded is not None, "15分钟后才过期，应正常返回"

        # 手动清除（模拟免打扰结束前用户取消）
        storage.clear_symbol_dnd(PROFILE, EURUSD)
        assert storage.load_symbol_dnd(PROFILE, EURUSD) is None

    def test_multiple_symbols_dnd_independent(self, storage):
        """多品种 DND 相互独立"""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        storage.save_symbol_dnd(PROFILE, 'EUR_USD', future)
        storage.save_symbol_dnd(PROFILE, 'GBP_USD', past)

        assert storage.load_symbol_dnd(PROFILE, 'EUR_USD') == future
        assert storage.load_symbol_dnd(PROFILE, 'GBP_USD') is None


# ─────────────────────────────────────────────────────────────────────
# 3. DndTimeSlot.is_active() 测试
# ─────────────────────────────────────────────────────────────────────

class TestDndTimeSlotIsActive:

    def _dt(self, hh: int, mm: int) -> datetime:
        """构造当天指定 UTC HH:MM 的 datetime"""
        return datetime(2026, 1, 1, hh, mm, 0, tzinfo=timezone.utc)

    def test_same_day_slot_inside(self):
        """12:00–13:00，12:30 在内"""
        slot = DndTimeSlot(start="12:00", end="13:00")
        assert slot.is_active(self._dt(12, 30))

    def test_same_day_slot_before_start(self):
        """12:00–13:00，11:59 不在内"""
        slot = DndTimeSlot(start="12:00", end="13:00")
        assert not slot.is_active(self._dt(11, 59))

    def test_same_day_slot_at_start_boundary(self):
        """12:00–13:00，12:00 恰好在内（闭区间开始）"""
        slot = DndTimeSlot(start="12:00", end="13:00")
        assert slot.is_active(self._dt(12, 0))

    def test_same_day_slot_at_end_boundary(self):
        """12:00–13:00，13:00 不在内（开区间结束）"""
        slot = DndTimeSlot(start="12:00", end="13:00")
        assert not slot.is_active(self._dt(13, 0))

    def test_cross_midnight_slot_in_first_half(self):
        """22:00–06:00（跨凌晨），23:00 在内"""
        slot = DndTimeSlot(start="22:00", end="06:00")
        assert slot.is_active(self._dt(23, 0))

    def test_cross_midnight_slot_in_second_half(self):
        """22:00–06:00，03:00 在内"""
        slot = DndTimeSlot(start="22:00", end="06:00")
        assert slot.is_active(self._dt(3, 0))

    def test_cross_midnight_slot_outside(self):
        """22:00–06:00，12:00 不在内"""
        slot = DndTimeSlot(start="22:00", end="06:00")
        assert not slot.is_active(self._dt(12, 0))

    def test_cross_midnight_slot_at_end_boundary(self):
        """22:00–06:00，06:00 不在内（开区间结束）"""
        slot = DndTimeSlot(start="22:00", end="06:00")
        assert not slot.is_active(self._dt(6, 0))

    def test_same_start_end_is_never_active(self):
        """start == end 视为空时段，永不激活"""
        slot = DndTimeSlot(start="12:00", end="12:00")
        assert not slot.is_active(self._dt(12, 0))
        assert not slot.is_active(self._dt(15, 0))

    def test_default_utc_now(self):
        """无参数时使用系统 UTC 时间，不应抛出异常"""
        slot = DndTimeSlot(start="00:00", end="00:01")
        result = slot.is_active()
        assert isinstance(result, bool)

    def test_multiple_slots_any_logic(self):
        """引擎使用 any() 判断全局 DND：任一时段激活即静默"""
        slots = [
            DndTimeSlot(start="00:00", end="06:00"),
            DndTimeSlot(start="12:00", end="13:00"),
        ]
        check_time = self._dt(0, 30)
        assert any(s.is_active(check_time) for s in slots)

        check_time2 = self._dt(10, 0)
        assert not any(s.is_active(check_time2) for s in slots)


# ─────────────────────────────────────────────────────────────────────
# 4. Watchlist + TrendPool 管理工作流
# ─────────────────────────────────────────────────────────────────────

class TestWatchlistTrendPoolWorkflow:

    def test_add_to_watchlist_then_promote_to_trend_pool(self, storage):
        """
        完整工作流：
          品种加入 Watchlist → H1 扫描触发 → 用户标记 → 加入 TrendPool
        """
        # Step 1: 加入 Watchlist
        watchlist = [
            WatchlistItem(symbol="EUR_USD", range_high=1.12, range_low=1.08),
            WatchlistItem(symbol="GBP_USD"),
        ]
        storage.save_watchlist(PROFILE, [w.to_dict() for w in watchlist])

        loaded = [WatchlistItem.from_dict(d) for d in storage.load_watchlist(PROFILE)]
        assert len(loaded) == 2
        assert loaded[0].symbol == "EUR_USD"

        # Step 2: 价格突破震荡区间，用户标记多头，加入 TrendPool
        trend_item = TrendPoolItem(
            symbol="EUR_USD",
            direction="long",
            h1_ema_period=20,
        )
        storage.save_trend_pool(PROFILE, [trend_item.to_dict()])

        pool = [TrendPoolItem.from_dict(d) for d in storage.load_trend_pool(PROFILE)]
        assert len(pool) == 1
        assert pool[0].symbol == "EUR_USD"
        assert pool[0].direction == "long"
        assert pool[0].h1_ema_period == 20

    def test_remove_from_watchlist(self, storage):
        """从 Watchlist 中移除品种"""
        items = [
            WatchlistItem(symbol="EUR_USD").to_dict(),
            WatchlistItem(symbol="GBP_USD").to_dict(),
            WatchlistItem(symbol="AUD_USD").to_dict(),
        ]
        storage.save_watchlist(PROFILE, items)

        # 模拟 /watch remove GBP_USD
        updated = [d for d in storage.load_watchlist(PROFILE) if d['symbol'] != 'GBP_USD']
        storage.save_watchlist(PROFILE, updated)

        final = [WatchlistItem.from_dict(d) for d in storage.load_watchlist(PROFILE)]
        assert len(final) == 2
        assert all(item.symbol != 'GBP_USD' for item in final)

    def test_clear_trend_pool(self, storage):
        """清空趋势池（模拟品种趋势结束）"""
        items = [
            TrendPoolItem(symbol="EUR_USD", direction="long", h1_ema_period=20).to_dict(),
            TrendPoolItem(symbol="GBP_USD", direction="short", h1_ema_period=60).to_dict(),
        ]
        storage.save_trend_pool(PROFILE, items)
        assert len(storage.load_trend_pool(PROFILE)) == 2

        # 清除单个品种
        remaining = [d for d in storage.load_trend_pool(PROFILE) if d['symbol'] != 'EUR_USD']
        storage.save_trend_pool(PROFILE, remaining)
        assert len(storage.load_trend_pool(PROFILE)) == 1


# ─────────────────────────────────────────────────────────────────────
# 5. WatchlistItem 区间一致性校验（bug fix 验证）
# ─────────────────────────────────────────────────────────────────────

class TestWatchlistItemRangeValidation:

    def test_valid_no_range(self):
        """不设区间应正常创建"""
        item = WatchlistItem(symbol="EUR_USD")
        assert item.range_high is None
        assert item.range_low is None

    def test_valid_both_range(self):
        """同时设置上下限应正常"""
        item = WatchlistItem(symbol="EUR_USD", range_high=1.12, range_low=1.08)
        assert item.range_high == 1.12
        assert item.range_low == 1.08

    def test_only_range_high_raises(self):
        """只设 range_high 不设 range_low 应报错"""
        with pytest.raises(ValueError, match="range_high"):
            WatchlistItem(symbol="EUR_USD", range_high=1.12)

    def test_only_range_low_raises(self):
        """只设 range_low 不设 range_high 应报错"""
        with pytest.raises(ValueError, match="range_low|range_high"):
            WatchlistItem(symbol="EUR_USD", range_low=1.08)

    def test_range_high_less_than_low_raises(self):
        """range_high <= range_low 应报错"""
        with pytest.raises(ValueError, match="range_high"):
            WatchlistItem(symbol="EUR_USD", range_high=1.08, range_low=1.12)

    def test_range_high_equal_low_raises(self):
        """range_high == range_low 应报错"""
        with pytest.raises(ValueError, match="range_high"):
            WatchlistItem(symbol="EUR_USD", range_high=1.10, range_low=1.10)

    def test_range_check_in_engine_simulation(self):
        """
        模拟引擎的震荡区间检查逻辑：
          当前价格在区间内 → 跳过扫描
          当前价格在区间外 → 执行扫描
        """
        item = WatchlistItem(symbol="EUR_USD", range_high=1.12, range_low=1.08)
        current_price_inside = 1.10
        current_price_outside_high = 1.13
        current_price_outside_low = 1.07

        def price_in_range(item: WatchlistItem, price: float) -> bool:
            if item.range_high is None or item.range_low is None:
                return False
            return item.range_low <= price <= item.range_high

        assert price_in_range(item, current_price_inside)
        assert not price_in_range(item, current_price_outside_high)
        assert not price_in_range(item, current_price_outside_low)


# ─────────────────────────────────────────────────────────────────────
# 6. global_dnd 整合 DndTimeSlot 的完整工作流
# ─────────────────────────────────────────────────────────────────────

class TestGlobalDndWorkflow:

    def test_global_dnd_add_and_check(self, storage):
        """添加全局 DND 时段后，验证 is_active() 正常工作"""
        slots = [
            DndTimeSlot(start="00:00", end="06:00"),
            DndTimeSlot(start="12:00", end="13:00"),
        ]
        storage.save_global_dnd(PROFILE, [s.to_dict() for s in slots])

        loaded_dicts = storage.load_global_dnd(PROFILE)
        loaded_slots = [DndTimeSlot.from_dict(d) for d in loaded_dicts]

        # 01:00 应处于全局静默（00:00-06:00）
        check_0100 = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)
        assert any(s.is_active(check_0100) for s in loaded_slots)

        # 12:30 应处于全局静默（12:00-13:00）
        check_1230 = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
        assert any(s.is_active(check_1230) for s in loaded_slots)

        # 09:00 应不在静默期
        check_0900 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        assert not any(s.is_active(check_0900) for s in loaded_slots)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
