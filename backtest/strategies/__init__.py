"""
Strategies package
"""

from .trend_filter_strategy_v1 import TrendFilterStrategy
from .dual_direction_trend_strategy import DualDirectionTrendStrategy

__all__ = ['TrendFilterStrategy', 'DualDirectionTrendStrategy']
