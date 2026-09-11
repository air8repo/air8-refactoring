from app import create_app
from app import mongo

app = create_app()

with app.app_context():
    # 检查失败的seller_reference是否在融资订单中存在
    print("=== Checking failed matches ===")
    
    # 获取所有已确认的银行对账单
    confirmed_statements = list(mongo.refactoring_bank_statement.find({
        'invoice.status': 'Financing confirmed'
    }))
    
    # 获取所有融资订单的invoice_number集合
    invoice_nums = set()
    for order in mongo.refactoring_financing_order.find():
        invoice_num = order.get('invoice_number', '')
        if invoice_num:
            invoice_nums.add(invoice_num)
    
    # 检查前20条失败的seller_reference
    print(f"Checking first 20 seller_references that might fail...")
    
    for i, stmt in enumerate(confirmed_statements[:20]):
        seller_ref = stmt['invoice'].get('seller_reference', '')
        
        if seller_ref not in invoice_nums:
            print(f"\nStmt {i+1}: seller_ref={seller_ref}")
            print(f"  Not found in financing_order.invoice_number")
            
            # 检查是否在cross_ref_inv_no中存在
            cross_ref_order = mongo.refactoring_financing_order.find_one({'cross_ref_inv_no': seller_ref})
            if cross_ref_order:
                print(f"  ✅ Found in cross_ref_inv_no: FR={cross_ref_order['finance_request_number']}")
            else:
                print(f"  ❌ Not found in cross_ref_inv_no")
            
            # 检查是否在reference_no中存在
            ref_no_order = mongo.refactoring_financing_order.find_one({'reference_no': seller_ref})
            if ref_no_order:
                print(f"  ✅ Found in reference_no: FR={ref_no_order['finance_request_number']}")
            else:
                print(f"  ❌ Not found in reference_no")
            
            # 检查是否在reference_no中包含
            ref_no_contains_order = None
            for order in mongo.refactoring_financing_order.find():
                if seller_ref in str(order.get('reference_no', '')):
                    ref_no_contains_order = order
                    break
            
            if ref_no_contains_order:
                print(f"  ✅ Found in reference_no (contains): FR={ref_no_contains_order['finance_request_number']}")
            else:
                print(f"  ❌ Not found in reference_no (contains)")
            
            # 检查是否在cross_ref_inv_no中包含
            cross_ref_contains_order = None
            for order in mongo.refactoring_financing_order.find():
                if seller_ref in str(order.get('cross_ref_inv_no', '')):
                    cross_ref_contains_order = order
                    break
            
            if cross_ref_contains_order:
                print(f"  ✅ Found in cross_ref_inv_no (contains): FR={cross_ref_contains_order['finance_request_number']}")
            else:
                print(f"  ❌ Not found in cross_ref_inv_no (contains)")