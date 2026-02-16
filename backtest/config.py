"""
配置参数文件
Configuration parameters for backtest system
"""

# ==================== 数据配置 ====================
DATA_CONFIG = {
    'symbol': 'GBPUSD',
    'timeframe': '5min',
    'start_date': '2025-02-01',
    'end_date': '2026-02-14',
    'data_path': './data/GBP_USD_M5.csv',  # OANDA下载的数据路径
    'test_data_path': './data/EURUSD_5m_test.csv',  # 测试数据路径
}

# ==================== UP/DOWN识别配置 ====================
RANGE_DETECTION_CONFIG = {
    'method': 'donchian',  # 'donchian' or 'support_resistance'
    'lookback_period': 20,  # Donchian通道回看周期（20根K线 = 100分钟）
    'min_range_height': 0.0010,  # 最小区间高度（10 pips）
    'update_frequency': 5,  # 每5根K线更新一次UP/DOWN
}

# ==================== ATR和Buffer配置 ====================
ATR_CONFIG = {
    'period': 14,  # ATR计算周期
    'buffer_multiplier': 0.2,  # Buffer = ATR × 0.2（回调幅度，原始值）
}

# ==================== 策略参数配置 ====================
STRATEGY_CONFIG = {
    'confirm_seconds': 30,  # 突破确认秒数
    'confirm_bars': 3,  # 确认K线数（需要3根K线持续突破，过滤假突破）
    'max_retracement': 0.5,  # 最大回撤幅度（不能跌破中轴）
    'max_wait_bars': 12,  # 最大等待时间（60分钟 = 12根5分钟K线，增加等待时间）
    'trailing_stop_enabled': True,  # 是否启用移动止损
}

# ==================== 风险管理配置 ====================
RISK_CONFIG = {
    'initial_capital': 10000,  # 初始资金（美元）
    'risk_percent': 1.0,  # 每笔交易风险百分比（账户的%）
    'min_lots': 0.01,  # 最小手数（1000单位）
    'max_lots': 10.0,  # 最大手数（1,000,000单位）
    'max_positions': 1,  # 最大同时持仓数
    'spread_pips': 1.0,  # 模拟点差（1 pip）
    'commission': 0,  # 佣金
}

# ==================== 回测配置 ====================
BACKTEST_CONFIG = {
    'cerebro_cash': 10000,  # Cerebro初始资金
    'cerebro_commission': 0.0,  # Cerebro佣金率（已在策略中处理点差）
    'plot_results': False,  # 是否绘制结果图表（终端测试时禁用）
    'save_results': True,  # 是否保存回测报告
}

# ==================== 输出路径配置 ====================
OUTPUT_CONFIG = {
    'reports_dir': './results/reports/',
    'charts_dir': './results/charts/',
    'logs_dir': './results/logs/',
}

# ==================== PinBar识别配置（可选功能）====================
PINBAR_CONFIG = {
    'enabled': False,  # 是否启用PinBar过滤
    'tail_ratio': 2.0,  # 尾部/实体比例
    'body_ratio': 0.3,  # 实体/总长比例
}
