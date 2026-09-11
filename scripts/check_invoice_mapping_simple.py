from app import create_app
from app import mongo

app = create_app()

with app.app_context():
    # 简化的检查脚本，专注于发票号映射关系
    print("=== Simplified Invoice Mapping Check ===")
    
    try:
        # 只获取前10条银行对账单记录
        bank_statements = list(mongo.refactoring_bank_statement.find({})
                              .limit(10))
        print(f"Found {len(bank_statements)} bank statements")
        
        # 只获取前10条融资订单
        financing_orders = list(mongo.refactoring_financing_order.find({})
                               .limit(10))
        print(f"Found {len(financing_orders)} financing orders")
        
        # 检查银行对账单中的system_invoice_id
        print("\n=== Bank Statement system_invoice_id ===")
        for i, stmt in enumerate(bank_statements):
            invoice = stmt.get('invoice', {})
            system_invoice_id = invoice.get('system_invoice_id', 'N/A')
            print(f"Stmt {i+1}: system_invoice_id={system_invoice_id}")
        
        # 检查融资订单中的invoice_number
        print("\n=== Financing Order invoice_number ===")
        for i, order in enumerate(financing_orders):
            invoice_number = order.get('invoice_number', 'N/A')
            finance_request_number = order.get('finance_request_number', 'N/A')
            print(f"Order {i+1}: invoice_number={invoice_number}, FR={finance_request_number}")
        
        # 尝试直接匹配
        print("\n=== Direct Matching Attempt ===")
        for stmt in bank_statements:
            system_invoice_id = stmt['invoice'].get('system_invoice_id', '')
            if not system_invoice_id:
                continue
                
            print(f"Trying to match system_invoice_id: {system_invoice_id}")
            
            # 尝试直接匹配
            order = mongo.refactoring_financing_order.find_one({
                'invoice_number': system_invoice_id
            })
            
            if order:
                print(f"  ✅ MATCHED: FR={order['finance_request_number']}")
            else:
                print(f"  ❌ NOT MATCHED")
                
                # 尝试转换类型后匹配
                str_id = str(system_invoice_id)
                order2 = mongo.refactoring_financing_order.find_one({
                    'invoice_number': str_id
                })
                if order2:
                    print(f"  ✅ MATCHED after string conversion: FR={order2['finance_request_number']}")
                
                try:
                    int_id = int(system_invoice_id)
                    order3 = mongo.refactoring_financing_order.find_one({
                        'invoice_number': int_id
                    })
                    if order3:
                        print(f"  ✅ MATCHED after int conversion: FR={order3['finance_request_number']}")
                except (ValueError, TypeError):
                    pass
                    
    except Exception as e:
        print(f"Error occurred: {e}")
        import traceback
        traceback.print_exc()