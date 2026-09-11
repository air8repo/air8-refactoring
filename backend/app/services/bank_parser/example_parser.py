from typing import Dict, Any
from backend.app.services.bank_parser.base_parser import BaseBankParser


class ExampleBankParser(BaseBankParser):
    """示例银行解析器，用于演示解析器的实现"""

    def parse(self, data: Any) -> Dict[str, Any]:
        """解析示例银行回单数据

        Args:
            data: 银行回单数据，可以是文件路径或字符串

        Returns:
            Dict[str, Any]: 解析后的标准化银行回单数据
        """
        # 这里是示例实现，实际解析逻辑需要根据银行回单格式定制
        # 假设data是一个包含银行回单信息的字符串
        if isinstance(data, str):
            # 简单的示例解析逻辑
            lines = data.split('\n')
            parsed_data = {}
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    parsed_data[key.strip().lower().replace(' ', '_')] = value.strip()
            
            # 标准化输出格式
            return {
                'bank_name': self.get_bank_name(),
                'finance_request_number': parsed_data.get('finance_request_number', ''),
                'amount': parsed_data.get('amount', 0),
                'date': parsed_data.get('date', ''),
                'status': parsed_data.get('status', ''),
                'raw_data': data
            }
        
        # 对于文件路径的处理
        elif isinstance(data, dict) and 'file_path' in data:
            file_path = data['file_path']
            with open(file_path, 'r') as f:
                content = f.read()
            return self.parse(content)
        
        return {
            'bank_name': self.get_bank_name(),
            'finance_request_number': '',
            'amount': 0,
            'date': '',
            'status': '',
            'raw_data': str(data)
        }

    def get_bank_name(self) -> str:
        """获取银行名称

        Returns:
            str: 银行名称
        """
        return "Example Bank"

    def can_handle(self, data: Any) -> bool:
        """检查当前解析器是否能处理该数据

        Args:
            data: 银行回单数据

        Returns:
            bool: 是否能处理
        """
        # 示例实现：检查数据中是否包含"Example Bank"标识
        if isinstance(data, str):
            return "Example Bank" in data
        elif isinstance(data, dict) and 'bank_name' in data:
            return data['bank_name'] == "Example Bank"
        return False
