"""
仓位计算器 — 纯 Python 版本

从 backtest/strategies/trend_filter_strategy_v1.py._calculate_position_size() 提取。
所有防护逻辑保持不变：最小止损距离、滑点保护、ATR 仓位上限、保证金限制。
"""

from typing import Optional
from core.forex_utils import get_pair_type, get_quote_usd_rate, calculate_margin


# ============================================================
# 常量 — 与回测策略完全一致
# ============================================================

SLIPPAGE_PROTECTION = 3.0       # 最坏情况滑点倍数
MIN_STOP_ATR_RATIO = 0.15       # 止损距离最小 = ATR × 15%
MAX_SINGLE_LOSS_PCT = 0.01      # 单笔最大亏损 = 账户 1%
ATR_WORST_CASE = 2.5            # 最坏退场距离 = 2.5×ATR
MAX_MARGIN_RATIO = 0.80         # 保证金最多用可用资金 80%
DEFAULT_LEVERAGE = 30.0         # 默认杠杆
LOT_SIZE = 100000               # 1 标准手


def calculate_position_size(
    symbol: str,
    entry_price: float,
    stop_loss: float,
    short: bool,
    total_account_size: float,
    risk_percent: float,
    num_symbols: int,
    current_atr: float,
    cash_available: float,
    min_lot: float = 0.01,
    max_lot: float = 10.0,
    leverage: float = DEFAULT_LEVERAGE,
    quote_usd_rate: Optional[float] = None,
    debug: bool = False,
) -> float:
    """
    计算仓位大小 (单位: units)

    逻辑与回测策略 _calculate_position_size() 完全一致。

    Args:
        symbol:             品种名 (如 'GBP_USD')
        entry_price:        入场价格
        stop_loss:          止损价格
        short:              是否做空
        total_account_size: 总账户规模 (USD / AUD 等账户货币)
        risk_percent:       单品种单笔风险% (如 1.0 = 1%)
        num_symbols:        同时交易品种数
        current_atr:        当前 ATR 值
        cash_available:     可用现金
        min_lot:            最小手数 (默认 0.01)
        max_lot:            最大手数 (默认 10.0)
        leverage:           杠杆倍数 (默认 30)
        quote_usd_rate:     交叉货币对的 quote→USD 汇率 (None=自动检测)
        debug:              是否输出调试信息

    Returns:
        float: 仓位大小 (units)。0 表示拒绝交易。
    """
    # ---- 风险金额 ----
    risk_amount = (total_account_size * risk_percent / 100.0) / num_symbols

    # ---- 止损距离 ----
    if short:
        stop_distance = stop_loss - entry_price
    else:
        stop_distance = entry_price - stop_loss

    if stop_distance <= 0:
        return 0.0

    # ---- 最小止损距离 ----
    min_stop_distance = current_atr * MIN_STOP_ATR_RATIO
    if stop_distance < min_stop_distance:
        if debug:
            print(f"  ⚠️  止损距离 {stop_distance:.5f} < 最小 {min_stop_distance:.5f} (ATR×{MIN_STOP_ATR_RATIO}), 拒绝")
        return 0.0

    # ---- PnL 因子 ----
    if quote_usd_rate is None:
        quote_usd_rate = get_quote_usd_rate(symbol)

    if quote_usd_rate > 0:
        pnl_factor = quote_usd_rate
    else:
        # direct/indirect 统一用 1/entry_price
        pnl_factor = 1.0 / entry_price

    # ---- 基本仓位 ----
    size = risk_amount / (stop_distance * pnl_factor * SLIPPAGE_PROTECTION)

    # ---- ATR 仓位上限 (Bug #12 修复) ----
    max_single_loss = total_account_size * MAX_SINGLE_LOSS_PCT
    max_safe_size = max_single_loss / (current_atr * ATR_WORST_CASE * pnl_factor)

    if size > max_safe_size:
        if debug:
            print(f"  ⚠️  ATR 仓位上限: {size:.0f} → {max_safe_size:.0f}")
        size = max_safe_size

    # ---- 最小手数风险检查 (Bug #7 修复) ----
    min_size = min_lot * LOT_SIZE
    if size < min_size:
        max_loss_with_min_size = min_size * stop_distance * pnl_factor * SLIPPAGE_PROTECTION
        if max_loss_with_min_size > risk_amount * 1.5:
            if debug:
                print(f"  ⚠️  最小仓位风险 ${max_loss_with_min_size:.2f} > 1.5×风险 ${risk_amount*1.5:.2f}, 拒绝")
            return 0.0

    # ---- 保证金限制 (Bug #10 修复) ----
    margin_needed = calculate_margin(symbol, size, entry_price, leverage)
    max_margin = cash_available * MAX_MARGIN_RATIO

    if margin_needed > max_margin:
        scale = max_margin / margin_needed
        if debug:
            print(f"  ⚠️  保证金限制: {size:.0f} → {size*scale:.0f}")
        size = size * scale

    # ---- 手数限制 ----
    lots = size / LOT_SIZE
    lots = max(min_lot, min(lots, max_lot))
    size = lots * LOT_SIZE

    if debug:
        print(f"  📐 仓位: {size:.0f} units ({lots:.2f} 手), 风险 ${risk_amount:.2f}")

    return size
