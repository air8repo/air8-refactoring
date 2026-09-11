#!/usr/bin/env python3
"""
简单测试Settlement Schedule修复效果
直接调用get_settlement_schedule函数，验证金额是否正确
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, '.')

from backend.app import create_app

def simple_test_settlement():
    """简单测试Settlement Schedule修复效果"""
    print("=" * 60)
    print("简单测试Settlement Schedule修复效果")
    print("=" * 60)
    
    # 创建Flask应用实例
    app = create_app()
    
    with app.app_context():
        # 从extensions获取mongo实例
        from backend.app.extensions import mongo
        
        if mongo is None:
            print("❌ MongoDB连接失败")
            return False
        
        print("✅ MongoDB连接成功")
        
        # 检查集合数据
        count = mongo.refactoring_financing_overview.count_documents({})
        print(f"\n1. 集合中文档数量: {count}")
        
        # 检查第一个文档的详细信息
        print("\n2. 检查第一个文档的详细信息:")
        first_doc = mongo.refactoring_financing_overview.find_one({})
        if first_doc:
            print(f"   finance_request_number: {first_doc.get('finance_request_number')}")
            print(f"   outstanding_loan_exclude_wip: {first_doc.get('outstanding_loan_exclude_wip')}")
            print(f"   settled_db_loan: {first_doc.get('settled_db_loan')}")
            
            # 检查order_details.due_date
            order_details = first_doc.get('order_details', {})
            due_date = order_details.get('due_date')
            print(f"   order_details.due_date: {due_date} (类型: {type(due_date)})")
            if due_date:
                print(f"   due_date_str: {due_date.strftime('%Y-%m-%d')}")
        
        # 调用修复后的get_settlement_schedule函数
        from backend.app.routes.main import get_settlement_schedule
        
        print("\n3. 调用get_settlement_schedule函数")
        schedule = get_settlement_schedule()
        
        print(f"   due_dates数量: {len(schedule['due_dates'])}")
        
        if len(schedule['due_dates']) > 0:
            print("\n4. 查看所有日期的金额数据:")
            print("-" * 40)
            
            # 查看所有日期的数据，找出非零金额
            found_non_zero = False
            
            for date in schedule['due_dates']:
                totals = schedule['totals'][date]
                total = sum(totals.values())
                
                if total > 0:
                    print(f"\n日期: {date} (非零金额!)")
                    print(f"  DB贷款金额: {totals['db_loan_amt']:.2f}")
                    print(f"  买方还款金额: {totals['repayment_from_buyer']:.2f}")
                    print(f"  未偿金额: {totals['os_amt_in_db']:.2f}")
                    print(f"  已结算金额: {totals['settled_amt_by_air8']:.2f}")
                    found_non_zero = True
            
            if not found_non_zero:
                print("\n所有日期的金额都为0")
                
                # 查看第一个文档的完整数据，调试问题
                print("\n5. 调试第一个文档的完整数据:")
                print("-" * 40)
                if first_doc:
                    # 检查order_details的完整内容
                    print(f"   order_details完整内容: {first_doc.get('order_details')}")
                    
                    # 检查totals字段
                    print(f"   totals字段: {first_doc.get('totals')}")
                    
                    # 检查bank_statements
                    bank_statements = first_doc.get('bank_statements', [])
                    if bank_statements:
                        print(f"   bank_statements[0].usd_finance_amount: {bank_statements[0].get('usd_finance_amount')}")
                        print(f"   bank_statements[0].outstanding_amount_usd: {bank_statements[0].get('outstanding_amount_usd')}")
                    
                    # 检查repayments
                    repayments = first_doc.get('repayments', [])
                    if repayments:
                        print(f"   repayments[0].repayment_from_buyer_to_air8: {repayments[0].get('repayment_from_buyer_to_air8')}")
                        print(f"   repayments[0].settled_amt_by_air8_to_db: {repayments[0].get('settled_amt_by_air8_to_db')}")
            
            # 计算汇总金额
            total_db_loan = sum(item['db_loan_amt'] for item in schedule['totals'].values())
            total_repayment = sum(item['repayment_from_buyer'] for item in schedule['totals'].values())
            total_os = sum(item['os_amt_in_db'] for item in schedule['totals'].values())
            total_settled = sum(item['settled_amt_by_air8'] for item in schedule['totals'].values())
            
            print("\n6. 总金额汇总:")
            print("-" * 40)
            print(f"  总DB贷款金额: {total_db_loan:.2f}")
            print(f"  总买方还款金额: {total_repayment:.2f}")
            print(f"  总未偿金额: {total_os:.2f}")
            print(f"  总已结算金额: {total_settled:.2f}")
            
            # 验证金额是否不为0
            if total_db_loan > 0 or total_repayment > 0 or total_os > 0 or total_settled > 0:
                print("\n✅ 修复成功! Settlement Schedule返回了非零金额")
                return True
            else:
                print("\n❌ 修复失败! Settlement Schedule返回的金额仍然为0")
                return False
        else:
            print("\n❌ 没有找到due_dates，无法测试")
            return False

if __name__ == "__main__":
    success = simple_test_settlement()
    print("\n" + "=" * 60)
    if success:
        print("测试通过! Settlement Schedule修复成功")
    else:
        print("测试失败! Settlement Schedule修复需要进一步调整")
    print("=" * 60)
