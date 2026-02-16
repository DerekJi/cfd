"""
自定义分析器
Custom analyzers for backtest system
"""

import backtrader as bt
from datetime import datetime


class DetailedTradeAnalyzer(bt.Analyzer):
    """
    详细的交易分析器
    
    记录每笔交易的详细信息
    """
    
    def __init__(self):
        self.trades = []
        self.current_trade = None
    
    def notify_trade(self, trade):
        """交易通知"""
        if trade.isclosed:
            # 计算持仓时间
            entry_bar = trade.baropen
            exit_bar = trade.barclose
            holding_period = exit_bar - entry_bar
            
            # 安全计算exit_price和pnl_percent
            if trade.size != 0:
                exit_price = trade.price + trade.pnl / trade.size
                pnl_percent = (trade.pnl / (trade.price * trade.size)) * 100
            else:
                exit_price = trade.price
                pnl_percent = 0.0
            
            # 记录交易详情
            trade_info = {
                'entry_bar': entry_bar,
                'exit_bar': exit_bar,
                'entry_date': bt.num2date(trade.dtopen),
                'exit_date': bt.num2date(trade.dtclose),
                'holding_bars': holding_period,
                'entry_price': trade.price,
                'exit_price': exit_price,
                'size': trade.size,
                'pnl': trade.pnl,
                'pnl_comm': trade.pnlcomm,
                'commission': trade.commission,
                'pnl_percent': pnl_percent,
            }
            
            self.trades.append(trade_info)
    
    def get_analysis(self):
        """返回分析结果"""
        return {
            'trades': self.trades,
            'total_trades': len(self.trades),
        }


class DrawdownAnalyzer(bt.Analyzer):
    """
    回撤分析器
    
    计算详细的回撤信息
    """
    
    def __init__(self):
        self.peak_value = self.strategy.broker.get_value()
        self.max_drawdown = 0
        self.max_drawdown_period = 0
        self.current_drawdown_period = 0
        self.drawdown_history = []
    
    def next(self):
        """每根K线调用"""
        current_value = self.strategy.broker.get_value()
        
        # 更新峰值
        if current_value > self.peak_value:
            self.peak_value = current_value
            self.current_drawdown_period = 0
        else:
            self.current_drawdown_period += 1
        
        # 计算当前回撤
        drawdown = (self.peak_value - current_value) / self.peak_value
        
        # 更新最大回撤
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
        
        # 更新最长回撤期
        if self.current_drawdown_period > self.max_drawdown_period:
            self.max_drawdown_period = self.current_drawdown_period
        
        # 记录回撤历史
        self.drawdown_history.append({
            'datetime': self.strategy.data.datetime.datetime(0),
            'value': current_value,
            'peak': self.peak_value,
            'drawdown': drawdown,
            'drawdown_period': self.current_drawdown_period
        })
    
    def get_analysis(self):
        """返回分析结果"""
        return {
            'max_drawdown': self.max_drawdown,
            'max_drawdown_percent': self.max_drawdown * 100,
            'max_drawdown_period': self.max_drawdown_period,
            'drawdown_history': self.drawdown_history
        }


class StateTransitionAnalyzer(bt.Analyzer):
    """
    状态转换分析器
    
    统计策略的状态机转换情况
    """
    
    def __init__(self):
        self.state_transitions = []
        self.state_duration = {i: [] for i in range(5)}
        self.last_state = 0
        self.last_state_bar = 0
    
    def next(self):
        """每根K线调用"""
        current_state = self.strategy.state_machine.state_data.state.value
        current_bar = len(self.strategy.data)
        
        # 检测状态转换
        if current_state != self.last_state:
            # 记录转换
            duration = current_bar - self.last_state_bar
            
            self.state_transitions.append({
                'bar': current_bar,
                'datetime': self.strategy.data.datetime.datetime(0),
                'from_state': self.last_state,
                'to_state': current_state,
                'duration': duration
            })
            
            # 记录状态持续时间
            self.state_duration[self.last_state].append(duration)
            
            self.last_state = current_state
            self.last_state_bar = current_bar
    
    def get_analysis(self):
        """返回分析结果"""
        # 计算每个状态的平均持续时间
        avg_duration = {}
        for state, durations in self.state_duration.items():
            avg_duration[state] = sum(durations) / len(durations) if durations else 0
        
        return {
            'transitions': self.state_transitions,
            'total_transitions': len(self.state_transitions),
            'state_duration': self.state_duration,
            'avg_state_duration': avg_duration
        }


class WinStreakAnalyzer(bt.Analyzer):
    """
    连胜/连败分析器
    
    统计交易的连续盈亏情况
    """
    
    def __init__(self):
        self.current_streak = 0
        self.max_win_streak = 0
        self.max_loss_streak = 0
        self.streak_history = []
    
    def notify_trade(self, trade):
        """交易通知"""
        if not trade.isclosed:
            return
        
        # 判断盈亏
        is_win = trade.pnl > 0
        
        # 更新连胜/连败
        if is_win:
            if self.current_streak >= 0:
                self.current_streak += 1
            else:
                self.current_streak = 1
        else:
            if self.current_streak <= 0:
                self.current_streak -= 1
            else:
                self.current_streak = -1
        
        # 更新最大连胜/连败
        if self.current_streak > self.max_win_streak:
            self.max_win_streak = self.current_streak
        
        if abs(self.current_streak) > self.max_loss_streak and self.current_streak < 0:
            self.max_loss_streak = abs(self.current_streak)
        
        # 记录历史
        self.streak_history.append({
            'datetime': bt.num2date(trade.dtclose),
            'pnl': trade.pnl,
            'streak': self.current_streak
        })
    
    def get_analysis(self):
        """返回分析结果"""
        return {
            'max_win_streak': self.max_win_streak,
            'max_loss_streak': self.max_loss_streak,
            'final_streak': self.current_streak,
            'streak_history': self.streak_history
        }


if __name__ == '__main__':
    print("Custom Analyzers - Ready")
    print("可用分析器:")
    print("  1. DetailedTradeAnalyzer - 详细交易记录")
    print("  2. DrawdownAnalyzer - 回撤分析")
    print("  3. StateTransitionAnalyzer - 状态转换分析")
    print("  4. WinStreakAnalyzer - 连胜连败分析")
