"""
外汇工具函数 — 纯 Python 版本

从 backtest/utils/forex_commission.py 提取，不依赖 Backtrader。
提供货币对分类、PnL 转换率、头寸价值计算等功能。
"""

from typing import Optional


# ============================================================
# 货币对分类
# ============================================================
#
# direct:   报价货币=账户货币(USD)   如 GBPUSD, EURUSD, AUDUSD
#           PnL(USD) = size × Δprice
#
# indirect: 基础货币=账户货币(USD)   如 USDJPY
#           PnL(USD) = size × Δprice / newprice
#
# cross:    USD不参与                如 AUDJPY, EURJPY, GBPJPY
#           PnL(USD) = size × Δprice × quote_usd_rate
# ============================================================

PAIR_TYPE_MAP = {
    # 直接报价: XXX/USD
    'GBPUSD': 'direct',
    'GBP_USD': 'direct',
    'EURUSD': 'direct',
    'EUR_USD': 'direct',
    'AUDUSD': 'direct',
    'AUD_USD': 'direct',
    'NZDUSD': 'direct',
    'NZD_USD': 'direct',
    'XAUUSD': 'direct',
    'XAU_USD': 'direct',
    'XAGUSD': 'direct',
    'XAG_USD': 'direct',
    # 间接报价: USD/XXX
    'USDJPY': 'indirect',
    'USD_JPY': 'indirect',
    'USDCAD': 'indirect',
    'USD_CAD': 'indirect',
    'USDCHF': 'indirect',
    'USD_CHF': 'indirect',
    # 交叉货币对
    'AUDJPY': 'cross',
    'AUD_JPY': 'cross',
    'EURJPY': 'cross',
    'EUR_JPY': 'cross',
    'GBPJPY': 'cross',
    'GBP_JPY': 'cross',
    'NZDJPY': 'cross',
    'NZD_JPY': 'cross',
    'CADJPY': 'cross',
    'CAD_JPY': 'cross',
    'CHFJPY': 'cross',
    'CHF_JPY': 'cross',
}

# 交叉货币对: 报价货币 → USD 近似转换率
CROSS_QUOTE_USD_RATES = {
    'JPY': 1.0 / 150.0,   # 1 JPY ≈ 0.00667 USD
    'CAD': 1.0 / 1.36,    # 1 CAD ≈ 0.735 USD
    'CHF': 1.0 / 0.88,    # 1 CHF ≈ 1.136 USD
    'GBP': 1.0 / 0.79,    # 1 GBP ≈ 1.266 USD
}


def get_quote_currency(symbol: str) -> Optional[str]:
    """从品种名称提取报价货币 (后3个字母)"""
    s = symbol.upper().replace('_', '')
    if len(s) >= 6:
        return s[3:6]
    return None


def get_base_currency(symbol: str) -> Optional[str]:
    """从品种名称提取基础货币 (前3个字母)"""
    s = symbol.upper().replace('_', '')
    if len(s) >= 6:
        return s[0:3]
    return None


def get_pair_type(symbol: str) -> str:
    """
    根据品种名称返回报价类型

    Args:
        symbol: 品种名称 (如 'USDJPY', 'USD_JPY', 'GBPUSD')

    Returns:
        'direct', 'indirect' 或 'cross'
    """
    return PAIR_TYPE_MAP.get(symbol.upper(), 'direct')


def get_quote_usd_rate(symbol: str) -> float:
    """
    获取交叉货币对的报价货币 → USD 转换率

    Returns:
        float: 对直接/间接报价返回 0.0
               对交叉货币对返回近似转换率
    """
    if get_pair_type(symbol) != 'cross':
        return 0.0
    quote_ccy = get_quote_currency(symbol)
    if quote_ccy and quote_ccy in CROSS_QUOTE_USD_RATES:
        return CROSS_QUOTE_USD_RATES[quote_ccy]
    return 0.0


def get_pnl_factor(symbol: str, current_price: float) -> float:
    """
    计算 PnL 转换因子 — 将原始盈亏转换为 USD

    PnL(USD) = size × Δprice × pnl_factor

    Args:
        symbol: 品种名称
        current_price: 当前价格 (用于间接报价)

    Returns:
        float: PnL 转换因子
          - direct:   1.0
          - indirect: 1.0 / current_price
          - cross:    quote_usd_rate
    """
    pair_type = get_pair_type(symbol)

    if pair_type == 'direct':
        return 1.0
    elif pair_type == 'indirect':
        if current_price == 0:
            return 0.0
        return 1.0 / current_price
    elif pair_type == 'cross':
        rate = get_quote_usd_rate(symbol)
        return rate if rate > 0 else 0.0

    return 1.0


def calculate_margin(symbol: str, size: float, price: float,
                     leverage: float = 30.0) -> float:
    """
    计算所需保证金 (USD)

    Args:
        symbol: 品种名称
        size: 头寸大小 (单位数)
        price: 当前价格
        leverage: 杠杆倍数

    Returns:
        float: 保证金 (USD)
    """
    pair_type = get_pair_type(symbol)
    abs_size = abs(size)

    if pair_type == 'direct':
        # 持仓价值 = size × price (USD)
        value = abs_size * price
    elif pair_type == 'indirect':
        # 持仓价值 = size (已经是 USD)
        value = abs_size
    elif pair_type == 'cross':
        # 持仓价值 = size × price × quote_usd_rate
        rate = get_quote_usd_rate(symbol)
        value = abs_size * price * rate
    else:
        value = abs_size * price

    return value / leverage


def normalize_symbol(symbol: str, target_format: str = 'oanda') -> str:
    """
    标准化品种名称格式

    Args:
        symbol: 输入品种名 (如 'GBPUSD', 'GBP_USD', 'gbpusd')
        target_format: 'oanda' → 'GBP_USD', 'standard' → 'GBPUSD'

    Returns:
        标准化后的品种名
    """
    s = symbol.upper().replace('_', '')

    if len(s) < 6:
        return symbol.upper()

    base = s[:3]
    quote = s[3:6]

    if target_format == 'oanda':
        return f'{base}_{quote}'
    else:
        return f'{base}{quote}'
