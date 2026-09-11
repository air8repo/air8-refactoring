from datetime import datetime
from typing import Dict, List, Any
from backend.app.services.import_service import get_mongo

class BatchService:
    """批次号管理服务"""
    
    def __init__(self):
        self.mongo = get_mongo()
        
    def get_all_batches(self) -> List[Dict[str, Any]]:
        """获取所有批次号信息"""
        if self.mongo is None:
            return []
        
        # 查询所有批次号，并按批次号降序排序
        pipeline = [
            {'$match': {'batch_number': {'$gt': 0}}},  # 只查询有批次号的记录
            {'$group': {
                '_id': '$batch_number',  # 按批次号分组
                'batch_status': {'$first': '$batch_status'},  # 获取批次状态
                'batch_created_at': {'$first': '$batch_created_at'},  # 获取批次生成时间
                'bank_source': {'$first': '$bank_source'},  # 获取数据源
                'order_count': {'$sum': 1},  # 统计该批次下的融资订单数量
                'last_updated': {'$max': '$updated_at'}  # 获取最后更新时间
            }},
            {'$sort': {'_id': -1}}  # 按批次号降序排序
        ]
        
        batches = list(self.mongo.refactoring_financing_order.aggregate(pipeline))
        
        # 格式化结果
        result = []
        for batch in batches:
            result.append({
                'batch_number': batch['_id'],
                'batch_status': batch['batch_status'],
                'batch_created_at': batch['batch_created_at'],
                'bank_source': batch['bank_source'],
                'order_count': batch['order_count'],
                'last_updated': batch['last_updated']
            })
        
        return result
    
    def get_batch_by_number(self, batch_number: int) -> Dict[str, Any]:
        """根据批次号获取批次详情"""
        if self.mongo is None:
            return {}
        
        # 查询该批次下的所有融资订单
        orders = list(self.mongo.refactoring_financing_order.find(
            {'batch_number': batch_number},
            {'finance_request_number': 1, 'invoice_number': 1, 'batch_status': 1, 'batch_created_at': 1, 'bank_source': 1, 'updated_at': 1}
        ))
        
        if not orders:
            return {}
        
        # 计算批次信息
        batch_info = {
            'batch_number': batch_number,
            'batch_status': orders[0]['batch_status'],
            'batch_created_at': orders[0]['batch_created_at'],
            'bank_source': orders[0]['bank_source'],
            'order_count': len(orders),
            'orders': orders
        }
        
        return batch_info
    
    def cancel_batch(self, batch_number: int) -> Dict[str, Any]:
        """作废指定批次号"""
        if self.mongo is None:
            return {'success': False, 'message': '数据库未连接'}
        
        # 1. 查询该批次是否存在
        batch_info = self.get_batch_by_number(batch_number)
        if not batch_info:
            return {'success': False, 'message': f'批次号 {batch_number} 不存在'}
        
        # 2. 更新该批次下所有融资订单的批次状态
        update_result = self.mongo.refactoring_financing_order.update_many(
            {'batch_number': batch_number},
            {'$set': {
                'batch_number': 0,  # 将批次号重置为0
                'batch_status': '',  # 将批次状态置空
                'batch_created_at': None,  # 清空批次生成时间
                'updated_at': datetime.now()  # 更新时间
            }}
        )
        
        # 3. 触发聚合接口，刷新Overview表
        from backend.app.services.aggregate_service import AggregateService
        aggregate_service = AggregateService()
        aggregate_result = aggregate_service.aggregate_financing_overview()
        
        # 4. 返回结果
        return {
            'success': True,
            'message': f'批次号 {batch_number} 已成功作废',
            'updated_count': update_result.modified_count,
            'aggregate_result': aggregate_result
        }
    
    def get_batch_by_finance_request_number(self, finance_request_number: str) -> Dict[str, Any]:
        """根据融资申请号获取批次信息"""
        if self.mongo is None:
            return {}
        
        # 查询融资订单
        order = self.mongo.refactoring_financing_order.find_one(
            {'finance_request_number': finance_request_number},
            {'batch_number': 1, 'batch_status': 1, 'batch_created_at': 1, 'bank_source': 1}
        )
        
        if not order:
            return {}
        
        return {
            'batch_number': order.get('batch_number', 0),
            'batch_status': order.get('batch_status', ''),
            'batch_created_at': order.get('batch_created_at'),
            'bank_source': order.get('bank_source', 'db')
        }
    
    def get_batch_status_count(self) -> Dict[str, int]:
        """获取各批次状态的数量"""
        if self.mongo is None:
            return {}
        
        pipeline = [
            {'$match': {'batch_number': {'$gt': 0}}},  # 只查询有批次号的记录
            {'$group': {
                '_id': '$batch_status',  # 按批次状态分组
                'count': {'$sum': 1}  # 统计数量
            }}
        ]
        
        result = list(self.mongo.refactoring_financing_order.aggregate(pipeline))
        
        # 格式化结果
        status_count = {}
        for item in result:
            status_count[item['_id']] = item['count']
        
        return status_count
