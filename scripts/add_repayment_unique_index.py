"""
一次性迁移脚本：为 refactoring_repayment_order 集合的 finance_request_number 字段添加唯一索引。

使用方法：
    python scripts/add_repayment_unique_index.py

注意：
    - 若存在重复的 finance_request_number，脚本会打印报告并退出，需手动处理后重跑
    - 若无重复数据，直接创建唯一索引
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app
from backend.app import extensions
import pymongo

app = create_app()

with app.app_context():
    extensions.init_extensions(app)
    mongo_db = extensions.mongo

    print("=" * 60)
    print("检查 refactoring_repayment_order 重复数据")
    print("=" * 60)

    # 检测重复的 finance_request_number
    pipeline = [
        {"$group": {
            "_id": "$finance_request_number",
            "count": {"$sum": 1},
            "ids": {"$push": "$_id"}
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}}
    ]
    duplicates = list(mongo_db.refactoring_repayment_order.aggregate(pipeline))

    if duplicates:
        print(f"\n⚠️  发现 {len(duplicates)} 个重复的 finance_request_number：\n")
        for dup in duplicates:
            print(f"  finance_request_number={dup['_id']}  出现 {dup['count']} 次  IDs: {dup['ids']}")
        print("\n请手动处理以上重复数据后，重新运行本脚本。")
        print("建议：保留最新记录，删除旧记录（按 updated_at 或 created_at 排序）。")
        sys.exit(1)

    print("✓ 无重复数据")

    # 创建唯一索引
    print("\n添加唯一索引 unique_finance_request_number ...")
    try:
        mongo_db.refactoring_repayment_order.create_index(
            [('finance_request_number', pymongo.ASCENDING)],
            unique=True,
            name='unique_finance_request_number'
        )
        print("✓ 唯一索引创建成功")
    except pymongo.errors.OperationFailure as e:
        if 'already exists' in str(e) or 'IndexOptionsConflict' in str(e):
            print("✓ 唯一索引已存在，跳过")
        else:
            print(f"✗ 创建索引失败: {e}")
            sys.exit(1)

    # 验证
    indexes = list(mongo_db.refactoring_repayment_order.list_indexes())
    print("\n当前索引列表：")
    for idx in indexes:
        print(f"  {idx['name']}: {idx['key']}  unique={idx.get('unique', False)}")

    print("\n" + "=" * 60)
    print("迁移完成")
    print("=" * 60)
