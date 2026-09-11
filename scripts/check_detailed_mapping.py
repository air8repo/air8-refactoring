from app import create_app
from app import mongo

app = create_app()

with app.app_context():
    # 详细查询脚本，输出完整的关联数据
    print("=== Detailed Mapping Check ===")
    
    # 获取所有已确认的银行对账单
    confirmed_statements = list(mongo.refactoring_bank_statement.find({
        'invoice.status': 'Financing confirmed'
    }))
    
    print(f"Total confirmed bank statements: {len(confirmed_statements)}")
    
    # 统计匹配情况
    matched_count = 0
    unmatched_count = 0
    matched_details = []
    
    for stmt in confirmed_statements:
        seller_ref = stmt['invoice'].get('seller_reference', '')
        
        if seller_ref:
            # 查找对应的融资订单
            order = mongo.refactoring_financing_order.find_one({
                'invoice_number': seller_ref
            })
            
            if order:
                matched_count += 1
                matched_details.append({
                    'stmt_id': str(stmt['_id']),
                    'seller_reference': seller_ref,
                    'order_id': str(order['_id']),
                    'invoice_number': order['invoice_number'],
                    'finance_request_number': order['finance_request_number']
                })
            else:
                unmatched_count += 1
        else:
            unmatched_count += 1
    
    # 输出匹配结果
    print(f"\n=== Matching Results ===")
    print(f"Matched: {matched_count}")
    print(f"Unmatched: {unmatched_count}")
    print(f"Matching rate: {matched_count / (matched_count + unmatched_count) * 100:.2f}%")
    
    # 输出部分匹配记录作为示例
    if matched_details:
        print(f"\n=== Sample Matched Records (first 20) ===")
        for i, detail in enumerate(matched_details[:20]):
            print(f"  {i+1}. seller_ref={detail['seller_reference']} -> FR={detail['finance_request_number']}")
    
    # 输出完整的匹配数据到文件
    print(f"\n=== Writing detailed results to file ===")
    with open('mapping_results.csv', 'w') as f:
        # 写入表头
        f.write('stmt_id,seller_reference,order_id,invoice_number,finance_request_number\n')
        
        # 写入数据
        for detail in matched_details:
            f.write(f"{detail['stmt_id']},{detail['seller_reference']},{detail['order_id']},{detail['invoice_number']},{detail['finance_request_number']}\n")
    
    print(f"Results written to mapping_results.csv")
    print("Done!")