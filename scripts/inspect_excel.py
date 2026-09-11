import pandas as pd

# 读取Excel文件
excel_file = 'overview_batch_number.xlsx'
df = pd.read_excel(excel_file)

# 打印文件基本信息
print("Excel文件基本信息：")
print(f"行数：{len(df)}")
print(f"列数：{len(df.columns)}")
print(f"列名：{list(df.columns)}")

# 打印前5行数据
print("\n前5行数据：")
print(df.head())

# 检查数据类型
print("\n数据类型：")
print(df.dtypes)

# 检查是否有缺失值
print("\n缺失值情况：")
print(df.isnull().sum())
