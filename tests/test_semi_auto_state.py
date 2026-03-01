"""
测试 Phase 3 状态管理层

覆盖：
  1. state.py 数据模型：序列化 / 反序列化 / 校验
  2. LocalJsonStorage 半自动策略状态存取（无外部依赖，可直接运行）
"""

import os
import tempfile
import pytest
from datetime import datetime, timezone

from strategies.semi_auto.state import (
    WatchlistItem,
    TrendPoolItem,
    PendingSignal,
    DndTimeSlot,
)
from storage.local_json import LocalJsonStorage


# ─────────────────────────────────────────────
# WatchlistItem
# ─────────────────────────────────────────────

class TestWatchlistItem:
    def test_to_dict_and_from_dict_roundtrip(self):
        item = WatchlistItem(symbol="EUR_USD", range_high=1.1000, range_low=1.0800)
        assert WatchlistItem.from_dict(item.to_dict()) == item

    def test_optional_range_defaults_to_none(self):
        item = WatchlistItem(symbol="GBP_USD")
        assert item.range_high is None
        assert item.range_low is None

    def test_from_dict_accepts_missing_range(self):
        item = WatchlistItem.from_dict({"symbol": "AUD_USD"})
        assert item.symbol == "AUD_USD"
        assert item.range_high is None


# ─────────────────────────────────────────────
# TrendPoolItem
# ─────────────────────────────────────────────

class TestTrendPoolItem:
    def test_to_dict_and_from_dict_roundtrip(self):
        item = TrendPoolItem(
            symbol="EUR_USD",
            direction="long",
            h1_ema_period=21,
            added_at="2026-03-01T08:00:00+00:00",
        )
        assert TrendPoolItem.from_dict(item.to_dict()) == item

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="direction"):
            TrendPoolItem(symbol="EUR_USD", direction="buy", h1_ema_period=21)

    def test_added_at_defaults_to_utc_now(self):
        before = datetime.now(timezone.utc).isoformat()
        item = TrendPoolItem(symbol="EUR_USD", direction="short", h1_ema_period=55)
        after = datetime.now(timezone.utc).isoformat()
        assert before <= item.added_at <= after


# ─────────────────────────────────────────────
# PendingSignal
# ─────────────────────────────────────────────

class TestPendingSignal:
    def test_to_dict_and_from_dict_roundtrip(self):
        sig = PendingSignal(
            symbol="XAU_USD",
            direction="long",
            entry_price=2300.0,
            stop_loss=2280.0,
            position_size=100,
            created_at="2026-03-01T10:00:00+00:00",
        )
        assert PendingSignal.from_dict(sig.to_dict()) == sig

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="direction"):
            PendingSignal(
                symbol="EUR_USD",
                direction="sell",
                entry_price=1.10,
                stop_loss=1.08,
                position_size=1000,
            )

    def test_zero_position_size_raises(self):
        with pytest.raises(ValueError, match="position_size"):
            PendingSignal(
                symbol="EUR_USD",
                direction="short",
                entry_price=1.10,
                stop_loss=1.12,
                position_size=0,
            )


# ─────────────────────────────────────────────
# DndTimeSlot
# ─────────────────────────────────────────────

class TestDndTimeSlot:
    def test_to_dict_and_from_dict_roundtrip(self):
        slot = DndTimeSlot(start="21:00", end="22:30")
        assert DndTimeSlot.from_dict(slot.to_dict()) == slot

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            DndTimeSlot(start="9:00", end="22:00")   # 单数字时

    def test_invalid_non_digits_raises(self):
        with pytest.raises(ValueError):
            DndTimeSlot(start="ab:cd", end="22:00")


# ─────────────────────────────────────────────
# LocalJsonStorage — 半自动策略状态
# ─────────────────────────────────────────────

@pytest.fixture
def storage(tmp_path):
    return LocalJsonStorage(base_dir=str(tmp_path))


PROFILE = "test_profile"
SYMBOL = "EUR_USD"


