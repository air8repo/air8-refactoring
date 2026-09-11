from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseBankParser(ABC):
    """银行回单解析器基类，定义了所有解析器必须实现的接口"""

    @abstractmethod
    def parse(self, data: Any) -> Dict[str, Any]:
        """解析银行回单数据

        Args:
            data: 银行回单数据，可以是文件路径、二进制数据或其他格式

        Returns:
            Dict[str, Any]: 解析后的标准化银行回单数据
        """
        pass

    @abstractmethod
    def get_bank_name(self) -> str:
        """获取银行名称

        Returns:
            str: 银行名称
        """
        pass

    @abstractmethod
    def can_handle(self, data: Any) -> bool:
        """检查当前解析器是否能处理该数据

        Args:
            data: 银行回单数据

        Returns:
            bool: 是否能处理
        """
        pass
