"""检查 / 创建 refactoring_bank_statement.invoice.seller_reference 唯一索引。

字段对应：Excel 列 "Invoice Details - Seller Reference" -> 文档 invoice.seller_reference

用法：
  # 1) 只检查：打印库名、现有索引、重复的 seller_reference（不建索引）
  python scripts/manage_seller_ref_index.py

  # 2) 确认无重复后，真正创建唯一索引
  python scripts/manage_seller_ref_index.py --create

说明：
- 连接串取环境变量 MONGODB_URI，缺省用 dev 默认（localhost / 库 refactoring）。
- 唯一索引一旦遇到重复值会抛 E11000；本脚本会先列出重复，避免盲目创建失败。
"""
import os
import sys
from collections import OrderedDict

from pymongo import MongoClient, ASCENDING

DEFAULT_URI = 'mongodb://air8:Air8%40123@localhost:27017/refactoring'
FIELD = 'invoice.seller_reference'
INDEX_NAME = 'uniq_invoice_seller_reference'


def main(create: bool):
    uri = os.environ.get('MONGODB_URI') or DEFAULT_URI
    client = MongoClient(uri)
    db = client.get_database()  # 取 URI 末尾的库名（refactoring）
    coll = db.refactoring_bank_statement

    print(f'连接库: {db.name}')
    print(f'集合: refactoring_bank_statement，文档总数: {coll.count_documents({})}')

    print('\n现有索引:')
    for name, spec in coll.index_information().items():
        print(f'  - {name}: key={spec.get("key")}, unique={spec.get("unique", False)}')

    # 查重：按 invoice.seller_reference 分组，统计 count>1
    pipeline = [
        {'$group': {'_id': f'${FIELD}', 'count': {'$sum': 1}}},
        {'$match': {'count': {'$gt': 1}}},
        {'$sort': {'count': -1}},
    ]
    dups = list(coll.aggregate(pipeline))

    # 统计字段缺失数量（缺失字段在唯一索引里会被当作 null，多条 null 也算重复）
    missing = coll.count_documents({FIELD: {'$exists': False}})

    print(f'\n重复的 {FIELD} 值: {len(dups)} 组')
    for d in dups[:20]:
        val = d['_id']
        shown = repr(val) if val is not None else 'null/缺失'
        print(f'  - {shown}: {d["count"]} 条')
    if len(dups) > 20:
        print(f'  ... 其余 {len(dups) - 20} 组略')
    print(f'字段缺失(不存在 {FIELD})的文档数: {missing}')

    can_create = (len(dups) == 0)
    if not create:
        print('\n[只检查] 未创建索引。')
        if can_create:
            print('✅ 无重复，可安全创建。加 --create 执行。')
        else:
            print('❌ 存在重复值，直接建唯一索引会报 E11000。请先清理重复/空值，'
                  '或改用 partial/sparse 索引（需求确认后我再给）。')
        return

    if not can_create:
        print('\n❌ 存在重复值，已中止创建（避免 E11000 报错）。先处理重复再来。')
        sys.exit(1)

    print(f'\n正在创建唯一索引 {INDEX_NAME} on {FIELD} ...')
    coll.create_index([(FIELD, ASCENDING)], unique=True, name=INDEX_NAME)
    print('✅ 创建成功。当前索引:')
    for name, spec in coll.index_information().items():
        print(f'  - {name}: key={spec.get("key")}, unique={spec.get("unique", False)}')


if __name__ == '__main__':
    main(create='--create' in sys.argv[1:])
