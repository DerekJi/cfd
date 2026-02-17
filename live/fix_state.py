"""
持仓状态修复工具

用途：手动修复Storage中的FSM状态和持仓记录，与实盘持仓同步

使用场景：
1. 平台自动止损/止盈后，FSM状态未同步
2. 手动平仓后，Storage记录未清理
3. 故障恢复后的状态一致性检查

用法：
    python -m live.fix_state --profile oanda_demo
    python -m live.fix_state --profile oanda_demo --dry-run
"""

import argparse
import logging
from datetime import datetime, timezone

from config.profiles import load_profile
from core.fsm import TrendFilterStateMachine
from execution.oanda_executor import OandaExecutor
from storage.azure_table import AzureTableStorage
from storage.local_json import LocalJsonStorage

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


def create_executor(config):
    """创建执行器"""
    return OandaExecutor(
        api_key=config.oanda_api_key,
        account_id=config.oanda_account_id,
        environment=config.oanda_environment,
    )


def create_storage():
    """创建存储（优先Azure Table）"""
    import os
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION')
    if conn_str:
        return AzureTableStorage(conn_str, table_name='cfdState')
    else:
        logger.warning("未设置AZURE_STORAGE_CONNECTION，使用本地JSON存储")
        return LocalJsonStorage(base_dir='./state_data')


def fix_state(profile_name: str, dry_run: bool = False):
    """
    修复持仓状态
    
    Args:
        profile_name: Profile名称
        dry_run: True=只检查不修改
    """
    logger.info(f"========================")
    logger.info(f"持仓状态修复工具")
    logger.info(f"Profile: {profile_name}")
    logger.info(f"模式: {'只读检查' if dry_run else '修复模式'}")
    logger.info(f"========================\n")
    
    # 加载配置
    config = load_profile(profile_name)
    executor = create_executor(config)
    storage = create_storage()
    
    try:
        # 获取实盘持仓
        actual_positions = executor.get_positions()
        actual_position_map = {p.symbol: p for p in actual_positions}
        
        logger.info(f"实盘持仓: {len(actual_positions)} 个")
        for pos in actual_positions:
            logger.info(
                f"  - {pos.symbol}: {pos.side} {pos.units} @ {pos.entry_price:.5f}, "
                f"SL={pos.stop_loss}, PnL={pos.unrealized_pnl:.2f}"
            )
        
        logger.info("")
        
        # 检查每个配置品种
        fixed_count = 0
        error_count = 0
        
        for sym_config in config.symbols:
            symbol = sym_config.oanda_name
            logger.info(f"检查品种: {symbol}")
            
            # 加载Storage中的持仓和FSM状态
            saved_pos = storage.load_position(profile_name, symbol)
            saved_fsm = storage.load_fsm_state(profile_name, symbol)
            
            has_actual = symbol in actual_position_map
            has_saved = saved_pos is not None
            
            # 重建FSM来检查状态
            fsm = TrendFilterStateMachine()
            if saved_fsm:
                fsm.restore(saved_fsm)
            fsm_in_position = fsm.state.name.startswith('POSITION')
            
            logger.info(f"  Storage持仓: {'有' if has_saved else '无'}")
            logger.info(f"  实盘持仓: {'有' if has_actual else '无'}")
            logger.info(f"  FSM状态: {fsm.state.value} ({'持仓中' if fsm_in_position else '空闲'})")
            
            # 情况1: Storage有记录但实盘无持仓
            if has_saved and not has_actual:
                logger.warning(f"  ❌ 不一致: Storage有记录但实盘无持仓（已被自动平仓）")
                trade_id = saved_pos.get('trade_id', 'N/A')
                
                if not dry_run:
                    # 删除持仓记录
                    storage.delete_position(profile_name, symbol)
                    logger.info(f"  ✓ 已删除Storage持仓记录 (trade_id={trade_id})")
                    
                    # 重置FSM
                    if fsm_in_position:
                        fsm._reset()
                        storage.save_fsm_state(profile_name, symbol, fsm.get_state_snapshot())
                        logger.info(f"  ✓ 已重置FSM状态为IDLE")
                    
                    fixed_count += 1
                else:
                    logger.info(f"  [DRY_RUN] 需要删除持仓记录 (trade_id={trade_id}) 并重置FSM")
                    fixed_count += 1
            
            # 情况2: 实盘有持仓但Storage无记录
            elif not has_saved and has_actual:
                logger.error(f"  ❌ 严重不一致: 实盘有持仓但Storage无记录!")
                actual_pos = actual_position_map[symbol]
                logger.error(
                    f"     实盘持仓: {actual_pos.position_id}, "
                    f"{actual_pos.side} {actual_pos.units} @ {actual_pos.entry_price:.5f}"
                )
                logger.error(f"     建议: 人工检查是否为手动开仓，或重新初始化记录")
                error_count += 1
            
            # 情况3: FSM状态与持仓不匹配
            elif has_saved != fsm_in_position:
                logger.warning(
                    f"  ❌ FSM状态不一致: Storage持仓={has_saved}, FSM持仓状态={fsm_in_position}"
                )
                
                if not dry_run:
                    # 以Storage持仓记录为准
                    if has_saved and not fsm_in_position:
                        logger.warning(f"  [无法自动修复] FSM应进入持仓状态但无法确定方向，请人工处理")
                        error_count += 1
                    elif not has_saved and fsm_in_position:
                        fsm._reset()
                        storage.save_fsm_state(profile_name, symbol, fsm.get_state_snapshot())
                        logger.info(f"  ✓ 已重置FSM状态为IDLE")
                        fixed_count += 1
                else:
                    logger.info(f"  [DRY_RUN] 需要修复FSM状态")
                    fixed_count += 1
            
            else:
                logger.info(f"  ✓ 状态一致")
            
            logger.info("")
        
        # 总结
        logger.info(f"========================")
        logger.info(f"修复完成")
        logger.info(f"检查品种: {len(config.symbols)} 个")
        logger.info(f"需要修复: {fixed_count} 个")
        logger.info(f"错误/警告: {error_count} 个")
        logger.info(f"========================")
        
        if dry_run and fixed_count > 0:
            logger.info(f"\n提示: 移除 --dry-run 参数以执行实际修复")
        
    except Exception as e:
        logger.exception(f"修复失败: {e}")
        raise
    finally:
        executor.close()


def main():
    parser = argparse.ArgumentParser(description='持仓状态修复工具')
    parser.add_argument(
        '--profile',
        type=str,
        default='oanda_demo',
        help='Profile名称 (默认: oanda_demo)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只读模式，检查但不修改',
    )
    
    args = parser.parse_args()
    fix_state(args.profile, args.dry_run)


if __name__ == '__main__':
    main()
