from typing import Dict, Any

class BaseStrategy:
    """
    策略基类，所有策略需继承此类并实现以下方法。
    """

    def initialize(self, config: Dict[str, Any]) -> None:
        """
        初始化策略。
        Args:
            config (Dict[str, Any]): 策略配置参数。
        """
        raise NotImplementedError("initialize() 方法未实现")

    def process_symbol(self, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单个品种的逻辑。
        Args:
            symbol (str): 品种名称。
            data (Dict[str, Any]): 品种相关数据。
        Returns:
            Dict[str, Any]: 策略输出结果。
        """
        raise NotImplementedError("process_symbol() 方法未实现")