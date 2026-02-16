"""
Forex专用CommissionInfo

解决Bug #11: Backtrader默认的盈亏计算对USDJPY等间接报价货币对（USD/XXX）不正确。
Backtrader默认公式: PnL = size × (newprice - price) × mult
  - 对GBPUSD（直接报价）正确：结果直接为USD
  - 对USDJPY（间接报价）错误：结果为JPY，未转换为USD，导致盈亏放大~155倍

正确公式:
  - 直接报价(XXX/USD): PnL = size × (newprice - price)
  - 间接报价(USD/XXX): PnL = size × (newprice - price) / newprice

参考:
  - 经纪商规格: 30倍杠杆, 3.33%保证金, $5/手开仓费
  - Backtrader源码: comminfo.py, brokers/bbroker.py
"""

import backtrader as bt


# 货币对报价类型映射
# direct: 报价货币=账户货币(USD)，如 GBPUSD, EURUSD, AUDUSD, XAUUSD, XAGUSD
# indirect: 基础货币=账户货币(USD)，如 USDJPY
PAIR_TYPE_MAP = {
    'GBPUSD': 'direct',
    'GBP_USD': 'direct',
    'EURUSD': 'direct',
    'EUR_USD': 'direct',
    'AUDUSD': 'direct',
    'AUD_USD': 'direct',
    'XAUUSD': 'direct',
    'XAU_USD': 'direct',
    'XAGUSD': 'direct',
    'XAG_USD': 'direct',
    'USDJPY': 'indirect',
    'USD_JPY': 'indirect',
}


def get_pair_type(symbol):
    """
    根据品种名称返回报价类型

    Args:
        symbol: 品种名称 (如 'USDJPY', 'USD_JPY', 'GBPUSD')

    Returns:
        'direct' 或 'indirect'
    """
    return PAIR_TYPE_MAP.get(symbol.upper(), 'direct')


class ForexCommissionInfo(bt.CommInfoBase):
    """
    Forex专用CommissionInfo

    支持两种报价类型:
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

    参数:
        pair_type: 'direct' 或 'indirect'
        commission_per_lot: 每手佣金(USD), 默认0
        lot_size: 1标准手大小, 默认100000
        leverage: 杠杆倍数, 默认30
    """

    params = (
        ('pair_type', 'direct'),        # 报价类型
        ('commission_per_lot', 0.0),     # 每手佣金(USD)
        ('lot_size', 100000),            # 1标准手大小
        ('leverage', 30.0),              # 杠杆倍数
        ('stocklike', False),            # Forex不是股票
        ('commtype', bt.CommInfoBase.COMM_FIXED),
        ('mult', 1.0),
    )

    def _getcommission(self, size, price, pseudoexec):
        """
        计算佣金

        按手数计算: lots × commission_per_lot
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
              而非默认的 9452 × (-0.012) = -113.42 JPY（被当作USD）
        """
        if self.p.pair_type == 'indirect':
            # 避免除以0
            if newprice == 0:
                return 0.0
            return size * (newprice - price) / newprice
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
        else:
            return size * (newprice - price)

    def getvaluesize(self, size, price):
        """
        持仓价值(USD) - 用于保证金计算和组合价值显示

        直接报价: abs(size) × price (基础货币数量 × USD单价)
        间接报价: abs(size) (已经是USD)
        """
        if self.p.pair_type == 'indirect':
            return abs(size)
        else:
            return abs(size) * price

    def getoperationcost(self, size, price):
        """
        操作成本(保证金) = 持仓价值 / 杠杆

        直接报价: abs(size) × price / leverage
        间接报价: abs(size) / leverage
        """
        return self.getvaluesize(size, price) / self.p.leverage

    def get_margin(self, price):
        """
        每单位(1 unit)所需保证金

        直接报价: price / leverage (1 GBP仓位需要 price USD / leverage)
        间接报价: 1.0 / leverage  (1 USD仓位需要 1 USD / leverage)
        """
        if self.p.pair_type == 'indirect':
            return 1.0 / self.p.leverage
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


def create_forex_commission(symbol, commission_per_lot=0.0, leverage=30.0, lot_size=100000):
    """
    工厂函数: 根据品种创建对应的ForexCommissionInfo

    Args:
        symbol: 品种名称 (如 'USDJPY', 'GBPUSD')
        commission_per_lot: 每手佣金(USD), 默认0
        leverage: 杠杆倍数, 默认30
        lot_size: 1标准手大小, 默认100000

    Returns:
        ForexCommissionInfo 实例
    """
    pair_type = get_pair_type(symbol)
    return ForexCommissionInfo(
        pair_type=pair_type,
        commission_per_lot=commission_per_lot,
        leverage=leverage,
        lot_size=lot_size,
    )
