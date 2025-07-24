import os
from http.client import responses
from flask import Flask, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
from flask import send_from_directory
import secrets

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:Yhr20050420.@localhost/game_db'
app.config['SECRET_KEY'] = 'your-secret-key'  # 用于会话签名
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 防止CSRF攻击
app.config['SESSION_COOKIE_SECURE'] = False  # 开发环境使用HTTP，生产环境应设为True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 配置CORS允许跨域请求
CORS(app, supports_credentials=True, origins='http://localhost:5000')  # 前端域名

db = SQLAlchemy(app)


# 数据库模型
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)


class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    moves = db.Column(db.Integer, nullable=False)
    time = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# 注册接口
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    if len(username) < 1 or len(password) < 1:
        return jsonify({"error": "请填写您的用户名或密码"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "用户名已存在"}), 400

    try:
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"message": "注册成功，请登录"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "注册失败，请重试"}), 500



@app.route('/api/login', methods=['POST'])
def login():
    if not request.is_json:
        return jsonify({"error": "请求必须是JSON格式"}), 415

    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    try:
        user = User.query.filter_by(username=username).first()

        if not user or user.password != password:
            return jsonify({"error": "用户名或密码错误"}), 401

        # 防止会话固定攻击
        session.permanent = True
        # 保存用户 ID 到临时变量
        user_id = user.id
        # 销毁当前会话
        session.clear()
        # 重新启动会话
        session['user_id'] = user_id

        return jsonify({
            "message": "登录成功",
            "user": {
                "id": user.id,
                "username": user.username
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()  # 打印详细的错误堆栈信息
        return jsonify({"error": f"服务器内部错误: {str(e)}"}), 500


@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(os.path.join(app.root_path, 'templates'), path)


@app.route('/')
def index():
    return redirect(url_for('serve_static', path='index.html'))

# 检查登录状态
@app.route('/api/check_login', methods=['GET'])
def check_login():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            return jsonify({
                "message": "已登录",
                "user": {
                    "id": user.id,
                    "username": user.username
                }
            })
    return jsonify({"message": "未登录"}), 401


# 保存游戏记录
@app.route('/api/game', methods=['POST'])
def save_game():
    if 'user_id' not in session:
        return jsonify({"error": "未登录"}), 401

    data = request.json
    score = data.get('score')
    moves = data.get('moves')
    time = data.get('time')

    if not isinstance(score, int) or not isinstance(moves, int) or not time:
        return jsonify({"error": "无效的游戏数据"}), 400

    try:
        new_history = History(
            user_id=session['user_id'],
            score=score,
            moves=moves,
            time=time
        )
        db.session.add(new_history)
        db.session.commit()
        return jsonify({"message": "记录已保存"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "保存失败，请重试"}), 500


# 获取排行榜
@app.route('/api/ranking', methods=['GET'])
def ranking():
    try:
        records = History.query.join(User).add_columns(
            User.username, History.score, History.moves, History.time, History.created_at
        ).order_by(History.score.desc()).limit(10).all()

        result = [{
            "username": r.username,
            "score": r.score,
            "moves": r.moves,
            "time": r.time,
            "created_at": r.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for r in records]

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": "获取排行榜失败"}), 500


# 退出登录
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "已退出登录"})


# 获取用户游戏历史记录
@app.route('/api/history', methods=['GET'])
def get_history():
    if 'user_id' not in session:
        return jsonify({"error": "未登录"}), 401

    try:
        records = History.query.filter_by(user_id=session['user_id']).order_by(History.created_at.desc()).all()
        result = [{
            "created_at": record.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            "score": record.score,
            "moves": record.moves,
            "time": record.time
        } for record in records]

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": "获取历史记录失败"}), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='127.0.0.1', port=5000)

