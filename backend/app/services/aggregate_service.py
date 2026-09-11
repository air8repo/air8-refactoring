from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any
from flask import current_app
import logging
import multiprocessing
from functools import partial

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_mongo():
    """获取已初始化的mongo对象"""
    mongo = None
    
    # 首先尝试直接从extensions模块导入（最高优先级，适合测试环境）
    try:
        from backend.app.extensions import mongo as ext_mongo
        if ext_mongo is not None:
            return ext_mongo
    except Exception:
        pass
    
    # 然后尝试从app模块导入
    try:
        from backend.app import mongo as app_mongo
        if app_mongo is not None:
            return app_mongo
    except Exception:
        pass
    
    # 最后尝试从current_app.extensions获取（适合运行环境）
    try:
        if hasattr(current_app, 'extensions'):
            mongo = current_app.extensions.get('mongo')
            if mongo is not None:
                return mongo
    except Exception:
        pass
    
    return None


def _pick_latest_statement(statements):
    """从多条银行对账单原始文档中，按 invoice.creation_time 降序取最新一条；无记录返回 None"""
    if not statements:
        return None

    def sort_key(statement):
        creation_time = statement.get('invoice', {}).get('creation_time')
        return creation_time or datetime.min

    return sorted(statements, key=sort_key, reverse=True)[0]


def _build_refactor_snapshot_fields(latest_statement):
    """由最新一条银行对账单派生 refactoring_financing_overview 的再保理相关顶层字段"""
    if latest_statement is None:
        return {
            'refactoring_status': 'init',
            'refactor_id': '',
            'refactor_portal_status': '',
            'refactor_settlement_status': '',
            'refactor_currency': '',
            'refactor_amount': None,
            'refactor_interest_rate_pct': None,
            'refactor_interest_amount': None,
            'refactor_purchase_price': None,
        }

    invoice = latest_statement.get('invoice', {})
    finance = latest_statement.get('finance', {})
    return {
        'refactoring_status': finance.get('status', 'init'),
        'refactor_id': invoice.get('system_invoice_id', ''),
        'refactor_portal_status': invoice.get('status', ''),
        'refactor_settlement_status': latest_statement.get('settlement_status', ''),
        'refactor_currency': invoice.get('currency', ''),
        'refactor_amount': finance.get('finance_amount'),
        'refactor_interest_rate_pct': finance.get('interest_rate_pct'),
        'refactor_interest_amount': finance.get('interest_amount'),
        'refactor_purchase_price': finance.get('purchase_price'),
    }

