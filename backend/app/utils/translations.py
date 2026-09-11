import json
import os
from babel.support import Translations

class JSONTranslations(Translations):
    """自定义的 JSON 翻译加载器"""
    
    def __init__(self, json_data=None):
        super().__init__(None)
        self.json_data = json_data or {}
    
    def load_json(self, json_path):
        """从 JSON 文件加载翻译数据"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.json_data = json.load(f)
        except FileNotFoundError:
            # 如果文件不存在，使用空字典
            self.json_data = {}
        except json.JSONDecodeError:
            # 如果 JSON 解析错误，使用空字典
            self.json_data = {}
        except UnicodeDecodeError:
            # 如果编码错误，尝试使用其他编码
            try:
                with open(json_path, 'r', encoding='gbk') as f:
                    self.json_data = json.load(f)
            except:
                # 如果所有编码都失败，使用空字典
                self.json_data = {}
        return self
    
    def gettext(self, message):
        """获取翻译文本"""
        # 首先尝试直接查找整个消息
        if message in self.json_data:
            return self.json_data[message]
        
        # 解析嵌套键，如 "common.title.dashboard"
        keys = message.split('.')
        result = self.json_data
        
        try:
            for key in keys:
                if isinstance(result, dict) and key in result:
                    result = result[key]
                else:
                    # 如果找不到键或中间结果不是字典，返回原消息
                    return message
            return result
        except (KeyError, TypeError):
            # 如果找不到翻译，返回原消息
            return message
    
    def ugettext(self, message):
        """Unicode 版本的 gettext，与 gettext 相同"""
        return self.gettext(message)
    
    def ngettext(self, singular, plural, num):
        """复数形式翻译"""
        # 尝试获取复数形式的翻译
        if num == 1:
            return self.gettext(singular)
        else:
            return self.gettext(plural)