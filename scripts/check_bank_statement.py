from app import create_app
from app import mongo

app = create_app()

with app.app_context():
    # 专门查找状态为'Financing confirmed'的记录
    print("=== Searching for 'Financing confirmed' bank statements ===")
    
    # 尝试使用过滤条件查询
    confirmed_statements = list(mongo.refactoring_bank_statement.find({
        'invoice.status': 'Financing confirmed'
    }))
    
    print(f"Found {len(confirmed_statements)} confirmed statements with filter {{'invoice.status': 'Financing confirmed'}}")
    
    if confirmed_statements:
        # 检查finance_request_number字段
        print("\n=== Checking finance_request_number field ===")
        first_stmt = confirmed_statements[0]
        
        # 检查finance子对象
        if 'finance' in first_stmt:
            finance = first_stmt['finance']
            print("Finance field keys:", list(finance.keys()))
            print("Has finance_request_number:", 'finance_request_number' in finance)
            if 'finance_request_number' in finance:
                print("finance_request_number value:", finance['finance_request_number'])
        
        # 检查finance子对象中的db_finance_ref字段
        if 'finance' in first_stmt:
            db_finance_ref = first_stmt['finance'].get('db_finance_ref', '')
            print(f"db_finance_ref: {db_finance_ref}")
        
        # 检查system_invoice_id
        invoice = first_stmt.get('invoice', {})
        system_invoice_id = invoice.get('system_invoice_id', '')
        print(f"system_invoice_id: {system_invoice_id}")
        
        # 尝试通过system_invoice_id查找融资订单
        print(f"\n=== Searching financing_order by system_invoice_id {system_invoice_id} ===")
        financing_order = mongo.refactoring_financing_order.find_one({'invoice_number': system_invoice_id})
        if financing_order:
            print("Found financing order!")
            print(f"Has finance_request_number: {'finance_request_number' in financing_order}")
            if 'finance_request_number' in financing_order:
                print(f"finance_request_number: {financing_order['finance_request_number']}")
        else:
            print("No financing order found!")
        
        # 检查是否有finance_request_number为None或空的记录
        print("\n=== Checking for missing finance_request_number ===")
        missing_count = 0
        for stmt in confirmed_statements[:10]:  # 检查前10条
            finance = stmt.get('finance', {})
            frn = finance.get('finance_request_number')
            if not frn:
                missing_count += 1
        print(f"Missing finance_request_number in first 10 statements: {missing_count}")
    else:
        print("No bank statement records found")
