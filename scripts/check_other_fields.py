from app import create_app
from app import mongo

app = create_app()

with app.app_context():
    print("=== Checking other possible关联字段 ===")
    
    # 获取银行对账单的完整结构
    bank_stmt = mongo.refactoring_bank_statement.find_one()
    print("\n=== Bank Statement Full Structure ===")
    for key, value in bank_stmt.items():
        print(f"{key}: {type(value)}")
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                print(f"  {sub_key}: {sub_value}")
    
    # 获取融资订单的完整结构
    financing_order = mongo.refactoring_financing_order.find_one()
    print("\n=== Financing Order Full Structure ===")
    for key, value in financing_order.items():
        print(f"{key}: {type(value)}")
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                print(f"  {sub_key}: {sub_value}")
    
    # 检查融资订单中是否有system_invoice_id字段
    print("\n=== Checking if financing orders have system_invoice_id ===")
    orders_with_system_invoice = list(mongo.refactoring_financing_order.find({
        'system_invoice_id': {'$exists': True}
    }).limit(5))
    print(f"Found {len(orders_with_system_invoice)} orders with system_invoice_id")
    
    for order in orders_with_system_invoice:
        print(f"  FR={order['finance_request_number']}, system_invoice_id={order['system_invoice_id']}")
    
    # 检查银行对账单中是否有其他可能关联的字段
    print("\n=== Checking other possible关联字段 in bank statements ===")
    for stmt in mongo.refactoring_bank_statement.find().limit(3):
        print(f"Stmt DB ref: {stmt['finance'].get('db_finance_ref', 'N/A')}")
        print(f"Stmt invoice: {stmt['invoice'].get('seller_reference', 'N/A')}")
        print()
    
    # 检查融资订单中是否有与db_finance_ref匹配的字段
    print("\n=== Checking if financing orders have matching db_finance_ref ===")
    stmt = mongo.refactoring_bank_statement.find_one()
    db_finance_ref = stmt['finance'].get('db_finance_ref', '')
    print(f"Using db_finance_ref: {db_finance_ref}")
    
    # 搜索所有融资订单，查找可能的匹配
    matching_orders = []
    for order in mongo.refactoring_financing_order.find():
        # 检查reference_no字段
        ref_no = order.get('reference_no', '')
        if db_finance_ref in str(ref_no):
            matching_orders.append(order)
    
    print(f"Found {len(matching_orders)} orders with db_finance_ref in reference_no")
    for order in matching_orders:
        print(f"  FR={order['finance_request_number']}, reference_no={order['reference_no']}")