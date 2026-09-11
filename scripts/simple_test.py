# 简单测试应用程序
from flask import Flask, request

app = Flask(__name__)

# 简单的API导入路由
@app.route('/import/import_from_api', methods=['POST'])
def import_from_api():
    import_type = request.form.get('import_type')
    return f'API导入测试成功！导入类型：{import_type}', 200

# 简单的导入页面路由
@app.route('/import/', methods=['GET'])
def import_index():
    return '''
    <html>
        <body>
            <h1>导入测试</h1>
            <form method="POST" action="/import/import_from_api">
                <select name="import_type">
                    <option value="repayment">还款订单</option>
                </select>
                <button type="submit">从API导入</button>
            </form>
        </body>
    </html>
    ''', 200

if __name__ == '__main__':
    app.run(debug=True, port=5001)