from app import create_app
from app import mongo

app = create_app()

with app.app_context():
    # 检查融资订单表的结构和数据
    print("=== Checking financing_order collection ===")
    
    # 获取所有融资订单
    financing_orders = list(mongo.refactoring_financing_order.find())
    print(f"Total financing orders: {len(financing_orders)}")
    
    if financing_orders:
        # 检查第一条记录的结构
        first_order = financing_orders[0]
        print("\nFirst financing order keys:", list(first_order.keys()))
        
        # 检查是否有finance_request_number字段
        print("Has finance_request_number:", 'finance_request_number' in first_order)
        if 'finance_request_number' in first_order:
            print("finance_request_number value:", first_order['finance_request_number'])
        
        # 检查invoice_number字段
        print("Has invoice_number:", 'invoice_number' in first_order)
        if 'invoice_number' in first_order:
            print("invoice_number value:", first_order['invoice_number'])
        
        # 检查其他可能的关联字段
        print("\n=== Checking sample invoice numbers ===")
        for i, order in enumerate(financing_orders[:5]):
            invoice_num = order.get('invoice_number', 'N/A')
            fr_num = order.get('finance_request_number', 'N/A')
            print(f"Order {i+1}: invoice_number={invoice_num}, finance_request_number={fr_num}")
        
        # 检查是否有通过db_finance_ref关联的可能
        print("\n=== Checking bank statement and financing order connection ===")
        # 获取第一条银行对账单记录
        bank_stmt = mongo.refactoring_bank_statement.find_one()
        if bank_stmt:
            db_finance_ref = bank_stmt['finance'].get('db_finance_ref', '')
            print(f"First bank statement db_finance_ref: {db_finance_ref}")
            
            # 尝试通过db_finance_ref查找融资订单
            for order in financing_orders:
                if 'reference_no' in order and db_finance_ref in order['reference_no']:
                    print(f"Found matching order! reference_no: {order['reference_no']}")
                    break
            else:
                print("No matching order found by db_finance_ref")
    else:
        print("No financing orders found!")