class TestLocalJsonStorageSemiAuto:

    # ---- 观察列表 ----

    def test_watchlist_empty_on_init(self, storage):
        assert storage.load_watchlist(PROFILE) == []

    def test_watchlist_save_and_load(self, storage):
        items = [
            WatchlistItem(symbol="EUR_USD", range_high=1.10, range_low=1.08).to_dict(),
            WatchlistItem(symbol="GBP_USD").to_dict(),
        ]
        storage.save_watchlist(PROFILE, items)
        loaded = storage.load_watchlist(PROFILE)
        assert loaded == items

    def test_watchlist_overwrite(self, storage):
        storage.save_watchlist(PROFILE, [WatchlistItem("EUR_USD").to_dict()])
        storage.save_watchlist(PROFILE, [WatchlistItem("AUD_USD").to_dict()])
        loaded = storage.load_watchlist(PROFILE)
        assert len(loaded) == 1
        assert loaded[0]["symbol"] == "AUD_USD"

    # ---- 趋势激活池 ----

    def test_trend_pool_empty_on_init(self, storage):
        assert storage.load_trend_pool(PROFILE) == []

    def test_trend_pool_save_and_load(self, storage):
        items = [
            TrendPoolItem(symbol="EUR_USD", direction="long", h1_ema_period=21).to_dict()
        ]
        storage.save_trend_pool(PROFILE, items)
        loaded = storage.load_trend_pool(PROFILE)
        assert len(loaded) == 1
        restored = TrendPoolItem.from_dict(loaded[0])
        assert restored.symbol == "EUR_USD"
        assert restored.direction == "long"
        assert restored.h1_ema_period == 21

    # ---- 待确认信号 ----

    def test_pending_signal_none_on_init(self, storage):
        assert storage.load_pending_signal(PROFILE, SYMBOL) is None

    def test_pending_signal_save_load_delete(self, storage):
        sig = PendingSignal(
            symbol=SYMBOL,
            direction="short",
            entry_price=1.09,
            stop_loss=1.11,
            position_size=5000,
        )
        storage.save_pending_signal(PROFILE, SYMBOL, sig.to_dict())
        loaded = storage.load_pending_signal(PROFILE, SYMBOL)
        assert loaded is not None
        restored = PendingSignal.from_dict(loaded)
        assert restored.symbol == SYMBOL
        assert restored.direction == "short"
        assert restored.entry_price == pytest.approx(1.09)

        storage.delete_pending_signal(PROFILE, SYMBOL)
        assert storage.load_pending_signal(PROFILE, SYMBOL) is None

    def test_delete_nonexistent_signal_is_noop(self, storage):
        storage.delete_pending_signal(PROFILE, "XYZ_USD")  # should not raise

    # ---- 单品种免打扰 ----

    def test_symbol_dnd_none_on_init(self, storage):
        assert storage.load_symbol_dnd(PROFILE, SYMBOL) is None

    def test_symbol_dnd_save_load_clear(self, storage):
        expiry = "2026-03-01T12:00:00+00:00"
        storage.save_symbol_dnd(PROFILE, SYMBOL, expiry)
        assert storage.load_symbol_dnd(PROFILE, SYMBOL) == expiry

        storage.clear_symbol_dnd(PROFILE, SYMBOL)
        assert storage.load_symbol_dnd(PROFILE, SYMBOL) is None

    def test_clear_nonexistent_symbol_dnd_is_noop(self, storage):
        storage.clear_symbol_dnd(PROFILE, "XYZ_USD")  # should not raise

    # ---- 全局免打扰时段 ----

    def test_global_dnd_empty_on_init(self, storage):
        assert storage.load_global_dnd(PROFILE) == []

    def test_global_dnd_save_and_load(self, storage):
        slots = [
            DndTimeSlot(start="21:00", end="22:00").to_dict(),
            DndTimeSlot(start="04:00", end="05:00").to_dict(),
        ]
        storage.save_global_dnd(PROFILE, slots)
        loaded = storage.load_global_dnd(PROFILE)
        assert loaded == slots

    def test_global_dnd_overwrite(self, storage):
        storage.save_global_dnd(PROFILE, [DndTimeSlot("01:00", "02:00").to_dict()])
        storage.save_global_dnd(PROFILE, [])
        assert storage.load_global_dnd(PROFILE) == []
