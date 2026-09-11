from app import create_app
from app import mongo

app = create_app()

with app.app_context():
    # 检查银行对账单invoice.seller_reference和融资单invoice_number之间的关联数据
    print("=== Checking seller_reference vs invoice_number mapping ===")
    
    try:
        # 获取所有已确认的银行对账单
        confirmed_statements = list(mongo.refactoring_bank_statement.find({
            'invoice.status': 'Financing confirmed'
        }))
        
        print(f"Total confirmed bank statements: {len(confirmed_statements)}")
        
        if confirmed_statements:
            # 获取所有融资订单的invoice_number集合，用于快速查找
            financing_orders = list(mongo.refactoring_financing_order.find())
            print(f"Total financing orders: {len(financing_orders)}")
            
            # 创建融资订单invoice_number的集合，支持快速查找
            invoice_number_set = set()
            for order in financing_orders:
                invoice_number = order.get('invoice_number', '')
                if invoice_number:
                    invoice_number_set.add(invoice_number)
            
            print(f"Total unique invoice_numbers in financing orders: {len(invoice_number_set)}")
            
            # 统计匹配情况
            matched_count = 0
            unmatched_count = 0
            matched_records = []
            
            # 检查银行对账单中的seller_reference是否在融资订单的invoice_number集合中
            for stmt in confirmed_statements:
                seller_reference = stmt['invoice'].get('seller_reference', '')
                
                if seller_reference and seller_reference in invoice_number_set:
                    matched_count += 1
                    # 找到匹配的融资订单
                    matching_order = mongo.refactoring_financing_order.find_one({
                        'invoice_number': seller_reference
                    })
                    if matching_order:
                        finance_request_number = matching_order.get('finance_request_number', '')
                        matched_records.append({
                            'seller_reference': seller_reference,
                            'finance_request_number': finance_request_number
                        })
                else:
                    unmatched_count += 1
            
            # 输出匹配结果
            print(f"\n=== Matching Results ===")
            print(f"Matched: {matched_count}")
            print(f"Unmatched: {unmatched_count}")
            print(f"Matching rate: {matched_count / (matched_count + unmatched_count) * 100:.2f}%")
            
            # 输出部分匹配记录作为示例
            if matched_records:
                print(f"\n=== Sample Matched Records (first 10) ===")
                for i, record in enumerate(matched_records[:10]):
                    print(f"  {i+1}. seller_reference={record['seller_reference']} -> FR={record['finance_request_number']}")
            
            # 输出部分不匹配的seller_reference作为示例
            if unmatched_count > 0:
                print(f"\n=== Sample Unmatched seller_reference (first 10) ===")
                unmatched_samples = []
                for stmt in confirmed_statements:
                    seller_reference = stmt['invoice'].get('seller_reference', '')
                    if seller_reference not in invoice_number_set:
                        unmatched_samples.append(seller_reference)
                        if len(unmatched_samples) >= 10:
                            break
                
                for i, ref in enumerate(unmatched_samples):
                    print(f"  {i+1}. {ref}")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()