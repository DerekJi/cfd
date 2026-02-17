"""
命令行测试入口

用于本地手动触发实盘引擎，调试验证全流程。

用法:
    # dry-run 模式 (不实际下单)
    python -m live.cli --profile oanda_demo --dry-run

    # 单次执行 + 实际下单
    python -m live.cli --profile oanda_demo

    # Blue Guardian dry-run
    python -m live.cli --profile blue_guardian --dry-run

    # 指定本地存储目录
    python -m live.cli --profile oanda_demo --dry-run --state-dir ./local_state

环境变量:
    CFD_OANDA_API_KEY          Oanda API Key
    CFD_OANDA_DEMO_OANDA_ACCOUNT_ID   Oanda Account ID
    CFD_TELEGRAM_BOT_TOKEN     Telegram Bot Token
    CFD_TELEGRAM_CHAT_ID       Telegram Chat ID
"""

import argparse
import json
import logging
import sys

from config.profiles import load_profile
from execution.oanda_executor import OandaExecutor
from live.engine import LiveEngine
from notification.telegram import TelegramNotifier
from storage.local_json import LocalJsonStorage


def create_executor(config):
    """根据 Profile 创建执行器"""
    if config.executor_type == 'oanda':
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


def main():
    parser = argparse.ArgumentParser(description='CFD 实盘交易引擎 — CLI 测试')
    parser.add_argument(
        '--profile', '-p',
        choices=['oanda_demo', 'blue_guardian'],
        default='oanda_demo',
        help='交易 Profile (默认: oanda_demo)',
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Dry-run 模式 (不实际下单)',
    )
    parser.add_argument(
        '--state-dir', '-s',
        default='./local_state',
        help='本地状态存储目录 (默认: ./local_state)',
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='详细日志',
    )
    parser.add_argument(
        '--no-telegram',
        action='store_true',
        help='禁用 Telegram 通知',
    )

    args = parser.parse_args()

    # 日志设置
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # 加载配置
    config = load_profile(args.profile)
    if args.dry_run:
        config.dry_run = True
    if args.no_telegram:
        config.enable_telegram = False

    logger = logging.getLogger(__name__)
    logger.info(f"Profile: {config.profile_name}")
    logger.info(f"Executor: {config.executor_type}")
    logger.info(f"Dry-run: {config.dry_run}")
    logger.info(f"Symbols: {[s.oanda_name for s in config.symbols]}")
    logger.info(f"State dir: {args.state_dir}")

    # 创建组件
    storage = LocalJsonStorage(base_dir=args.state_dir)

    notifier = None
    if config.enable_telegram and config.telegram_bot_token and config.telegram_chat_id:
        notifier = TelegramNotifier(
            bot_token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
        )
        logger.info("Telegram 通知已启用")

    executor = create_executor(config)

    # 创建引擎并执行
    engine = LiveEngine(
        config=config,
        executor=executor,
        storage=storage,
        notifier=notifier,
    )

    try:
        logger.info("=" * 60)
        logger.info("开始执行 tick()...")
        logger.info("=" * 60)

        result = engine.tick()

        logger.info("=" * 60)
        logger.info("执行完成")
        logger.info(f"结果: {json.dumps(result, indent=2, ensure_ascii=False, default=str)}")
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.exception(f"执行异常: {e}")
        sys.exit(1)
    finally:
        engine.close()


if __name__ == '__main__':
    main()
