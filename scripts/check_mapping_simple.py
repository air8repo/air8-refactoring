from app import create_app
from app import mongo

app = create_app()

with app.app_context():
    # 简单查询脚本，检查seller_reference和invoice_number的关联
    print("=== Simple Mapping Check ===")
    
    # 获取第一条银行对账单
    stmt = mongo.refactoring_bank_statement.find_one()
    if stmt:
        seller_ref = stmt['invoice'].get('seller_reference', 'N/A')
        print(f"Bank statement seller_reference: {seller_ref}")
        
        # 查找对应的融资订单
        order = mongo.refactoring_financing_order.find_one({'invoice_number': seller_ref})
        if order:
            print(f"Found matching financing order: FR={order.get('finance_request_number')}")
        else:
            print("No matching financing order found")
    
    print("\n=== Checking sample data ===")
    
    # 检查前5条银行对账单的seller_reference
    for i, stmt in enumerate(mongo.refactoring_bank_statement.find().limit(5)):
        seller_ref = stmt['invoice'].get('seller_reference', 'N/A')
        print(f"Stmt {i+1}: seller_ref={seller_ref}")
    
    # 检查前5条融资订单的invoice_number
    for i, order in enumerate(mongo.refactoring_financing_order.find().limit(5)):
        invoice_num = order.get('invoice_number', 'N/A')
        print(f"Order {i+1}: invoice_num={invoice_num}")
    
    # 统计可能的匹配
    print("\n=== Counting potential matches ===")
    
    # 获取所有seller_reference
    seller_refs = []
    for stmt in mongo.refactoring_bank_statement.find():
        seller_ref = stmt['invoice'].get('seller_reference', '')
        if seller_ref:
            seller_refs.append(seller_ref)
    
    # 获取所有invoice_number
    invoice_nums = []
    for order in mongo.refactoring_financing_order.find():
        invoice_num = order.get('invoice_number', '')
        if invoice_num:
            invoice_nums.append(invoice_num)
    
    # 查找交集
    common = set(seller_refs) & set(invoice_nums)
    print(f"Common values between seller_reference and invoice_number: {common}")
    print(f"Number of common values: {len(common)}")
    
    if common:
        print("\nSample matches:")
        for value in list(common)[:5]:
            order = mongo.refactoring_financing_order.find_one({'invoice_number': value})
            if order:
                print(f"  {value} -> FR={order.get('finance_request_number')}")
