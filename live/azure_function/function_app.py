"""
Azure Functions Timer Trigger — 实盘交易入口

每 5 分钟执行一次 (CRON: 5 */5 * * * *)，延迟 5 秒等待 K 线 finalize。

环境变量 (Azure App Settings):
    ACTIVE_PROFILE              oanda_demo | blue_guardian
    CFD_OANDA_API_KEY           Oanda API Key
    CFD_OANDA_DEMO_OANDA_ACCOUNT_ID   Oanda Account ID (demo)
    CFD_BLUE_GUARDIAN_TL_EMAIL  TradeLocker email (实盘)
    CFD_BLUE_GUARDIAN_TL_PASSWORD
    CFD_BLUE_GUARDIAN_TL_SERVER
    CFD_BLUE_GUARDIAN_TL_ENVIRONMENT
    CFD_TELEGRAM_BOT_TOKEN      Telegram Bot Token
    CFD_TELEGRAM_CHAT_ID        Telegram Chat ID
    CFD_DRY_RUN                 true | false (默认 false)
    AZURE_STORAGE_CONNECTION    Azure Storage 连接字符串 (状态存储)
"""

import json
import logging
import os
import sys
from datetime import datetime
from storage.azure_table import TABLE_EXECUTION_LOGS
from timezone import timezone

import azure.functions as func

# 部署模式: deploy.sh 会将 core/, data/, execution/, storage/, config/,
# notification/, live/ (engine.py 等) 复制到本目录下，因此只需把当前目录加入 path
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from config.profiles import load_profile
from live.engine import LiveEngine
from notification.telegram import TelegramNotifier
from storage.local_json import LocalJsonStorage

logger = logging.getLogger(__name__)

app = func.FunctionApp()


def _create_executor(config):
    """根据 Profile 创建执行器"""
    if config.executor_type == 'oanda':
        from execution.oanda_executor import OandaExecutor
        return OandaExecutor(
            api_key=config.oanda_api_key,
            account_id=config.oanda_account_id,
            environment=config.oanda_environment,
        )
    elif config.executor_type == 'tradelocker':
        from execution.tradelocker_executor import TradeLockerExecutor
        return TradeLockerExecutor(
            email=config.tl_email,
            password=config.tl_password,
            server=config.tl_server,
            environment=config.tl_environment,
        )
    else:
        raise ValueError(f"Unknown executor type: {config.executor_type}")


def _create_storage():
    """创建状态存储"""
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION', '')
    if conn_str:
        from storage.azure_table import AzureTableStorage
        return AzureTableStorage(connection_string=conn_str)
    else:
        # 回退到本地 JSON (本地调试用)
        logger.warning("AZURE_STORAGE_CONNECTION not set, using LocalJsonStorage")
        return LocalJsonStorage(base_dir='/tmp/cfd_state')


@app.timer_trigger(
    schedule="5 */5 * * * *",
    arg_name="timer",
    run_on_startup=False,
)
def cfd_trading_tick(timer: func.TimerRequest) -> None:
    """
    每 5 分钟交易 tick

    CRON: 5 */5 * * * *
    含义: 每小时的 00:05, 05:05, 10:05, ..., 55:05 执行
    延迟 5 秒的原因: 等待 Oanda M5 K 线 finalize
    """
    if timer.past_due:
        logger.warning("Timer trigger is past due, executing anyway")

    # 获取 Profile
    profile_name = os.environ.get('ACTIVE_PROFILE', 'oanda_demo')
    logger.info(f"Trading tick: profile={profile_name}")

    engine = None
    try:
        config = load_profile(profile_name)

        # DRY_RUN 环境变量覆盖
        if os.environ.get('CFD_DRY_RUN', 'false').lower() == 'true':
            config.dry_run = True

        executor = _create_executor(config)
        storage = _create_storage()

        notifier = None
        if config.enable_telegram and config.telegram_bot_token and config.telegram_chat_id:
            notifier = TelegramNotifier(
                bot_token=config.telegram_bot_token,
                chat_id=config.telegram_chat_id,
            )

        engine = LiveEngine(
            config=config,
            executor=executor,
            storage=storage,
            notifier=notifier,
        )

        result = engine.tick()

        logger.info(f"Tick result: {json.dumps(result, ensure_ascii=False, default=str)}")

        log_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'profile': profile_name,
            'result': result,
            'errors': result.get('errors', None),
        }
        storage._upsert(TABLE_EXECUTION_LOGS, profile_name, f'log_{log_data["timestamp"]}', log_data)

        if result.get('errors'):
            logger.error(f"Tick errors: {result['errors']}")

    except Exception as e:
        logger.exception(f"Trading tick failed: {e}")
        # 尝试发送错误通知
        try:
            tg_token = os.environ.get('CFD_TELEGRAM_BOT_TOKEN', '')
            tg_chat = os.environ.get('CFD_TELEGRAM_CHAT_ID', '')
            if tg_token and tg_chat:
                notifier = TelegramNotifier(tg_token, tg_chat)
                notifier.notify_error(f"Tick 异常: {type(e).__name__}: {e}", profile_name)
                notifier.close()
        except Exception:
            pass
    finally:
        if engine:
            engine.close()
