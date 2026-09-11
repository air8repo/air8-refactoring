#!/usr/bin/env python3
"""
查找refactoring_bank_statement中invoice.seller_reference发票号，
在融资表中找批次号，没有批次号的发票号找出来
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.services.aggregate_service import get_mongo

def find_invoices_without_batch():
    """找出没有批次号的发票号"""
    print("开始执行发票号批次检查...")
    
    # 1. 获取数据库连接
    print("尝试获取数据库连接...")
    try:
        # 直接导入扩展模块，获取mongo对象
        from backend.app.extensions import mongo as ext_mongo
        if ext_mongo is not None:
            print("✓ 从扩展模块获取数据库连接成功")
            mongo = ext_mongo
        else:
            print("从扩展模块获取数据库连接失败，尝试其他方式...")
            # 尝试创建Flask应用实例，初始化数据库连接
            from backend.app import create_app
            app = create_app()
            with app.app_context():
                from backend.app.extensions import mongo as app_mongo
                if app_mongo is not None:
                    print("✓ 在应用上下文中获取数据库连接成功")
                    mongo = app_mongo
                else:
                    print("在应用上下文中获取数据库连接失败")
                    return []
    except Exception as e:
        print(f"错误：获取数据库连接失败 - {str(e)}")
        import traceback
        traceback.print_exc()
        return []
    
    print("✓ 数据库连接成功")
    
    # 2. 获取银行对账单中的所有发票号
    print("\n1. 获取银行对账单中的发票号...")
    try:
        seller_references = mongo.refactoring_bank_statement.distinct('invoice.seller_reference', {
            'invoice.seller_reference': {'$ne': None, '$ne': ''}
        })
        print(f"✓ 共获取到 {len(seller_references)} 个唯一发票号")
    except Exception as e:
        print(f"错误：获取发票号失败 - {str(e)}")
        return []
    
    # 3. 查询融资表中的批次号和融资编号
    print("\n2. 查询融资表中的批次号和融资编号...")
    try:
        financing_orders = list(mongo.refactoring_financing_order.find({
            'invoice_number': {'$in': seller_references}
        }, {'invoice_number': 1, 'batch_number': 1, 'finance_request_number': 1}))
        
        # 构建发票号到批次信息的映射，包含批次号和融资编号
        invoice_to_batch_info = {}
        for order in financing_orders:
            invoice_num = order.get('invoice_number')
            batch_num = order.get('batch_number')
            finance_request_number = order.get('finance_request_number')
            invoice_to_batch_info[invoice_num] = {
                'batch_number': batch_num,
                'finance_request_number': finance_request_number
            }
        
        print(f"✓ 共查询到 {len(invoice_to_batch_info)} 个发票号的批次和融资编号信息")
    except Exception as e:
        print(f"错误：查询批次号和融资编号失败 - {str(e)}")
        return []
    
    # 4. 找出没有批次号的发票号
    print("\n3. 找出没有批次号的发票号...")
    invoices_without_batch = []
    invoices_with_batch = []
    
    # 收集没有批次号的发票号详细信息
    invoices_without_batch_detail = []
    
    for invoice in seller_references:
        batch_info = invoice_to_batch_info.get(invoice, {})
        batch_num = batch_info.get('batch_number')
        finance_request_number = batch_info.get('finance_request_number')
        
        if not batch_num:
            invoices_without_batch.append(invoice)
            invoices_without_batch_detail.append({
                'invoice_number': invoice,
                'finance_request_number': finance_request_number,
                'batch_number': batch_num
            })
        else:
            invoices_with_batch.append(invoice)
    
    # 5. 输出结果
    print("\n=== 检查结果 ===")
    print(f"总发票号数量: {len(seller_references)}")
    print(f"有批次号的发票数量: {len(invoices_with_batch)}")
    print(f"没有批次号的发票数量: {len(invoices_without_batch)}")
    
    if invoices_without_batch_detail:
        print("\n没有批次号的发票号列表 (发票号 | 融资编号 | 批次号):")
        print("-" * 80)
        for detail in invoices_without_batch_detail[:10]:  # 只显示前10个
            print(f"  - {detail['invoice_number']} | {detail['finance_request_number']} | {detail['batch_number']}")
        if len(invoices_without_batch_detail) > 10:
            print(f"  ... 还有 {len(invoices_without_batch_detail) - 10} 个未显示")
        
        # 将结果保存到文件
        output_file = "invoices_without_batch.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("没有批次号的发票号列表\n")
            f.write("=" * 80 + "\n")
            f.write(f"{'发票号':<20} {'融资编号':<30} {'批次号':<15}\n")
            f.write("-" * 80 + "\n")
            for detail in invoices_without_batch_detail:
                f.write(f"{detail['invoice_number']:<20} {detail['finance_request_number']:<30} {detail['batch_number'] if detail['batch_number'] else '无':<15}\n")
        print(f"\n✓ 结果已保存到文件: {output_file}")
    else:
        print("\n✓ 所有发票号都有对应的批次号")
    
    # 6. 打印统计信息
    print("\n=== 统计信息 ===")
    total_invoices = len(seller_references)
    with_batch_pct = (len(invoices_with_batch) / total_invoices * 100) if total_invoices > 0 else 0
    without_batch_pct = (len(invoices_without_batch) / total_invoices * 100) if total_invoices > 0 else 0
    
    print(f"总发票数: {total_invoices}")
    print(f"有批次号的发票数: {len(invoices_with_batch)} ({with_batch_pct:.2f}%)")
    print(f"无批次号的发票数: {len(invoices_without_batch)} ({without_batch_pct:.2f}%)")
    
    return invoices_without_batch

if __name__ == "__main__":
    result = find_invoices_without_batch()
    print(f"\n执行完成，共找到 {len(result)} 个没有批次号的发票号")
    sys.exit(0 if len(result) == 0 else 1)
