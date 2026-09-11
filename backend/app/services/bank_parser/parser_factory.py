from typing import Dict, Any
from backend.app.services.bank_parser.base_parser import BaseBankParser
from backend.app.services.bank_parser import parsers  # 导入所有解析器


class BankParserFactory:
    """银行回单解析器工厂类，用于获取合适的解析器实例"""

    def __init__(self):
        """初始化工厂，注册所有可用的解析器"""
        self.parsers = []
        # 自动注册所有BaseBankParser的子类
        for cls_name in dir(parsers):
            cls = getattr(parsers, cls_name)
            if isinstance(cls, type) and issubclass(cls, BaseBankParser) and cls != BaseBankParser:
                self.parsers.append(cls())

    def get_parser(self, data: Any) -> BaseBankParser:
        """根据数据获取合适的解析器

        Args:
            data: 银行回单数据

        Returns:
            BaseBankParser: 合适的解析器实例

        Raises:
            ValueError: 没有找到能处理该数据的解析器
        """
        for parser in self.parsers:
            if parser.can_handle(data):
                return parser
        raise ValueError("没有找到能处理该银行回单的解析器")

    def parse(self, data: Any) -> Dict[str, Any]:
        """直接解析数据，内部会自动选择合适的解析器

        Args:
            data: 银行回单数据

        Returns:
            Dict[str, Any]: 解析后的标准化银行回单数据
        """
        parser = self.get_parser(data)
        return parser.parse(data)