class AggregateService:
    """数据聚合服务"""

    def _format_bank_statement(self, statement):
        """将单条银行对账单原始文档格式化为写入 overview.bank_statements[] 的扁平结构"""
        usd_details = statement.get('usd_details', {})
        invoice = statement.get('invoice', {})
        finance = statement.get('finance', {})
        return {
            'actual_upload_date': datetime.now(),
            'db_finance_ref': finance.get('db_finance_ref'),
            'finance_amount': finance.get('finance_amount'),
            'interest_amount_usd': usd_details.get('interest_amount'),
            'invoice_status': invoice.get('status'),
            'outstanding_amount_usd': usd_details.get('outstanding_amount'),
            'purchase_price_usd': usd_details.get('purchase_price'),
            'start_date': finance.get('start_date'),
            'status': finance.get('status'),
            'system_invoice_id': invoice.get('system_invoice_id'),
            'tenor': finance.get('tenor'),
            'invoice_buyer_reference': invoice.get('buyer_reference'),
            'invoice_seller_reference': invoice.get('seller_reference'),
            'parties_seller_erp_id': statement.get('parties', {}).get('seller_erp_id'),
            'parties_buyer_erp_id': statement.get('parties', {}).get('buyer_erp_id'),
            'parties_buyer_name': statement.get('parties', {}).get('buyer_name'),
            'parties_seller_name': statement.get('parties', {}).get('seller_name'),
            'invoice_issue_date': invoice.get('issue_date'),
            'invoice_due_date': invoice.get('due_date'),
            'invoice_adjusted_due_date': invoice.get('adjusted_due_date'),
            'finance_due_date': finance.get('due_date'),
            'invoice_currency': invoice.get('currency'),
            'invoice_original_amount': invoice.get('original_amount'),
            'invoice_settlement_date': invoice.get('settlement_date'),
            'invoice_creation_time': invoice.get('creation_time'),
            'finance_reference_rate_pct': finance.get('reference_rate'),
            'usd_original_amount': usd_details.get('original_amount'),
            'usd_finance_amount': usd_details.get('finance_amount'),
            'usd_outstanding_amount': usd_details.get('outstanding_amount'),
            'usd_interest_amount': usd_details.get('interest_amount'),
            'usd_purchase_price': usd_details.get('purchase_price'),
            'interest_rate_pct': finance.get('interest_rate_pct'),
            'invoice_vat_rate': invoice.get('vat_rate'),
            'invoice_vat_amount': invoice.get('vat_amount'),
            'outstanding_amount': finance.get('outstanding_amount'),
            'purchase_price': finance.get('purchase_price'),
            'settlement_status': statement.get('settlement_status'),
        }

    def _process_statement_group(self, seller_reference, statements, invoice_to_financing, fr_to_repayments):
        """处理某个 seller_reference 对应的全部银行对账单，生成一条融资概览记录"""
        financing_order = invoice_to_financing.get(seller_reference)
        if not financing_order:
            return None

        finance_request_number = financing_order.get('finance_request_number')
        if not finance_request_number:
            return None

        repayments = fr_to_repayments.get(finance_request_number, [])

        sorted_statements = sorted(
            statements,
            key=lambda s: s.get('invoice', {}).get('creation_time') or datetime.min,
            reverse=True
        )
        bank_statements = [self._format_bank_statement(s) for s in sorted_statements]
        latest_statement = sorted_statements[0] if sorted_statements else None
        refactor_fields = _build_refactor_snapshot_fields(latest_statement)

        formatted_repayments = []
        for repayment in repayments:
            formatted_repayments.append({
                'overdue_interest_wip': repayment.get('adjusted_interest_charges'),
                'repayment_from_buyer_to_air8': repayment.get('cumulative_repayment'),
                'repayment_status': repayment.get('repayment_status'),
                'settled_amt_by_air8_to_db': repayment.get('cumulative_repaid_principle'),
                'settlement_amount': repayment.get('os_balance'),
                'settlement_date': repayment.get('settlement_date')
            })

        order_details = {
            'adjusted_due_date': financing_order.get('due_date'),
            'air8_finance_amt': financing_order.get('actual_financing_amount'),
            'buyer_reference': financing_order.get('reference_no'),
            'currency': financing_order.get('trade_currency'),
            'due_date': financing_order.get('due_date'),
            'fr_settlement_date': financing_order.get('actual_funding_date'),
            'interest_rate_pct': financing_order.get('interest_rate_fee_charge'),
            'invoice_number': financing_order.get('invoice_number'),
            'issue_date': financing_order.get('invoice_date'),
            'maturity_date': financing_order.get('due_date'),
            'original_amount': financing_order.get('trade_amount'),
            'seller_reference': financing_order.get('reference_no'),
            'actual_tenor': financing_order.get('actual_tenor'),
            'collection_period': financing_order.get('collection_period'),
        }

        # totals 只应基于最新一条快照计算，避免同一融资单的历史阶段性对账单被重复加总
        totals = self._calculate_totals(financing_order, repayments, [latest_statement] if latest_statement else [])

        record = {
            'finance_request_number': finance_request_number,
            'buyer_erp_id': financing_order.get('buyer_code'),
            'buyer_name': financing_order.get('buyer_name'),
            'seller_erp_id': financing_order.get('supplier_code'),
            'seller_name': financing_order.get('supplier_name', ''),
            'summary_status': financing_order.get('status'),
            'loan_submission_batch': financing_order.get('batch_number', 0),
            'seq': 0,
            'order_details': order_details,
            'bank_statements': bank_statements,
            'repayments': formatted_repayments,
            'totals': totals,
            'updated_at': datetime.now(),
            'settled_in_air8': financing_order.get('settled_in_air8', ''),
            'db_loan_settle_date': financing_order.get('db_loan_settle_date', ''),
            'invoice_settlement_date_db_updated': '',
            'overdue_interest_settled_wip': '',
            'overdue_interest_od_wip': '',
            'air8_settled_fr_amt': totals.get('air8_settled_fr_amt'),
            'settled_db_loan': totals.get('settled_db_loan'),
            'outstanding_loan_exclude_wip': totals.get('outstanding_loan_exclude_wip'),
            'wip_pending_amount': totals.get('wip_pending_amount'),
            'financing_amount_trade_currency': financing_order.get('financing_amount_trade_currency'),
            'interest_amount_trade_currency': financing_order.get('financing_interest'),
            'interest_rate_pct': financing_order.get('interest_rate_fee_charge'),
            'funder': financing_order.get('insurer'),
        }
        record.update(refactor_fields)
        return record

    def aggregate_financing_overview(self):
        """聚合融资概览数据，按照用户要求的五个步骤进行处理"""
        mongo = get_mongo()
        if mongo is None:
            return {
                'success': False,
                'count': 0,
                'message': '数据库未连接'
            }
        
        try:
            # 第一步：筛选bank_statement表中finance.status="Loan booked"的数据
            logger.info("开始聚合融资概览数据")
            
            # 计算符合条件的记录总数
            confirmed_statements_count = mongo.refactoring_bank_statement.count_documents({})
            
            logger.info(f"筛选出 {confirmed_statements_count} 条状态为'Loan booked'的银行对账单")
            
            processed_count = 0
            
            if confirmed_statements_count == 0:
                logger.info("没有符合条件的银行对账单，跳过聚合")
                total_count = mongo.refactoring_financing_overview.count_documents({})
                return {
                    'success': True,
                    'count': total_count,
                    'message': f'没有符合条件的银行对账单，总计 {total_count} 条融资概览记录'
                }
            
            # 第二步：批量获取所有seller_reference
            # 使用distinct查询直接获取唯一的seller_reference
            seller_references = mongo.refactoring_bank_statement.distinct('invoice.seller_reference', {
                'invoice.seller_reference': {'$ne': None}
            })
            
            logger.info(f"提取出 {len(seller_references)} 个有效的seller_reference")
            
            if not seller_references:
                logger.info("没有有效的seller_reference，跳过聚合")
                total_count = mongo.refactoring_financing_overview.count_documents({})
                return {
                    'success': True,
                    'count': total_count,
                    'message': f'没有有效的seller_reference，总计 {total_count} 条融资概览记录'
                }
            
            # 第三步：批量查询融资订单，减少数据库查询次数
            financing_orders = list(mongo.refactoring_financing_order.find({
                'invoice_number': {'$in': seller_references}
            }))
            
            logger.info(f"批量查询到 {len(financing_orders)} 条融资订单")
            
            # 创建invoice_number到融资订单的映射，便于快速查找
            invoice_to_financing = {}
            for order in financing_orders:
                invoice_num = order.get('invoice_number')
                if invoice_num:
                    invoice_to_financing[invoice_num] = order
            
            # 第四步：提取所有finance_request_number
            finance_request_numbers = [order.get('finance_request_number') for order in financing_orders if order.get('finance_request_number')]
            finance_request_numbers = list(set(filter(None, finance_request_numbers)))  # 去重
            
            logger.info(f"提取出 {len(finance_request_numbers)} 个有效的finance_request_number")
            
            if not finance_request_numbers:
                logger.info("没有有效的finance_request_number，跳过聚合")
                total_count = mongo.refactoring_financing_overview.count_documents({})
                return {
                    'success': True,
                    'count': total_count,
                    'message': f'没有有效的finance_request_number，总计 {total_count} 条融资概览记录'
                }
            
            # 第五步：批量查询所有还款记录，减少数据库查询次数
            all_repayments = list(mongo.refactoring_repayment_order.find({
                'finance_request_number': {'$in': finance_request_numbers}
            }))
            
            logger.info(f"批量查询到 {len(all_repayments)} 条还款记录")
            
            # 创建finance_request_number到还款记录列表的映射，便于快速查找
            fr_to_repayments = {}
            for repayment in all_repayments:
                fr_num = repayment.get('finance_request_number')
                if fr_num:
                    if fr_num not in fr_to_repayments:
                        fr_to_repayments[fr_num] = []
                    fr_to_repayments[fr_num].append(repayment)
            
            # 第六步：获取所有符合条件的银行对账单，只处理与融资订单相关的数据
            cursor = mongo.refactoring_bank_statement.find({
                'invoice.seller_reference': {'$in': seller_references}  # 只处理与融资订单相关的对账单
            }, batch_size=100)  # 每次从数据库获取100条记录
            
            # 构建要处理的银行对账单列表
            confirmed_statements = []
            for statement in cursor:
                confirmed_statements.append(statement)
            
            # 关闭游标
            cursor.close()
            
            # 第七步：按 seller_reference 分组后处理，生成融资概览记录
            logger.info(f"开始处理 {len(confirmed_statements)} 条银行对账单")

            statements_by_seller_ref = {}
            for statement in confirmed_statements:
                seller_ref = statement.get('invoice', {}).get('seller_reference')
                if seller_ref:
                    statements_by_seller_ref.setdefault(seller_ref, []).append(statement)

            from concurrent.futures import ThreadPoolExecutor
            import concurrent.futures

            all_overview_records = []
            num_threads = min(32, concurrent.futures.ThreadPoolExecutor()._max_workers)

            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                future_to_group = {
                    executor.submit(
                        self._process_statement_group, seller_ref, statements, invoice_to_financing, fr_to_repayments
                    ): seller_ref
                    for seller_ref, statements in statements_by_seller_ref.items()
                }

                for future in concurrent.futures.as_completed(future_to_group):
                    result = future.result()
                    if result:
                        all_overview_records.append(result)

            logger.info(f"并行处理完成，生成了 {len(all_overview_records)} 条融资概览记录")
            
            # 第八步：批量更新或插入融资概览记录到数据库
            if all_overview_records:
                from pymongo import UpdateOne
                operations = []
                
                for overview_record in all_overview_records:
                    finance_request_number = overview_record.get('finance_request_number')
                    if finance_request_number:
                        operations.append(UpdateOne(
                            {'finance_request_number': finance_request_number},
                            {'$set': overview_record},
                            upsert=True
                        ))
                
                # 批量执行操作，每1000个操作执行一次
                batch_size = 1000
                for i in range(0, len(operations), batch_size):
                    batch_operations = operations[i:i+batch_size]
                    result = mongo.refactoring_financing_overview.bulk_write(batch_operations)
                    processed_count += result.upserted_count + result.modified_count
                
            # 计算最终统计数
            total_count = mongo.refactoring_financing_overview.count_documents({})
            
            logger.info(f"成功聚合 {processed_count} 条融资概览记录，总计 {total_count} 条")
            
            return {
                'success': True,
                'count': total_count,
                'message': f'成功聚合 {processed_count} 条融资概览记录，总计 {total_count} 条'
            }
        except Exception as e:
            logger.error(f"聚合过程中发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'count': 0,
                'message': f'聚合过程中发生错误: {str(e)}'
            }
    
    def _calculate_totals(
        self, 
        financing: Dict[str, Any], 
        repayments: List[Dict[str, Any]], 
        bank_statements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """计算汇总数据"""
        from decimal import Decimal
        from bson import Decimal128
        
        def to_decimal(value):
            if value is None:
                return Decimal('0')
            if isinstance(value, Decimal):
                return value
            if isinstance(value, (int, float)):
                return Decimal(str(value))
            if hasattr(value, 'to_decimal'):
                return value.to_decimal()
            return Decimal(str(value))
        
        air8_finance_amt = to_decimal(financing.get('actual_financing_amount', 0))
        air8_settled_fr_amt = sum(to_decimal(r.get('cumulative_repaid_principle', 0)) for r in repayments)
        finance_amount_usd = to_decimal(financing.get('financing_amount', 0))
        interest_amount_usd = sum(
            to_decimal(s.get('finance', {}).get('interest_amount', 0)) for s in bank_statements
        )
        outstanding_amount_usd = sum(
            to_decimal(s.get('finance', {}).get('outstanding_amount', 0)) for s in bank_statements
        )
        outstanding_loan_exclude_wip = outstanding_amount_usd
        overdue_interest_od_wip = sum(to_decimal(r.get('adjusted_interest_charges', 0)) for r in repayments)
        overdue_interest_settled_wip = Decimal('0')
        purchase_price_usd = sum(
            to_decimal(s.get('finance', {}).get('purchase_price', 0)) for s in bank_statements
        )
        settled_db_loan = air8_settled_fr_amt
        wip_pending_amount = Decimal('0')
        
        return {
            'air8_finance_amt': Decimal128(str(air8_finance_amt)),
            'air8_settled_fr_amt': Decimal128(str(air8_settled_fr_amt)),
            'finance_amount_usd': Decimal128(str(finance_amount_usd)),
            'interest_amount_usd': Decimal128(str(interest_amount_usd)),
            'outstanding_amount_usd': Decimal128(str(outstanding_amount_usd)),
            'outstanding_loan_exclude_wip': Decimal128(str(outstanding_loan_exclude_wip)),
            'overdue_interest_od_wip': Decimal128(str(overdue_interest_od_wip)),
            'overdue_interest_settled_wip': Decimal128(str(overdue_interest_settled_wip)),
            'purchase_price_usd': Decimal128(str(purchase_price_usd)),
            'settled_db_loan': Decimal128(str(settled_db_loan)),
            'wip_pending_amount': Decimal128(str(wip_pending_amount))
        }
    
    def manual_aggregate(self, finance_request_number: str = None):
        """手动触发聚合，可以指定单个融资申请号"""
        try:
            if finance_request_number:
                return self._aggregate_single_finance(finance_request_number)
            else:
                return self.aggregate_financing_overview()
        except Exception as e:
            return {
                'success': False,
                'count': 0,
                'message': f'手动聚合过程中发生错误: {str(e)}'
            }
    
    def _aggregate_single_finance(self, finance_request_number: str):
        """聚合单个融资申请号的数据"""
        mongo = get_mongo()
        if mongo is None:
            return {
                'success': False,
                'count': 0,
                'message': '数据库未连接'
            }
        
        try:
            # 第一步：获取融资订单
            financing = mongo.refactoring_financing_order.find_one({
                'finance_request_number': finance_request_number
            })
            
            if not financing:
                return {
                    'success': False,
                    'count': 0,
                    'message': f'未找到融资申请号: {finance_request_number}'
                }
            
            invoice_number = financing.get('invoice_number')
            if not invoice_number:
                return {
                    'success': False,
                    'count': 0,
                    'message': f'融资申请号 {finance_request_number} 缺少发票号'
                }
            
            # 第二步：获取该融资申请号的还款记录
            repayments = list(mongo.refactoring_repayment_order.find({
                'finance_request_number': finance_request_number
            }))
            
            # 第三步：筛选与该融资申请号相关的银行对账单（不再限定 finance.status）
            related_statements = []
            confirmed_statements = list(mongo.refactoring_bank_statement.find({}))

            for statement in confirmed_statements:
                db_ref = statement.get('finance', {}).get('db_finance_ref', '')
                seller_ref = statement.get('invoice', {}).get('seller_reference', '')
                if finance_request_number in db_ref or invoice_number in db_ref or invoice_number in seller_ref:
                    related_statements.append(statement)

            # 第四步：格式化全部匹配的银行对账单（按 invoice.creation_time 降序排列，确保 bank_statements[0] 为最新一条），
            # 并取最新一条用于再保理状态/金额快照
            sorted_related_statements = sorted(
                related_statements,
                key=lambda s: s.get('invoice', {}).get('creation_time') or datetime.min,
                reverse=True
            )
            bank_statements = [self._format_bank_statement(s) for s in sorted_related_statements]
            latest_statement = sorted_related_statements[0] if sorted_related_statements else None
            refactor_fields = _build_refactor_snapshot_fields(latest_statement)
            # totals 只用最新一条快照计算，避免同一融资单的历史阶段性对账单被重复加总
            totals_source_statements = [latest_statement] if latest_statement else []
            
            # 第五步：格式化还款记录
            formatted_repayments = []
            for repayment in repayments:
                formatted_repayments.append({
                    'overdue_interest_wip': repayment.get('adjusted_interest_charges'),
                    'repayment_from_buyer_to_air8': repayment.get('cumulative_repayment'),
                    'repayment_status': repayment.get('repayment_status'),
                    'settled_amt_by_air8_to_db': repayment.get('cumulative_repaid_principle'),
                    'settlement_amount': repayment.get('os_balance'),
                    'settlement_date': repayment.get('settlement_date')
                })
            
            # 第六步：构建订单详情
            order_details = {
                'adjusted_due_date': financing.get('due_date'),
                'air8_finance_amt': financing.get('actual_financing_amount'),
                'buyer_reference': financing.get('reference_no'),
                'currency': financing.get('trade_currency'),
                'due_date': financing.get('due_date'),
                'fr_settlement_date': financing.get('actual_funding_date'),
                'interest_rate_pct': financing.get('interest_rate_fee_charge'),
                'invoice_number': financing.get('invoice_number'),
                'issue_date': financing.get('invoice_date'),
                'maturity_date': financing.get('due_date'),
                'original_amount': financing.get('trade_amount'),
                'seller_reference': financing.get('reference_no'),
                'actual_tenor': financing.get('actual_tenor'),
                'collection_period': financing.get('collection_period'),
            }

            # 第七步：计算汇总数据
            totals = self._calculate_totals(financing, repayments, totals_source_statements)

            # 第八步：构建融资概览记录
            overview_record = {
                'finance_request_number': finance_request_number,
                'buyer_erp_id': financing.get('buyer_code'),
                'buyer_name': financing.get('buyer_name'),
                'seller_erp_id': financing.get('supplier_code'),
                'seller_name': financing.get('supplier_name', ''),
                'summary_status': financing.get('status'),
                'loan_submission_batch': financing.get('batch_number', 0),
                'seq': 0,
                'order_details': order_details,
                'bank_statements': bank_statements,
                'repayments': formatted_repayments,
                'totals': totals,
                'updated_at': datetime.now(),
                # 补全用户要求的其他字段
                'settled_in_air8': financing.get('settled_in_air8', ''),
                'db_loan_settle_date': financing.get('db_loan_settle_date', ''),
                'invoice_settlement_date_db_updated': '',
                'overdue_interest_settled_wip': '',
                'overdue_interest_od_wip': '',
                'air8_settled_fr_amt': totals.get('air8_settled_fr_amt'),
                'settled_db_loan': totals.get('settled_db_loan'),
                'outstanding_loan_exclude_wip': totals.get('outstanding_loan_exclude_wip'),
                'wip_pending_amount': totals.get('wip_pending_amount'),
                'financing_amount_trade_currency': financing.get('financing_amount_trade_currency'),
                'interest_amount_trade_currency': financing.get('financing_interest'),
                'interest_rate_pct': financing.get('interest_rate_fee_charge'),
                'funder': financing.get('insurer'),
            }
            overview_record.update(refactor_fields)
            
            # 第九步：更新或插入融资概览记录
            existing = mongo.refactoring_financing_overview.find_one({
                'finance_request_number': finance_request_number
            })
            
            if existing:
                # 更新现有记录
                mongo.refactoring_financing_overview.replace_one(
                    {'_id': existing['_id']},
                    overview_record
                )
            else:
                # 插入新记录
                mongo.refactoring_financing_overview.insert_one(overview_record)
            
            return {
                'success': True,
                'count': 1,
                'message': f'成功聚合融资申请号: {finance_request_number}'
            }
        except Exception as e:
            return {
                'success': False,
                'count': 0,
                'message': f'聚合单个融资申请号 {finance_request_number} 时发生错误: {str(e)}'
            }
