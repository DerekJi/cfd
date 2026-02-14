"""
配置参数文件
Configuration parameters for backtest system
"""

# ==================== 数据配置 ====================
DATA_CONFIG = {
    'symbol': 'EURUSD',
    'timeframe': '5min',
    'start_date': '2025-11-01',
    'end_date': '2026-02-14',
    'data_path': './data/EUR_USD_M5.csv',  # OANDA下载的数据路径
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
    'buffer_multiplier': 0.2,  # Buffer = ATR × 0.2
}

# ==================== 策略参数配置 ====================
STRATEGY_CONFIG = {
    'confirm_seconds': 30,  # 突破确认秒数
    'confirm_bars': 1,  # 确认K线数（30秒 / 5分钟 ≈ 0.1根，向上取整为1根）
    'max_retracement': 0.5,  # 最大回撤幅度（不能跌破中轴）
    'max_wait_bars': 6,  # 最大等待时间（30分钟 = 6根5分钟K线）
    'trailing_stop_enabled': True,  # 是否启用移动止损
}

# ==================== 风险管理配置 ====================
RISK_CONFIG = {
    'initial_capital': 10000,  # 初始资金（美元）
    'position_size': 100000,  # 每单位仓位（1标准手 = 100,000基础货币）
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
