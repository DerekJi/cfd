"""
双平台 Profile 配置

两个运行模式:
  - oanda_demo:     Oanda 模拟账户 (AUD 100K, 验证阶段)
  - blue_guardian:   Blue Guardian 实盘 (USD 5K, TradeLocker)

行情数据: 两个 Profile 共用 Oanda REST v20。
执行层:   oanda_demo → OandaExecutor, blue_guardian → TradeLockerExecutor。
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SymbolConfig:
    """品种配置"""
    oanda_name: str          # Oanda 格式: 'GBP_USD'
    tradelocker_name: str    # TradeLocker 格式: 'GBPUSD'
    pair_type: str           # 'direct', 'indirect', 'cross'


# 默认交易品种
DEFAULT_SYMBOLS = [
    SymbolConfig(oanda_name='GBP_USD', tradelocker_name='GBPUSD', pair_type='direct'),
    SymbolConfig(oanda_name='USD_JPY', tradelocker_name='USDJPY', pair_type='indirect'),
]


@dataclass
class ProfileConfig:
    """
    交易 Profile 配置

    包含一个 Profile 运行所需的全部参数:
      - 身份标识 (profile_name)
      - Oanda 数据源凭证 (两个 Profile 共用)
      - 执行层凭证 (Oanda 或 TradeLocker)
      - 账户参数 (货币、资金、杠杆、手数限制)
      - 策略参数
      - 风控参数
      - 通知配置
    """

    # ---- 基本信息 ----
    profile_name: str                     # 'oanda_demo' 或 'blue_guardian'
    executor_type: str                    # 'oanda' 或 'tradelocker'
    dry_run: bool = False                 # True = 不实际下单，仅日志

    # ---- Oanda 数据源 (共用) ----
    oanda_api_key: str = ''
    oanda_environment: str = 'practice'   # 'practice' 或 'live'

    # ---- Oanda 执行 (oanda_demo 用) ----
    oanda_account_id: str = ''

    # ---- TradeLocker 执行 (blue_guardian 用) ----
    tl_email: str = ''
    tl_password: str = ''
    tl_server: str = ''
    tl_environment: str = ''              # TradeLocker 环境 URL

    # ---- 账户参数 ----
    account_currency: str = 'USD'
    account_size: float = 5000.0
    leverage: float = 30.0
    min_lot: float = 0.01                 # 最小手数
    max_lot: float = 10.0                 # 最大手数
    min_units: int = 1000                 # 最小单位数

    # ---- 交易品种 ----
    symbols: List[SymbolConfig] = field(default_factory=lambda: list(DEFAULT_SYMBOLS))

    # ---- 策略参数 ----
    risk_percent: float = 1.0             # 单品种单笔风险 %

    # ---- 策略配置 ----
    strategies: dict = field(default_factory=lambda: {
        "trend_filter": {
            "param1": "value1",
            "param2": "value2",
        },
        "dual_direction_trend": {
            "param1": "value1",
            "param2": "value2",
        },
    })

    # ---- Blue Guardian 风控 ----
    enable_bg_risk_limits: bool = False
    bg_max_single_loss_pct: float = 0.01  # 1%
    bg_max_daily_loss_pct: float = 0.03   # 3%
    bg_max_total_drawdown_pct: float = 0.06  # 6%

    # ---- Telegram 通知 ----
    telegram_bot_token: str = ''
    telegram_chat_id: str = ''
    enable_telegram: bool = False

    @property
    def num_symbols(self) -> int:
        return len(self.symbols)

    def get_symbol_name(self, symbol_config: SymbolConfig) -> str:
        """根据执行器类型返回对应的品种名"""
        if self.executor_type == 'tradelocker':
            return symbol_config.tradelocker_name
        return symbol_config.oanda_name


def load_profile(profile_name: str) -> ProfileConfig:
    """
    从环境变量加载 Profile 配置

    环境变量命名规则:
      CFD_{PROFILE}_{KEY}
      例: CFD_OANDA_DEMO_API_KEY, CFD_BLUE_GUARDIAN_TL_EMAIL

    也支持通用变量:
      CFD_OANDA_API_KEY        — Oanda 数据源 (共用)
      CFD_TELEGRAM_BOT_TOKEN   — Telegram 通知 (共用)
      CFD_TELEGRAM_CHAT_ID

    Args:
        profile_name: 'oanda_demo' 或 'blue_guardian'

    Returns:
        ProfileConfig
    """
    def env(key: str, default: str = '') -> str:
        """优先读 Profile 专用变量，再读通用变量"""
        prefix = f'CFD_{profile_name.upper()}_'
        val = os.environ.get(prefix + key, '')
        if val:
            return val
        return os.environ.get(f'CFD_{key}', default)

    # Oanda 数据源凭证 (两个 Profile 共用)
    oanda_api_key = env('OANDA_API_KEY')
    oanda_env = env('OANDA_ENVIRONMENT', 'practice')

    # Telegram (共用)
    tg_token = env('TELEGRAM_BOT_TOKEN')
    tg_chat = env('TELEGRAM_CHAT_ID')

    if profile_name == 'oanda_demo':
        return ProfileConfig(
            profile_name='oanda_demo',
            executor_type='oanda',
            dry_run=env('DRY_RUN', 'false').lower() == 'true',
            oanda_api_key=oanda_api_key,
            oanda_environment=oanda_env,
            oanda_account_id=env('OANDA_ACCOUNT_ID'),
            account_currency='AUD',
            account_size=100_000.0,
            leverage=30.0,
            min_lot=0.0,      # Oanda 无最小手数限制
            max_lot=100.0,
            min_units=1,      # Oanda 最小 1 unit
            risk_percent=float(env('RISK_PERCENT', '1.0')),
            enable_bg_risk_limits=False,
            telegram_bot_token=tg_token,
            telegram_chat_id=tg_chat,
            enable_telegram=bool(tg_token and tg_chat),
        )

    elif profile_name == 'blue_guardian':
        return ProfileConfig(
            profile_name='blue_guardian',
            executor_type='tradelocker',
            dry_run=env('DRY_RUN', 'false').lower() == 'true',
            oanda_api_key=oanda_api_key,
            oanda_environment=oanda_env,
            tl_email=env('TL_EMAIL'),
            tl_password=env('TL_PASSWORD'),
            tl_server=env('TL_SERVER'),
            tl_environment=env('TL_ENVIRONMENT'),
            account_currency='USD',
            account_size=5_000.0,
            leverage=30.0,
            min_lot=0.01,
            max_lot=10.0,
            min_units=1000,
            risk_percent=float(env('RISK_PERCENT', '1.0')),
            enable_bg_risk_limits=True,
            bg_max_single_loss_pct=0.01,
            bg_max_daily_loss_pct=0.03,
            bg_max_total_drawdown_pct=0.06,
            telegram_bot_token=tg_token,
            telegram_chat_id=tg_chat,
            enable_telegram=bool(tg_token and tg_chat),
        )

    else:
        raise ValueError(f"Unknown profile: {profile_name}")
