"""
Forex专用CommissionInfo

解决Bug #11: Backtrader默认的盈亏计算对非直接报价货币对不正确。
Backtrader默认公式: PnL = size × (newprice - price) × mult
  - 对GBPUSD（直接报价）正确：结果直接为USD
  - 对USDJPY（间接报价）错误：结果为JPY，未转换为USD，导致盈亏放大~155倍
  - 对AUDJPY（交叉货币对）错误：结果为JPY，保证金也算错，导致所有订单被拒

正确公式:
  - 直接报价(XXX/USD): PnL = size × (newprice - price)
  - 间接报价(USD/XXX): PnL = size × (newprice - price) / newprice
  - 交叉货币对(XXX/YYY): PnL = size × (newprice - price) × quote_usd_rate

参考:
  - 经纪商规格: 30倍杠杆, 3.33%保证金, $5/手开仓费
  - Backtrader源码: comminfo.py, brokers/bbroker.py
"""

import backtrader as bt


# ============================================================
# 货币对分类与配置
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
#           需要指定 quote_usd_rate (报价货币兑USD的汇率)
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
    # 交叉货币对: XXX/JPY (报价货币=JPY)
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
    # 交叉货币对: 其他 (根据需要添加)
    # 'EURGBP': 'cross',  # 报价货币=GBP, quote_usd_rate ≈ 1/1.27
    # 'AUDCAD': 'cross',  # 报价货币=CAD, quote_usd_rate ≈ 1/1.36
}

# 交叉货币对的报价货币→USD转换率
# 用于将PnL从报价货币转换为USD
# 使用近似固定值，对回测精度影响极小 (<5%)
CROSS_QUOTE_USD_RATES = {
    'JPY': 1.0 / 150.0,   # 1 JPY ≈ 0.00667 USD (USDJPY ≈ 150)
    'CAD': 1.0 / 1.36,    # 1 CAD ≈ 0.735 USD
    'CHF': 1.0 / 0.88,    # 1 CHF ≈ 1.136 USD
    'GBP': 1.0 / 0.79,    # 1 GBP ≈ 1.266 USD (注意: 1/GBPUSD的倒数)
}

# 从品种名称推断报价货币
def _get_quote_currency(symbol):
    """从品种名称提取报价货币 (后3个字母)"""
    s = symbol.upper().replace('_', '')
    if len(s) >= 6:
        return s[3:6]
    return None


def get_pair_type(symbol):
    """
    根据品种名称返回报价类型

    Args:
        symbol: 品种名称 (如 'USDJPY', 'USD_JPY', 'GBPUSD')

    Returns:
        'direct', 'indirect' 或 'cross'
    """
    return PAIR_TYPE_MAP.get(symbol.upper(), 'direct')


def get_quote_usd_rate(symbol):
    """
    获取交叉货币对的报价货币→USD转换率

    Args:
        symbol: 品种名称

    Returns:
        float: 转换率 (1单位报价货币 = X USD)
               对直接/间接报价返回 0.0 (策略应使用 1/price 自动检测)
               对交叉货币对返回实际转换率
    """
    if get_pair_type(symbol) != 'cross':
        return 0.0  # 非交叉对: 策略使用 1/price 自动模式
    quote_ccy = _get_quote_currency(symbol)
    if quote_ccy and quote_ccy in CROSS_QUOTE_USD_RATES:
        return CROSS_QUOTE_USD_RATES[quote_ccy]
    return 0.0


