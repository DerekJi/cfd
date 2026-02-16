"""
趋势过滤状态机

使用ADX+EMA200过滤假突破，只在强趋势中交易
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any


class TrendFilterState(Enum):
    """趋势过滤状态机状态"""
    IDLE = "空闲"
    BREAKOUT_DETECTED = "检测到突破"
    TREND_ANALYSIS = "趋势分析"
    WAIT_PULLBACK = "等待回踩"
    POSITION_LONG = "多头持仓"
    POSITION_SHORT = "空头持仓"


@dataclass
class TrendConditions:
    """趋势条件"""
    adx_value: float
    adx_strong: bool  # ADX > threshold
    price_above_ema200: bool
    price_above_ema50: bool
    breakout_up: bool
    breakout_down: bool


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
        """
        初始化状态机
        
        Args:
            up_period: UP线周期
            down_period: DOWN线周期
            ema50_period: EMA50周期（回踩参考）
            ema200_period: EMA200周期（趋势方向）
            adx_period: ADX周期
            adx_threshold: ADX阈值（强趋势）
            analysis_bars: 分析周期
            pullback_wait_bars: 等待回踩的最大K线数
            debug: 是否输出调试信息
        """
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
        self.state = TrendFilterState.IDLE
        self.breakout_direction = None  # 'up' or 'down'
        self.locked_up_line = None
        self.locked_down_line = None
        self.locked_ema50 = None
        self.locked_ema200 = None
        self.analysis_counter = 0
        self.wait_counter = 0
        self.entry_price = None
        self.stop_loss = None
        
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
                'bar_index': K线索引
            }
        
        Returns:
            action: 操作指令 或 None
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
    
    def _process_idle(self, bar_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """空闲状态：检测突破"""
        close = bar_data['close']
        up_line = bar_data['up_line']
        down_line = bar_data['down_line']
        
        # 检测向上突破
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
        
        # 检测向下突破
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
        # 直接进入趋势分析
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
        adx = bar_data['adx']
        ema200 = bar_data['ema200']
        
        # 检查趋势条件
        adx_strong = adx > self.adx_threshold
        price_above_ema200 = close > ema200
        
        # 判断是否满足趋势交易条件
        valid_uptrend = (
            self.breakout_direction == 'up' and 
            adx_strong and 
            price_above_ema200
        )
        valid_downtrend = (
            self.breakout_direction == 'down' and 
            adx_strong and 
            not price_above_ema200
        )
        
        if self.debug:
            print(f"\n[Bar {bar_data['bar_index']}] {bar_data.get('datetime', '')}")
            print(f"  Price: {close:.5f} | ADX: {adx:.1f} | EMA200: {ema200:.5f}")
            print(f"  突破方向: {self.breakout_direction}")
            print(f"  ADX强趋势: {adx_strong} | 价格>EMA200: {price_above_ema200}")
        
        # 如果满足趋势条件，进入等待回踩
        if valid_uptrend or valid_downtrend:
            self.state = TrendFilterState.WAIT_PULLBACK
            self.wait_counter = 0
            
            if self.debug:
                direction_str = "上升趋势" if valid_uptrend else "下降趋势"
                print(f"  ✓ 确认{direction_str}，等待回踩EMA50")
            return None
        
        # 分析超时，放弃交易
        if self.analysis_counter >= self.analysis_bars:
            if self.debug:
                print(f"  ✗ 趋势条件不满足，放弃交易")
                print(f"    原因: ADX={adx:.1f}{'<' if not adx_strong else '>='}{self.adx_threshold}")
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
        atr = bar_data['atr']
        
        # 向上突破：等待价格回踩到EMA50附近
        if self.breakout_direction == 'up':
            pullback_threshold = ema50 + atr * 0.5  # EMA50上方0.5倍ATR
            
            if close <= pullback_threshold:
                # 回踩成功，做多入场
                self.entry_price = close
                self.stop_loss = ema50 - atr * 1.0  # 止损设在EMA50下方1倍ATR
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
                    'locked_down': self.locked_down_line
                }
        
        # 向下突破：等待价格回踩到EMA50附近
        elif self.breakout_direction == 'down':
            pullback_threshold = ema50 - atr * 0.5  # EMA50下方0.5倍ATR
            
            if close >= pullback_threshold:
                # 回踩成功，做空入场
                self.entry_price = close
                self.stop_loss = ema50 + atr * 1.0  # 止损设在EMA50上方1倍ATR
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
                    'locked_down': self.locked_down_line
                }
        
        # 等待超时
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
                'reason': 'stop_loss'
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
                'reason': 'stop_loss'
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
    
    def get_state(self) -> dict:
        """获取当前状态信息"""
        return {
            'state': self.state.value,
            'breakout_direction': self.breakout_direction,
            'locked_up': self.locked_up_line,
            'locked_down': self.locked_down_line,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss
        }
