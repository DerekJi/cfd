import os
import sys
import logging
import json

# 禁用大部分日志
logging.basicConfig(level=logging.ERROR)

# 从环境变量读取连接字符串
conn_str = os.environ.get('AZURE_STORAGE_CONNECTION')
if not conn_str:
    print("错误: 未设置 AZURE_STORAGE_CONNECTION 环境变量")
    print()
    print("请先设置环境变量:")
    print("  Windows: set AZURE_STORAGE_CONNECTION=<your-connection-string>")
    print("  Linux/Mac: export AZURE_STORAGE_CONNECTION=<your-connection-string>")
    print()
    print("或者运行: dcqSetSecrets default")
    sys.exit(1)

# 导入模块
from storage.azure_table import AzureTableStorage
from core.fsm import TrendFilterStateMachine
from config.profiles import load_profile

try:
    # 加载配置
    profile_name = 'oanda_demo'
    config = load_profile(profile_name)
    storage = AzureTableStorage(conn_str)
    
    # 直接查询 Azure Table
    from azure.data.tables import TableServiceClient
    service = TableServiceClient.from_connection_string(conn_str)
    table = service.get_table_client('TradingState')
    
    print("=" * 60)
    print("Azure Table Storage Status Check")
    print("=" * 60)
    print(f"Profile: {profile_name}\n")
    
    # 检查 FSM 状态
    print("【FSM States】")
    fsm_states = []
    fsm_query = f"PartitionKey eq '{profile_name}' and RowKey gt 'fsm_' and RowKey lt 'fsm~'"
    for entity in table.query_entities(fsm_query):
        symbol = entity['RowKey'].replace('fsm_', '')
        data = json.loads(entity['data'])
        state = data.get('state', 'UNKNOWN')
        fsm_states.append((symbol, state))
    
    problematic = []
    for symbol, state in sorted(fsm_states):
        if state in ['POSITION_LONG', 'POSITION_SHORT']:
            problematic.append((symbol, state))
            print(f"  {symbol}: ⚠️  {state}")
        else:
            print(f"  {symbol}: ✓ {state}")
    
    # 检查持仓记录
    print()
    print("【Positions】")
    positions = []
    pos_query = f"PartitionKey eq '{profile_name}' and RowKey gt 'pos_' and RowKey lt 'pos~'"
    for entity in table.query_entities(pos_query):
        symbol = entity['RowKey'].replace('pos_', '')
        data = json.loads(entity['data'])
        positions.append((symbol, data))
        print(f"  {symbol}: {data.get('side')} {data.get('units')} @ {data.get('entry_price')}")
    
    if not positions:
        print("  No positions")
    
    # 结论
    print()
    print("=" * 60)
    print("【Summary】")
    print()
    print(f"Positions: {len(positions)}")
    print(f"FSM in POSITION state: {len(problematic)}")
    if problematic:
        for symbol, state in problematic:
            print(f"  - {symbol}: {state}")
    
    print()
    
    # 如果命令行参数是 fix，则执行修复
    if len(sys.argv) > 1 and sys.argv[1] == 'fix':
        if len(problematic) > 0 or len(positions) > 0:
            print("Starting fix...")
            print()
            
            # 修复有问题的 FSM
            for symbol, state in problematic:
                print(f"Resetting FSM for {symbol}...")
                # 重置 FSM
                fsm = TrendFilterStateMachine()
                storage.save_fsm_state(profile_name, symbol, fsm.get_state_snapshot())
                print(f"  ✓ {symbol}: FSM reset to IDLE")
            
            # 删除不一致的持仓记录
            for symbol, data in positions:
                print(f"Deleting position record for {symbol}...")
                storage.delete_position(profile_name, symbol)
                print(f"  ✓ {symbol}: Position record deleted")
            
            print()
            print("✅ Fix completed!")
        else:
            print("No fix needed, status OK.")
    else:
        # 只是检查，不修复
        if len(positions) == 0 and len(problematic) == 0:
            print("✅ Status OK - Can open new trades!")
        elif len(problematic) > 0:
            print("❌ FSM status error - Cannot open new trades")
            print()
            print("To fix, run:")
            print("  python check_azure_state.py fix")
    
    print("=" * 60)

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