class ForexCommissionInfo(bt.CommInfoBase):
    """
    Forex专用CommissionInfo

    支持三种报价类型:
    1. 直接报价(direct): XXX/USD (GBPUSD, EURUSD等)
       - size单位: 基础货币 (GBP, EUR等)
       - 价格单位: USD/基础货币
       - 盈亏: PnL(USD) = size × (newprice - price)
       - 持仓价值: abs(size) × price (USD)

    2. 间接报价(indirect): USD/XXX (USDJPY)
       - size单位: USD (基础货币=账户货币)
       - 价格单位: XXX/USD (如 JPY/USD)
       - 盈亏: PnL(USD) = size × (newprice - price) / newprice
       - 持仓价值: abs(size) (已经是USD)

    3. 交叉货币对(cross): XXX/YYY (AUDJPY, EURJPY等)
       - size单位: 基础货币 (AUD, EUR等)
       - 价格单位: YYY/基础货币 (如 JPY/AUD)
       - 盈亏: PnL(USD) = size × (newprice - price) × quote_usd_rate
       - 持仓价值: abs(size) × price × quote_usd_rate (USD)
       - quote_usd_rate: 1单位报价货币 = X USD

    参数:
        pair_type: 'direct', 'indirect' 或 'cross'
        quote_usd_rate: 报价货币→USD转换率 (仅cross类型使用)
        commission_per_lot: 每手每边佣金(USD), 默认0。
            Backtrader在开仓和平仓时各调用一次_getcommission,
            所以Round Turn总佣金 = commission_per_lot × 2。
            例: Blue Guardian实际$5/lot RT → 设为2.5
        lot_size: 1标准手大小, 默认100000
        leverage: 杠杆倍数, 默认30
    """

    params = (
        ('pair_type', 'direct'),        # 报价类型: 'direct', 'indirect', 'cross'
        ('quote_usd_rate', 1.0),        # 报价货币→USD转换率 (仅cross使用)
        ('commission_per_lot', 0.0),     # 每手每边佣金(USD), RT=此值×2
        ('lot_size', 100000),            # 1标准手大小
        ('leverage', 30.0),              # 杠杆倍数
        ('stocklike', False),            # Forex不是股票
        ('commtype', bt.CommInfoBase.COMM_FIXED),
        ('mult', 1.0),
    )

    def _getcommission(self, size, price, pseudoexec):
        """
        计算单边佣金 (Backtrader在开仓和平仓时各调用一次)

        按手数计算: lots × commission_per_lot
        Round Turn总佣金 = 此值 × 2
        """
        if self.p.commission_per_lot == 0:
            return 0.0
        lots = abs(size) / self.p.lot_size
        return lots * self.p.commission_per_lot

    def profitandloss(self, size, price, newprice):
        """
        计算盈亏(USD)

        直接报价(GBPUSD): PnL = size × (newprice - price)
          例: 买入10000 GBP @ 1.2700, 卖出 @ 1.2710
              PnL = 10000 × 0.0010 = $10.00

        间接报价(USDJPY): PnL = size × (newprice - price) / newprice
          例: 买入9452 USD @ 155.110, 止损 @ 155.098 (跌0.012)
              PnL = 9452 × (-0.012) / 155.098 = -$0.73

        交叉货币对(AUDJPY): PnL = size × (newprice - price) × quote_usd_rate
          例: 买入3205 AUD @ 96.156, 止损 @ 95.656 (跌0.5)
              PnL = 3205 × (-0.5) × (1/150) = -$10.68
        """
        if self.p.pair_type == 'indirect':
            if newprice == 0:
                return 0.0
            return size * (newprice - price) / newprice
        elif self.p.pair_type == 'cross':
            return size * (newprice - price) * self.p.quote_usd_rate
        else:
            return size * (newprice - price)

    def cashadjust(self, size, price, newprice):
        """
        现金调整（每根K线的mark-to-market）

        必须与profitandloss保持一致, 否则现金余额会出错
        """
        if self.p.pair_type == 'indirect':
            if newprice == 0:
                return 0.0
            return size * (newprice - price) / newprice
        elif self.p.pair_type == 'cross':
            return size * (newprice - price) * self.p.quote_usd_rate
        else:
            return size * (newprice - price)

    def getvaluesize(self, size, price):
        """
        持仓价值(USD) - 用于保证金计算和组合价值显示

        直接报价: abs(size) × price
          10000 GBP × 1.27 USD/GBP = $12,700

        间接报价: abs(size)
          9452 USD = $9,452

        交叉货币对: abs(size) × price × quote_usd_rate
          3205 AUD × 96.156 JPY/AUD × (1/150 USD/JPY) = $2,055
        """
        if self.p.pair_type == 'indirect':
            return abs(size)
        elif self.p.pair_type == 'cross':
            return abs(size) * price * self.p.quote_usd_rate
        else:
            return abs(size) * price

    def getoperationcost(self, size, price):
        """
        操作成本(保证金) = 持仓价值(USD) / 杠杆
        """
        return self.getvaluesize(size, price) / self.p.leverage

    def get_margin(self, price):
        """
        每单位(1 unit)所需保证金(USD)

        直接报价: price / leverage
        间接报价: 1.0 / leverage
        交叉货币对: price × quote_usd_rate / leverage
        """
        if self.p.pair_type == 'indirect':
            return 1.0 / self.p.leverage
        elif self.p.pair_type == 'cross':
            return price * self.p.quote_usd_rate / self.p.leverage
        else:
            return price / self.p.leverage

    def getvalue(self, position, price):
        """
        当前持仓市值(保证金价值)

        用于组合价值计算
        """
        return self.getvaluesize(position.size, price)

    def getsize(self, price, cash):
        """
        根据可用现金计算最大可交易数量

        cash / margin_per_unit = max_size
        """
        margin = self.get_margin(price)
        if margin == 0:
            return 0
        return int(cash / margin)


# 每品种标准手合约规格 (单位: 基础资产)
# 外汇: 1 手 = 100,000 单位基础货币
# 黄金(XAUUSD): 1 手 = 100 盎司
# 白银(XAGUSD): 1 手 = 5,000 盎司
CONTRACT_SIZE_MAP = {
    'XAUUSD': 100,
    'XAU_USD': 100,
    'XAGUSD': 5000,
    'XAG_USD': 5000,
}


def get_contract_size(symbol):
    """
    返回品种的每手合约大小 (单位数量)

    Args:
        symbol: 品种名称 (如 'XAUUSD', 'GBPUSD')

    Returns:
        int: 每标准手合约大小
    """
    return CONTRACT_SIZE_MAP.get(symbol.upper(), 100000)


def create_forex_commission(symbol, commission_per_lot=0.0, leverage=30.0, lot_size=100000):
    """
    工厂函数: 根据品种创建对应的ForexCommissionInfo

    自动检测品种类型 (direct/indirect/cross) 并设置正确的参数。
    交叉货币对会自动查找 quote_usd_rate。

    Args:
        symbol: 品种名称 (如 'USDJPY', 'GBPUSD', 'AUDJPY')
        commission_per_lot: 每手每边佣金(USD), 默认0。
            Backtrader开+平各调一次, RT总佣金=此值×2。
            Blue Guardian实际$5/lot RT → 传入2.5
        leverage: 杠杆倍数, 默认30
        lot_size: 1标准手大小, 默认100000

    Returns:
        ForexCommissionInfo 实例
    """
    pair_type = get_pair_type(symbol)
    quote_rate = get_quote_usd_rate(symbol)
    return ForexCommissionInfo(
        pair_type=pair_type,
        quote_usd_rate=quote_rate,
        commission_per_lot=commission_per_lot,
        leverage=leverage,
        lot_size=lot_size,
    )
