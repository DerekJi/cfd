"""
五步状态机逻辑
State Machine for 5-state trading logic
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional
import datetime


class TradingState(Enum):
    """交易状态枚举"""
    IDLE = 0  # 静默状态
    TOUCHING = 1  # 触碰中
    TOUCHED_SUCCESS = 2  # 有效突破
    RETRACED = 3  # 回落确认
    POSITION = 4  # 持仓管理


@dataclass
class StateData:
    """状态数据记录"""
    state: TradingState
    
    # 状态1数据
    touch_start_time: Optional[datetime.datetime] = None
    touch_start_bar: Optional[int] = None
    
    # 状态2数据
    peak_price: Optional[float] = None
    peak_time: Optional[datetime.datetime] = None
    peak_bar: Optional[int] = None
    
    # 状态3数据
    dip_price: Optional[float] = None
    dip_time: Optional[datetime.datetime] = None
    dip_bar: Optional[int] = None
    retrace_start_bar: Optional[int] = None
    
    # 状态4数据
    entry_price: Optional[float] = None
    entry_time: Optional[datetime.datetime] = None
    entry_bar: Optional[int] = None
    stop_loss: Optional[float] = None
    initial_stop_loss: Optional[float] = None
    
    # UP/DOWN线记录
    up_line: Optional[float] = None
    down_line: Optional[float] = None
    mid_line: Optional[float] = None
    buffer: Optional[float] = None
    atr: Optional[float] = None
    
    def reset_to_idle(self):
        """重置到IDLE状态"""
        self.state = TradingState.IDLE
        self.touch_start_time = None
        self.touch_start_bar = None
        self.peak_price = None
        self.peak_time = None
        self.peak_bar = None
        self.dip_price = None
        self.dip_time = None
        self.dip_bar = None
        self.retrace_start_bar = None
        self.entry_price = None
        self.entry_time = None
        self.entry_bar = None
        self.stop_loss = None
        self.initial_stop_loss = None


class StateMachine:
    """
    五步状态机
    
    实现策略文档中的5个状态转换逻辑
    """
    
    def __init__(self, confirm_bars=1, max_wait_bars=6, trailing_stop=True):
        """
        初始化状态机
        
        Args:
            confirm_bars: 突破确认K线数
            max_wait_bars: 最大等待K线数
            trailing_stop: 是否启用移动止损
        """
        self.confirm_bars = confirm_bars
        self.max_wait_bars = max_wait_bars
        self.trailing_stop_enabled = trailing_stop
        
        self.state_data = StateData(state=TradingState.IDLE)
        self.current_bar = 0
        
        # 记录状态转换历史
        self.state_history = []
    
    def update_range_data(self, up_line, down_line, buffer, atr):
        """更新区间数据"""
        self.state_data.up_line = up_line
        self.state_data.down_line = down_line
        self.state_data.mid_line = (up_line + down_line) / 2
        self.state_data.buffer = buffer
        self.state_data.atr = atr
    
    def process(self, current_time, current_bar, high, low, close):
        """
        处理当前K线，更新状态机
        
        Args:
            current_time: 当前时间
            current_bar: 当前K线索引
            high: 最高价
            low: 最低价
            close: 收盘价
            
        Returns:
            dict: 状态机的动作指令 {'action': 'entry'|'exit'|'update_stop'|None}
        """
        self.current_bar = current_bar
        current_state = self.state_data.state
        action = {'action': None}
        
        if current_state == TradingState.IDLE:
            action = self._process_idle(current_time, current_bar, high, low, close)
        
        elif current_state == TradingState.TOUCHING:
            action = self._process_touching(current_time, current_bar, high, low, close)
        
        elif current_state == TradingState.TOUCHED_SUCCESS:
            action = self._process_touched(current_time, current_bar, high, low, close)
        
        elif current_state == TradingState.RETRACED:
            action = self._process_retraced(current_time, current_bar, high, low, close)
        
        elif current_state == TradingState.POSITION:
            action = self._process_position(current_time, current_bar, high, low, close)
        
        # 记录状态转换
        if action.get('state_changed'):
            self.state_history.append({
                'bar': current_bar,
                'time': current_time,
                'from_state': current_state,
                'to_state': self.state_data.state,
                'price': close
            })
        
        return action
    
    def _process_idle(self, current_time, current_bar, high, low, close):
        """处理IDLE状态"""
        # 检查是否突破UP线
        if close > self.state_data.up_line:
            # 转入TOUCHING状态
            self.state_data.state = TradingState.TOUCHING
            self.state_data.touch_start_time = current_time
            self.state_data.touch_start_bar = current_bar
            self.state_data.peak_price = high
            
            return {
                'action': None,
                'state_changed': True,
                'message': f'突破UP线 {self.state_data.up_line:.5f}，进入TOUCHING状态'
            }
        
        return {'action': None}
    
    def _process_touching(self, current_time, current_bar, high, low, close):
        """处理TOUCHING状态"""
        # 更新Peak价格
        if high > self.state_data.peak_price:
            self.state_data.peak_price = high
        
        # 检查是否回落到UP线以下（失败）
        if close <= self.state_data.up_line:
            self.state_data.reset_to_idle()
            return {
                'action': None,
                'state_changed': True,
                'message': '回落到UP线以下，回到IDLE状态'
            }
        
        # 检查是否满足确认条件
        bars_elapsed = current_bar - self.state_data.touch_start_bar
        if bars_elapsed >= self.confirm_bars:
            # 转入TOUCHED_SUCCESS状态
            self.state_data.state = TradingState.TOUCHED_SUCCESS
            self.state_data.peak_bar = current_bar
            self.state_data.peak_time = current_time
            
            return {
                'action': None,
                'state_changed': True,
                'message': f'突破确认，Peak价格: {self.state_data.peak_price:.5f}'
            }
        
        return {'action': None}
    
    def _process_touched(self, current_time, current_bar, high, low, close):
        """处理TOUCHED_SUCCESS状态"""
        # 更新Peak价格
        if high > self.state_data.peak_price:
            self.state_data.peak_price = high
        
        # 检查是否回落到 UP - Buffer
        retracement_threshold = self.state_data.up_line - self.state_data.buffer
        
        if close <= retracement_threshold:
            # 转入RETRACED状态
            self.state_data.state = TradingState.RETRACED
            self.state_data.dip_price = low
            self.state_data.dip_time = current_time
            self.state_data.dip_bar = current_bar
            self.state_data.retrace_start_bar = current_bar
            
            return {
                'action': None,
                'state_changed': True,
                'message': f'回落确认，Dip价格: {self.state_data.dip_price:.5f}'
            }
        
        return {'action': None}
    
    def _process_retraced(self, current_time, current_bar, high, low, close):
        """处理RETRACED状态"""
        # 更新Dip价格
        if low < self.state_data.dip_price:
            self.state_data.dip_price = low
        
        # 失效条件1：跌破中轴
        if self.state_data.dip_price < self.state_data.mid_line:
            self.state_data.reset_to_idle()
            return {
                'action': None,
                'state_changed': True,
                'message': '跌破中轴，回到IDLE状态'
            }
        
        # 失效条件2：假突破（跌破UP线）
        if close < self.state_data.up_line:
            self.state_data.reset_to_idle()
            return {
                'action': None,
                'state_changed': True,
                'message': '假突破，回到IDLE状态'
            }
        
        # 失效条件3：超时
        bars_elapsed = current_bar - self.state_data.retrace_start_bar
        if bars_elapsed > self.max_wait_bars:
            self.state_data.reset_to_idle()
            return {
                'action': None,
                'state_changed': True,
                'message': '等待超时，回到IDLE状态'
            }
        
        # 入场触发：突破Peak价格
        if close > self.state_data.peak_price:
            # 转入POSITION状态
            self.state_data.state = TradingState.POSITION
            self.state_data.entry_price = close
            self.state_data.entry_time = current_time
            self.state_data.entry_bar = current_bar
            
            # 计算初始止损：Dip - ATR（模拟Spread）
            self.state_data.initial_stop_loss = self.state_data.dip_price - self.state_data.atr
            self.state_data.stop_loss = self.state_data.initial_stop_loss
            
            return {
                'action': 'entry',
                'state_changed': True,
                'entry_price': self.state_data.entry_price,
                'stop_loss': self.state_data.stop_loss,
                'message': f'入场！价格: {self.state_data.entry_price:.5f}, 止损: {self.state_data.stop_loss:.5f}'
            }
        
        return {'action': None}
    
    def _process_position(self, current_time, current_bar, high, low, close):
        """处理POSITION状态"""
        # 检查止损出场
        if close < self.state_data.stop_loss:
            exit_price = close
            self.state_data.reset_to_idle()
            
            return {
                'action': 'exit',
                'state_changed': True,
                'exit_price': exit_price,
                'message': f'触发止损，出场价格: {exit_price:.5f}'
            }
        
        # 移动止损逻辑
        if self.trailing_stop_enabled:
            # 如果创新高，移动止损
            entry_to_dip_distance = self.state_data.entry_price - self.state_data.dip_price
            new_stop = high - entry_to_dip_distance
            
            if new_stop > self.state_data.stop_loss:
                self.state_data.stop_loss = new_stop
                return {
                    'action': 'update_stop',
                    'new_stop': new_stop,
                    'message': f'移动止损至: {new_stop:.5f}'
                }
        
        return {'action': None}
    
    def get_current_state(self):
        """获取当前状态信息"""
        return {
            'state': self.state_data.state.name,
            'state_value': self.state_data.state.value,
            'up_line': self.state_data.up_line,
            'down_line': self.state_data.down_line,
            'mid_line': self.state_data.mid_line,
            'peak_price': self.state_data.peak_price,
            'dip_price': self.state_data.dip_price,
            'entry_price': self.state_data.entry_price,
            'stop_loss': self.state_data.stop_loss,
        }


if __name__ == '__main__':
    # 测试状态机
    sm = StateMachine(confirm_bars=1, max_wait_bars=6, trailing_stop=True)
    sm.update_range_data(up_line=1.1000, down_line=1.0950, buffer=0.0002, atr=0.0003)
    
    print("状态机测试:")
    print(f"初始状态: {sm.get_current_state()['state']}")
    
    # 模拟突破
    result = sm.process(datetime.datetime.now(), 0, 1.1005, 1.0999, 1.1003)
    print(f"突破后: {result}")
    print(f"当前状态: {sm.get_current_state()['state']}")
