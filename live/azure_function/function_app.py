"""
Azure Functions — 实盘交易入口 + 半自动 EMA 趋势跟踪策略

全自动策略:
  cfd_trading_tick            每 5 分钟 (CRON: 5 */5 * * * *)

半自动策略 (Phase 7 新增):
  semi_auto_h1_scan           每小时整点后 5 秒 (CRON: 5 0 * * * *)
  semi_auto_5m_scan           每 5 分钟后 10 秒 (CRON: 10 */5 * * * *)
  telegram_webhook            HTTP Trigger，接收 Telegram Bot Webhook 推送

环境变量 (Azure App Settings):
    ACTIVE_PROFILE                    oanda_demo | blue_guardian
    CFD_OANDA_API_KEY                 Oanda API Key
    CFD_OANDA_ENVIRONMENT             practice | live
    CFD_OANDA_DEMO_OANDA_ACCOUNT_ID   Oanda Account ID (demo)
    CFD_BLUE_GUARDIAN_TL_EMAIL        TradeLocker email (实盘)
    CFD_BLUE_GUARDIAN_TL_PASSWORD
    CFD_BLUE_GUARDIAN_TL_SERVER
    CFD_BLUE_GUARDIAN_TL_ENVIRONMENT
    CFD_TELEGRAM_BOT_TOKEN            Telegram Bot Token
    CFD_TELEGRAM_CHAT_ID              Telegram Chat ID（同时作为授权 chat_id）
    CFD_DRY_RUN                       true | false (默认 false)
    AZURE_STORAGE_CONNECTION          Azure Storage 连接字符串 (状态存储)
    --- 半自动策略专用 ---
    SA_PROFILE                        半自动策略使用的 Profile（默认 oanda_demo）
    CFD_SA_ACCOUNT_SIZE               账户规模（USD，默认 100000）
    CFD_TELEGRAM_WEBHOOK_SECRET       Webhook 安全校验 Token（可选）
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


# ==============================================================
# 半自动策略公共工厂
# ==============================================================

def _create_semi_auto_components():
    """
    创建半自动策略所需的全部组件。

    Returns
    -------
    tuple: (data_provider, executor, storage, notifier, profile, account_size)
    调用方负责在 finally 块中对各对象调用 close()。
    """
    from data.oanda_candles import OandaDataProvider
    from execution.oanda_executor import OandaExecutor

    sa_profile   = os.environ.get('SA_PROFILE', 'oanda_demo')
    account_size = float(os.environ.get('CFD_SA_ACCOUNT_SIZE', '100000'))

    # 半自动策略固定使用 Oanda；按 SA_PROFILE 前缀或通用 key 读取凭证
    prefix = f'CFD_{sa_profile.upper()}_OANDA_'
    oanda_api_key    = os.environ.get(f'{prefix}API_KEY')    or os.environ.get('CFD_OANDA_API_KEY', '')
    oanda_account_id = os.environ.get(f'{prefix}ACCOUNT_ID') or os.environ.get('CFD_OANDA_DEMO_OANDA_ACCOUNT_ID', '')
    oanda_env        = os.environ.get(f'{prefix}ENVIRONMENT') or os.environ.get('CFD_OANDA_ENVIRONMENT', 'practice')

    data_provider = OandaDataProvider(api_key=oanda_api_key, environment=oanda_env)
    executor      = OandaExecutor(api_key=oanda_api_key, account_id=oanda_account_id, environment=oanda_env)
    storage       = _create_storage()

    tg_token = os.environ.get('CFD_TELEGRAM_BOT_TOKEN', '')
    tg_chat  = os.environ.get('CFD_TELEGRAM_CHAT_ID', '')
    notifier = TelegramNotifier(bot_token=tg_token, chat_id=tg_chat) if (tg_token and tg_chat) else None

    return data_provider, executor, storage, notifier, sa_profile, account_size


def _build_semi_auto_engine(data_provider, executor, storage, notifier, profile, account_size):
    """组装 SemiAutoEngine，从 storage 中读取持久化的 EMA 周期设置。"""
    from live.semi_auto_engine import SemiAutoEngine, DEFAULT_EMA_H1, DEFAULT_EMA_5M

    settings = storage.load_fsm_state(profile, '__sa_settings__') or {}
    ema_h1   = settings.get('ema_h1', DEFAULT_EMA_H1)
    ema_5m   = settings.get('ema_5m', DEFAULT_EMA_5M)

    return SemiAutoEngine(
        data_provider=data_provider,
        executor=executor,
        storage=storage,
        notifier=notifier,
        profile=profile,
        account_size=account_size,
        ema_h1_periods=ema_h1,
        ema_5m_periods=ema_5m,
    )


# ==============================================================
# H1 扫描 — 每小时触发
# ==============================================================

@app.timer_trigger(
    schedule="5 0 * * * *",
    arg_name="timer_h1",
    run_on_startup=False,
)
def semi_auto_h1_scan(timer_h1: func.TimerRequest) -> None:
    """
    半自动策略 H1 K 线扫描

    CRON: 5 0 * * * *
    每小时的 :00:05 执行，等待 H1 K 线 finalize。
    遍历 Watchlist，检测 H1 EMA 穿越信号，触发时发图通知。
    """
    if timer_h1.past_due:
        logger.warning("[semi_auto_h1_scan] Timer past due, executing anyway")

    data_provider = executor = storage = notifier = engine = None
    try:
        data_provider, executor, storage, notifier, profile, account_size = \
            _create_semi_auto_components()
        engine = _build_semi_auto_engine(
            data_provider, executor, storage, notifier, profile, account_size
        )
        result = engine.tick_h1()
        logger.info(
            f"[semi_auto_h1_scan] done: triggered={result.get('triggered')}, "
            f"skipped={len(result.get('skipped', []))}, "
            f"errors={result.get('errors')}"
        )
    except Exception as e:
        logger.exception(f"[semi_auto_h1_scan] failed: {e}")
        if notifier:
            try:
                notifier._send(f"🚨 H1扫描异常: {type(e).__name__}: {e}")
            except Exception:
                pass
    finally:
        for obj in (engine, data_provider, executor, notifier):
            try:
                if obj and hasattr(obj, 'close'):
                    obj.close()
            except Exception:
                pass


# ==============================================================
# 5M 扫描 — 每 5 分钟触发
# ==============================================================

@app.timer_trigger(
    schedule="10 */5 * * * *",
    arg_name="timer_5m",
    run_on_startup=False,
)
def semi_auto_5m_scan(timer_5m: func.TimerRequest) -> None:
    """
    半自动策略 5M K 线扫描

    CRON: 10 */5 * * * *
    每 5 分钟后 10 秒执行，比全自动 tick 晚 5 秒，错开资源争抢。
    遍历趋势激活池，检测 5M 顺势信号，触发时保存 PendingSignal 并发图通知。
    """
    if timer_5m.past_due:
        logger.warning("[semi_auto_5m_scan] Timer past due, executing anyway")

    data_provider = executor = storage = notifier = engine = None
    try:
        data_provider, executor, storage, notifier, profile, account_size = \
            _create_semi_auto_components()
        engine = _build_semi_auto_engine(
            data_provider, executor, storage, notifier, profile, account_size
        )
        result = engine.tick_5m()
        logger.info(
            f"[semi_auto_5m_scan] done: triggered={result.get('triggered')}, "
            f"skipped={len(result.get('skipped', []))}, "
            f"errors={result.get('errors')}"
        )
    except Exception as e:
        logger.exception(f"[semi_auto_5m_scan] failed: {e}")
        if notifier:
            try:
                notifier._send(f"🚨 5M扫描异常: {type(e).__name__}: {e}")
            except Exception:
                pass
    finally:
        for obj in (engine, data_provider, executor, notifier):
            try:
                if obj and hasattr(obj, 'close'):
                    obj.close()
            except Exception:
                pass


# ==============================================================
# Telegram Webhook — HTTP Trigger
# ==============================================================

@app.route(route="telegram_webhook", auth_level=func.AuthLevel.ANONYMOUS)
def telegram_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Telegram Bot Webhook 入口

    Telegram 将每条 Bot Update 以 POST JSON 推送到此 HTTP 端点。
    本函数将 update 转发给 SemiAutoBot 解析并执行对应命令（开仓/平仓等）。

    安全校验:
      若设置了 CFD_TELEGRAM_WEBHOOK_SECRET，则校验请求头
      X-Telegram-Bot-Api-Secret-Token，不匹配则返回 403。
    """
    import json as _json

    # ── 安全校验 ────────────────────────────────────────────────────────────
    expected_secret = os.environ.get('CFD_TELEGRAM_WEBHOOK_SECRET', '')
    if expected_secret:
        received = req.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if received != expected_secret:
            logger.warning("[telegram_webhook] invalid secret token")
            return func.HttpResponse(status_code=403)

    # ── 忽略非 POST 请求 ─────────────────────────────────────────────────────
    if req.method != 'POST':
        return func.HttpResponse('OK', status_code=200)

    # ── 解析 Body ────────────────────────────────────────────────────────────
    try:
        update_dict = req.get_json()
    except Exception:
        logger.warning("[telegram_webhook] invalid JSON body")
        return func.HttpResponse(status_code=400)

    # ── 创建 Bot 并处理 update ───────────────────────────────────────────────
    tg_token = os.environ.get('CFD_TELEGRAM_BOT_TOKEN', '')
    tg_chat  = os.environ.get('CFD_TELEGRAM_CHAT_ID', '')
    if not tg_token or not tg_chat:
        logger.error("[telegram_webhook] missing Telegram credentials")
        return func.HttpResponse(status_code=500)

    data_provider = executor = storage = notifier = engine = None
    try:
        data_provider, executor, storage, notifier, profile, account_size = \
            _create_semi_auto_components()
        engine = _build_semi_auto_engine(
            data_provider, executor, storage, notifier, profile, account_size
        )
        from notification.telegram_bot import SemiAutoBot
        bot = SemiAutoBot(
            bot_token=tg_token,
            authorized_chat_id=tg_chat,
            storage=storage,
            profile=profile,
            engine=engine,
        )
        bot.process_update_sync(update_dict)
        return func.HttpResponse('OK', status_code=200)

    except Exception as e:
        logger.exception(f"[telegram_webhook] error: {e}")
        return func.HttpResponse(status_code=500)
    finally:
        for obj in (engine, data_provider, executor):
            try:
                if obj and hasattr(obj, 'close'):
                    obj.close()
            except Exception:
                pass
