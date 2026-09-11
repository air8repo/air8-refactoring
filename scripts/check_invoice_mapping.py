from app import create_app
from app import mongo

app = create_app()

with app.app_context():
    # 检查银行对账单和融资单之间的发票号映射关系
    print("=== Checking invoice mapping between bank statements and financing orders ===")
    
    # 获取所有已确认的银行对账单
    confirmed_statements = list(mongo.refactoring_bank_statement.find({
        'invoice.status': 'Financing confirmed'
    }))
    
    print(f"Total confirmed bank statements: {len(confirmed_statements)}")
    
    if confirmed_statements:
        # 获取所有融资订单
        financing_orders = list(mongo.refactoring_financing_order.find())
        print(f"Total financing orders: {len(financing_orders)}")
        
        # 提取所有融资订单的invoice_number
        financing_invoice_numbers = [order.get('invoice_number', '') for order in financing_orders if order.get('invoice_number')]
        print(f"Total unique invoice_numbers in financing orders: {len(set(financing_invoice_numbers))}")
        
        # 检查银行对账单中的system_invoice_id格式
        print("\n=== Checking system_invoice_id format ===")
        for i, stmt in enumerate(confirmed_statements[:5]):
            system_invoice_id = stmt['invoice'].get('system_invoice_id', '')
            print(f"Bank statement {i+1}: system_invoice_id={system_invoice_id}, type={type(system_invoice_id)}")
        
        # 检查融资订单中的invoice_number格式
        print("\n=== Checking invoice_number format ===")
        for i, order in enumerate(financing_orders[:5]):
            invoice_number = order.get('invoice_number', '')
            print(f"Financing order {i+1}: invoice_number={invoice_number}, type={type(invoice_number)}")
        
        # 尝试查找匹配的记录
        print("\n=== Trying to find matching records ===")
        matched_count = 0
        unmatched_count = 0
        
        for stmt in confirmed_statements:
            system_invoice_id = stmt['invoice'].get('system_invoice_id', '')
            
            # 尝试直接匹配
            financing_order = mongo.refactoring_financing_order.find_one({
                'invoice_number': system_invoice_id
            })
            
            if financing_order:
                matched_count += 1
                print(f"MATCHED: system_invoice_id={system_invoice_id} -> finance_request_number={financing_order['finance_request_number']}")
            else:
                unmatched_count += 1
                # 尝试转换类型后匹配（例如字符串转数字或数字转字符串）
                try:
                    # 尝试将system_invoice_id转换为字符串
                    str_id = str(system_invoice_id)
                    financing_order = mongo.refactoring_financing_order.find_one({
                        'invoice_number': str_id
                    })
                    if financing_order:
                        matched_count += 1
                        unmatched_count -= 1
                        print(f"MATCHED after conversion: system_invoice_id={system_invoice_id} -> invoice_number={str_id} -> finance_request_number={financing_order['finance_request_number']}")
                    else:
                        # 尝试将system_invoice_id转换为整数
                        int_id = int(system_invoice_id)
                        financing_order = mongo.refactoring_financing_order.find_one({
                            'invoice_number': int_id
                        })
                        if financing_order:
                            matched_count += 1
                            unmatched_count -= 1
                            print(f"MATCHED after conversion: system_invoice_id={system_invoice_id} -> invoice_number={int_id} -> finance_request_number={financing_order['finance_request_number']}")
                except (ValueError, TypeError):
                    pass
        
        print(f"\n=== Mapping results ===")
        print(f"Matched: {matched_count}")
        print(f"Unmatched: {unmatched_count}")
        print(f"Matching rate: {matched_count / (matched_count + unmatched_count) * 100:.2f}%")
        
        # 如果匹配率很低，尝试查找可能的匹配模式
        if matched_count / (matched_count + unmatched_count) < 0.1:
            print("\n=== Trying to find matching patterns ===")
            # 打印一些示例，看看是否有明显的模式
            print("Sample system_invoice_id from bank statements:")
            for i, stmt in enumerate(confirmed_statements[:10]):
                print(f"  {stmt['invoice'].get('system_invoice_id', '')}")
            
            print("Sample invoice_number from financing orders:")
            for i, order in enumerate(financing_orders[:10]):
                print(f"  {order.get('invoice_number', '')}")