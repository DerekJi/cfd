# OANDA API 配置文件
# 请填写你的API信息

# API密钥（从 https://www.oanda.com/account/tpa/personal_token 获取）
OANDA_API_KEY = "your-api-key-here"

# 账户ID（可选）
OANDA_ACCOUNT_ID = ""

# 环境类型：practice（模拟） 或 live（真实）
OANDA_ENVIRONMENT = "practice"

# 数据下载配置
DOWNLOAD_CONFIG = {
    "instrument": "EUR_USD",      # 交易品种
    "granularity": "M5",          # 时间周期（M5=5分钟）
    "start_date": "2024-01-01",   # 起始日期
    "end_date": "2026-02-14",     # 结束日期
}
