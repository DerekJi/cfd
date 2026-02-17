"""
趋势过滤状态机 — 纯 Python 版本

从 backtest/indicators/trend_filter_fsm.py 提取，增加了
  - get_state_snapshot() → 可序列化完整状态用于持久化
  - restore(snapshot)   → 从快照恢复状态
  - 实盘硬止损支持 (check_hard_stop) — 使用 high/low 而非 close

原始 FSM 逻辑保持完全不变，可通过回测对比验证。
"""

from enum import Enum
from typing import Optional, Dict, Any


class TrendFilterState(Enum):
    """趋势过滤状态机状态"""
    IDLE = "空闲"
    BREAKOUT_DETECTED = "检测到突破"
    TREND_ANALYSIS = "趋势分析"
    WAIT_PULLBACK = "等待回踩"
    POSITION_LONG = "多头持仓"
    POSITION_SHORT = "空头持仓"


class TrendFilterStateMachine:
    """
    趋势过滤状态机

    策略逻辑：
    1. 检测突破（UP线或DOWN线）
    2. 分析趋势强度（ADX > 25）和方向（EMA200）
    3. 只在强趋势中交易：
       - 向上突破 + ADX>25 + 价格>EMA200 → 等回踩做多
       - 向下突破 + ADX>25 + 价格<EMA200 → 等回踩做空
    4. 回踩EMA50后入场
    5. EMA50作为移动止损
    """

    def __init__(self,
                 up_period=20,
                 down_period=20,
                 ema50_period=50,
                 ema200_period=200,
                 adx_period=14,
                 adx_threshold=25,
                 analysis_bars=5,
                 pullback_wait_bars=20,
                 debug=False):
        self.up_period = up_period
        self.down_period = down_period
        self.ema50_period = ema50_period
        self.ema200_period = ema200_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.analysis_bars = analysis_bars
        self.pullback_wait_bars = pullback_wait_bars
        self.debug = debug

        # 状态变量
        self._reset()

    # ----------------------------------------------------------------
    # 主入口
    # ----------------------------------------------------------------

    def update(self, bar_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        更新状态机

        Args:
            bar_data: {
                'close': 收盘价,
                'high': 最高价,
                'low': 最低价,
                'up_line': UP线,
                'down_line': DOWN线,
                'ema50': EMA50,
                'ema200': EMA200,
                'adx': ADX值,
                'atr': ATR值,
                'bar_index': K线索引,
                'datetime': 日期时间 (可选)
            }

        Returns:
            action dict 或 None
        """
        if self.state == TrendFilterState.IDLE:
            return self._process_idle(bar_data)
        elif self.state == TrendFilterState.BREAKOUT_DETECTED:
            return self._process_breakout(bar_data)
        elif self.state == TrendFilterState.TREND_ANALYSIS:
            return self._process_analysis(bar_data)
        elif self.state == TrendFilterState.WAIT_PULLBACK:
            return self._process_wait_pullback(bar_data)
        elif self.state == TrendFilterState.POSITION_LONG:
            return self._process_position_long(bar_data)
        elif self.state == TrendFilterState.POSITION_SHORT:
            return self._process_position_short(bar_data)

        return None

    # ----------------------------------------------------------------
    # 持久化支持  (新增)
    # ----------------------------------------------------------------

    @staticmethod
    def _to_python(val):
        """将 numpy 标量转换为原生 Python 类型，确保 JSON 可序列化"""
        if val is None:
            return None
        import math
        # numpy float / int → Python float / int
        tp = type(val).__name__
        if 'float' in tp:
            v = float(val)
            return None if math.isnan(v) else v
        if 'int' in tp:
            return int(val)
        return val

    def get_state_snapshot(self) -> Dict[str, Any]:
        """
        获取完整状态快照，可直接序列化为 JSON / Azure Table 存储

        numpy 标量会自动转换为原生 Python 类型，NaN → None。

        Returns:
            dict: 包含所有可恢复状态变量
        """
        c = self._to_python
        return {
            'state': self.state.name,                    # str: 'IDLE', 'POSITION_LONG' 等
            'breakout_direction': self.breakout_direction,
            'locked_up_line': c(self.locked_up_line),
            'locked_down_line': c(self.locked_down_line),
            'locked_ema50': c(self.locked_ema50),
            'locked_ema200': c(self.locked_ema200),
            'analysis_counter': self.analysis_counter,
            'wait_counter': self.wait_counter,
            'entry_price': c(self.entry_price),
            'stop_loss': c(self.stop_loss),
        }

    def restore(self, snapshot: Dict[str, Any]) -> None:
        """
        从快照恢复状态 (对应 get_state_snapshot 的逆操作)

        Args:
            snapshot: get_state_snapshot() 返回的 dict
        """
        self.state = TrendFilterState[snapshot['state']]
        self.breakout_direction = snapshot.get('breakout_direction')
        self.locked_up_line = snapshot.get('locked_up_line')
        self.locked_down_line = snapshot.get('locked_down_line')
        self.locked_ema50 = snapshot.get('locked_ema50')
        self.locked_ema200 = snapshot.get('locked_ema200')
        self.analysis_counter = snapshot.get('analysis_counter', 0)
        self.wait_counter = snapshot.get('wait_counter', 0)
        self.entry_price = snapshot.get('entry_price')
        self.stop_loss = snapshot.get('stop_loss')

    def get_state(self) -> dict:
        """获取简化状态信息 (兼容旧 API)"""
        return {
            'state': self.state.value,
            'breakout_direction': self.breakout_direction,
            'locked_up': self.locked_up_line,
            'locked_down': self.locked_down_line,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
        }

    # ----------------------------------------------------------------
    # 硬止损检查  (新增 — 实盘用)
    # ----------------------------------------------------------------

    def check_hard_stop(self, bar_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        使用最高价/最低价检查硬止损，回测策略 next() 里的逻辑

        回测中 trend_filter_strategy_v1.py 在 next() 里有：
            if data.low[0] <= stop_loss (多头) → 立即平仓
            if data.high[0] >= stop_loss (空头) → 立即平仓

        实盘中这个检查在 FSM.update() 之前调用。

        Args:
            bar_data: 包含 'high', 'low' 的字典

        Returns:
            exit action dict 或 None
        """
        if self.state == TrendFilterState.POSITION_LONG and self.stop_loss is not None:
            if bar_data['low'] <= self.stop_loss:
                action = {
                    'action': 'exit_long',
                    'exit_price': self.stop_loss,  # 按止损价计算
                    'reason': 'hard_stop_loss',
                }
                self._reset()
                return action

        if self.state == TrendFilterState.POSITION_SHORT and self.stop_loss is not None:
            if bar_data['high'] >= self.stop_loss:
                action = {
                    'action': 'exit_short',
                    'exit_price': self.stop_loss,
                    'reason': 'hard_stop_loss',
                }
                self._reset()
                return action

        return None

    # ----------------------------------------------------------------
    # 状态处理器 — 与原始 FSM 逻辑完全一致
    # ----------------------------------------------------------------

    def _process_idle(self, bar_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """空闲状态：检测突破"""
        close = bar_data['close']
        up_line = bar_data['up_line']
        down_line = bar_data['down_line']

        if close > up_line:
            self.breakout_direction = 'up'
            self.locked_up_line = up_line
            self.locked_down_line = down_line
            self.locked_ema50 = bar_data['ema50']
            self.locked_ema200 = bar_data['ema200']
            self.state = TrendFilterState.BREAKOUT_DETECTED

            if self.debug:
                print(f"\n[Bar {bar_data['bar_index']}] {bar_data.get('datetime', '')}")
                print(f"  Price: {close:.5f}")
                print(f"  突破UP线 {up_line:.5f}，锁定边界")
            return None

        if close < down_line:
            self.breakout_direction = 'down'
            self.locked_up_line = up_line
            self.locked_down_line = down_line
            self.locked_ema50 = bar_data['ema50']
            self.locked_ema200 = bar_data['ema200']
            self.state = TrendFilterState.BREAKOUT_DETECTED

            if self.debug:
                print(f"\n[Bar {bar_data['bar_index']}] {bar_data.get('datetime', '')}")
                print(f"  Price: {close:.5f}")
                print(f"  突破DOWN线 {down_line:.5f}，锁定边界")
            return None

        return None

    def _process_breakout(self, bar_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """突破检测状态：确认突破"""
        self.state = TrendFilterState.TREND_ANALYSIS
        self.analysis_counter = 0

        if self.debug:
            print(f"\n[Bar {bar_data['bar_index']}] {bar_data.get('datetime', '')}")
            print(f"  开始趋势分析...")

        return None

    def _process_analysis(self, bar_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """趋势分析状态：判断是否是强趋势"""
        self.analysis_counter += 1

        close = bar_data['close']
        adx_val = bar_data['adx']
        ema200 = bar_data['ema200']

        adx_strong = adx_val > self.adx_threshold
        price_above_ema200 = close > ema200

        valid_uptrend = (
            self.breakout_direction == 'up'
            and adx_strong
            and price_above_ema200
        )
        valid_downtrend = (
            self.breakout_direction == 'down'
            and adx_strong
            and not price_above_ema200
        )

        if self.debug:
            print(f"\n[Bar {bar_data['bar_index']}] {bar_data.get('datetime', '')}")
            print(f"  Price: {close:.5f} | ADX: {adx_val:.1f} | EMA200: {ema200:.5f}")
            print(f"  突破方向: {self.breakout_direction}")
            print(f"  ADX强趋势: {adx_strong} | 价格>EMA200: {price_above_ema200}")

        if valid_uptrend or valid_downtrend:
            self.state = TrendFilterState.WAIT_PULLBACK
            self.wait_counter = 0

            if self.debug:
                direction_str = "上升趋势" if valid_uptrend else "下降趋势"
                print(f"  ✓ 确认{direction_str}，等待回踩EMA50")
            return None

        if self.analysis_counter >= self.analysis_bars:
            if self.debug:
                print(f"  ✗ 趋势条件不满足，放弃交易")
                print(f"    原因: ADX={adx_val:.1f}{'<' if not adx_strong else '>='}{self.adx_threshold}")
                if self.breakout_direction == 'up' and not price_above_ema200:
                    print(f"    价格未在EMA200上方")
                elif self.breakout_direction == 'down' and price_above_ema200:
                    print(f"    价格未在EMA200下方")

            self._reset()
            return None

        return None

    def _process_wait_pullback(self, bar_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """等待回踩状态"""
        self.wait_counter += 1

        close = bar_data['close']
        ema50 = bar_data['ema50']
        atr_val = bar_data['atr']

        if self.breakout_direction == 'up':
            pullback_threshold = ema50 + atr_val * 0.5

            if close <= pullback_threshold:
                self.entry_price = close
                self.stop_loss = ema50 - atr_val * 1.0
                self.state = TrendFilterState.POSITION_LONG

                if self.debug:
                    print(f"\n[Bar {bar_data['bar_index']}] {bar_data.get('datetime', '')}")
                    print(f"  ✓ 回踩成功，做多入场")
                    print(f"  入场: {self.entry_price:.5f} | 止损: {self.stop_loss:.5f}")

                return {
                    'action': 'entry_long',
                    'entry_price': self.entry_price,
                    'stop_loss': self.stop_loss,
                    'locked_up': self.locked_up_line,
                    'locked_down': self.locked_down_line,
                }

        elif self.breakout_direction == 'down':
            pullback_threshold = ema50 - atr_val * 0.5

            if close >= pullback_threshold:
                self.entry_price = close
                self.stop_loss = ema50 + atr_val * 1.0
                self.state = TrendFilterState.POSITION_SHORT

                if self.debug:
                    print(f"\n[Bar {bar_data['bar_index']}] {bar_data.get('datetime', '')}")
                    print(f"  ✓ 回踩成功，做空入场")
                    print(f"  入场: {self.entry_price:.5f} | 止损: {self.stop_loss:.5f}")

                return {
                    'action': 'entry_short',
                    'entry_price': self.entry_price,
                    'stop_loss': self.stop_loss,
                    'locked_up': self.locked_up_line,
                    'locked_down': self.locked_down_line,
                }

        if self.wait_counter >= self.pullback_wait_bars:
            if self.debug:
                print(f"\n[Bar {bar_data['bar_index']}] {bar_data.get('datetime', '')}")
                print(f"  等待回踩超时，放弃交易")

            self._reset()
            return None

        return None

    def _process_position_long(self, bar_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """多头持仓状态"""
        close = bar_data['close']
        ema50 = bar_data['ema50']

        # 更新移动止损（跟随EMA50）
        new_stop = ema50 - bar_data['atr'] * 0.8
        if new_stop > self.stop_loss:
            self.stop_loss = new_stop
            if self.debug:
                print(f"\n[Bar {bar_data['bar_index']}] 移动止损 → {self.stop_loss:.5f}")

        # 检查止损
        if close <= self.stop_loss:
            if self.debug:
                print(f"\n[Bar {bar_data['bar_index']}] 触发止损 @ {close:.5f}")

            action = {
                'action': 'exit_long',
                'exit_price': close,
                'reason': 'stop_loss',
            }
            self._reset()
            return action

        return None

    def _process_position_short(self, bar_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """空头持仓状态"""
        close = bar_data['close']
        ema50 = bar_data['ema50']

        # 更新移动止损（跟随EMA50）
        new_stop = ema50 + bar_data['atr'] * 0.8
        if new_stop < self.stop_loss:
            self.stop_loss = new_stop
            if self.debug:
                print(f"\n[Bar {bar_data['bar_index']}] 移动止损 → {self.stop_loss:.5f}")

        # 检查止损
        if close >= self.stop_loss:
            if self.debug:
                print(f"\n[Bar {bar_data['bar_index']}] 触发止损 @ {close:.5f}")

            action = {
                'action': 'exit_short',
                'exit_price': close,
                'reason': 'stop_loss',
            }
            self._reset()
            return action

        return None

    def _reset(self):
        """重置状态机"""
        self.state = TrendFilterState.IDLE
        self.breakout_direction = None
        self.locked_up_line = None
        self.locked_down_line = None
        self.locked_ema50 = None
        self.locked_ema200 = None
        self.analysis_counter = 0
        self.wait_counter = 0
        self.entry_price = None
        self.stop_loss = None
