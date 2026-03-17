# 通用离开房间/解散房间逻辑
def leave_room_db(current_user, room_id):
    room = Room.query.get(room_id)
    if not room:
        return False, '房间不存在！'
    membership = RoomMember.query.filter_by(user_id=current_user.id, room_id=room_id).first()
    if not membership:
        return False, '您不是这个房间的成员！'
    try:
        # 发送系统消息
        system_message = f"用户 {current_user.nickname} 离开了房间"
        if room.creator_id == current_user.id and room.is_active:
            # 房主解散房间
            system_chat = RoomChat(
                room_id=room_id,
                user_id=0,
                message_type='system',
                content="房主解散了房间"
            )
            db.session.add(system_chat)
            room.is_active = False
            db.session.commit()
            tips_update_active_rooms()
            msg = '房间已删除！'
            socketio.emit('room_deleted', {'room_id': room.id}, to='0')
        else:
            db.session.delete(membership)
            system_chat = RoomChat(
                room_id=room_id,
                user_id=0,
                message_type='system',
                content=system_message
            )
            db.session.add(system_chat)
            db.session.commit()
            msg = '成功退出房间！'
            socketio.emit('room_updated', room.to_dict(), to='0')
        # SocketIO广播
        message_data = system_chat.to_dict()
        socketio.emit('message', message_data, to=str(room_id))
        ()
        return True, msg
    except Exception as e:
        db.session.rollback()
        print(f"离开房间错误: {str(e)}")
        return False, '退出房间失败，请稍后重试！'
# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import time
from functools import wraps
import os
from flask import send_from_directory
from models import db, User, Room, RoomMember, RoomChat, MatchUser, init_socketio
from config import Config
from datetime import datetime, timedelta, timezone
from flask_socketio import SocketIO, join_room, leave_room, emit
import eventlet

online_user_list = []
online_user_sid_list = []
online_start_time_list = []

# 使用eventlet，提升SocketIO性能
eventlet.monkey_patch()

app = Flask(__name__)
app.config.from_object(Config)

# 配置SocketIO
app.config['SECRET_KEY'] = app.config['SECRET_KEY']
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='eventlet',
                   ping_timeout=60,
                   ping_interval=25)

# 初始化socketio到models
init_socketio(socketio)

east8 = timezone(timedelta(hours=8))

os.makedirs('instance', exist_ok=True)

db.init_app(app)


# 更新CORS配置
CORS(app, 
    origins=app.config['CORS_ORIGINS'],
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization", "Access-Control-Allow-Credentials"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# 强制 HTTP 跳转到 HTTPS
from flask import redirect
@app.before_request
def before_request_https_redirect():
    # 只在生产环境生效，开发环境可注释掉
    if request.headers.get('X-Forwarded-Proto', 'https') == 'http':
       url = request.url.replace('http://', 'https://', 1)
       return redirect(url, code=301)



def init_system_user():
    """初始化系统用户"""
    system_user = User.query.get(0)
    if not system_user:
        system_user = User(
            id=0,
            username='系统',
            password_hash='system_user_no_password',  # 随机字符串，不会被用于登录
            profile='系统消息'
        )
        db.session.add(system_user)
        db.session.commit()
        print("系统用户创建成功")
    return system_user


with app.app_context():
    db.create_all()
    init_system_user()  # 添加这行
    # 启用 SQLite 外键约束
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from sqlite3 import Connection as SQLite3Connection

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if isinstance(dbapi_connection, SQLite3Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

# app.py 中的 token_required 装饰器部分

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'message': 'Token格式错误！'}), 401
        
        if not token:
            return jsonify({'message': '缺少访问令牌！'}), 401
        
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            # 修改这里：使用 User.query.get() 而不是 db.session.get()
            current_user = User.query.get(data['user_id'])
            
            if not current_user:
                return jsonify({'message': '用户不存在！'}), 401
            
            # 简化方案：只对某些关键API更新活跃时间，避免过于频繁
            # 或者完全移除时间检查，每次请求都更新（性能可能稍差但更准确）
            path = request.path
            # 只在重要的用户操作时更新，避免过于频繁的数据库写入
            important_paths = ['/api/rooms', '/api/user/profile', '/api/user/rooms']
            
            if any(path.startswith(important_path) for important_path in important_paths):
                current_user.last_login_at = datetime.now(east8)
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    print(f"更新最后活跃时间失败: {str(e)}")
                
        except jwt.ExpiredSignatureError:
            return jsonify({'message': '令牌已过期！'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': '无效的令牌！'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated

# 添加前端路由
from flask import send_file
from werkzeug.utils import secure_filename

# 上传头像API
@app.route('/api/upload_avatar', methods=['POST'])
@token_required
def upload_avatar(current_user):
    if 'avatar' not in request.files:
        return jsonify({'message': '未检测到头像文件'}), 400
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'message': '未选择文件'}), 400
    filename = f"{current_user.id}.png"
    save_dir = os.path.join('instance', 'pic')
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)
    file.save(save_path)
    # image自增
    current_user.image = (current_user.image or 0) + 1
    db.session.commit()
    return jsonify({'message': '上传成功', 'image': current_user.image}), 200

# 获取头像API，支持image参数用于缓存控制
@app.route('/api/avatar/<int:user_id>/<int:image>', methods=['GET'])
def get_avatar(user_id, image):
    pic_path = os.path.join('instance', 'pic', f'{user_id}.png')
    if os.path.exists(pic_path):
        return send_file(pic_path, mimetype='image/png')
    # 若无则返回根目录default.png
    default_path = os.path.join(app.root_path,'default.png')
    print(os.path.exists(default_path))
    if os.path.exists(default_path):
        return send_file(default_path, mimetype='image/png')
    return '', 404

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/index')
def serve_index2():
    return send_from_directory('.', 'index.html')

@app.route('/login')
def serve_login():
    return send_from_directory('.', 'login.html')

@app.route('/room')
def serve_room():
    return send_from_directory('.', 'room.html')

@app.route('/info')
def serve_info():
    return send_from_directory('.', 'info.html')

@app.route('/user')
def serve_user():
    return send_from_directory('.', 'user.html')

@app.route('/skin')
def serve_skin():
    return send_from_directory('.', 'skin.html')

@app.route('/admin')
def serve_admin():
    return send_from_directory('.', 'admin.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'OK', 'message': '服务运行正常'}), 200


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': '用户名和密码是必需的！'}), 400
    
    user = User.query.filter_by(username=data['username']).first()
    
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify({'message': '用户名或密码错误！'}), 401
    
    # 更新上次登录时间
    try:
        user.last_login_at = datetime.now(east8)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"更新上次登录时间错误: {str(e)}")
    
    token = user.generate_token()
    
    return jsonify({
        'message': '登录成功！',
        'token': token,
        'user': user.to_dict()
    }), 200

def token_required_for_socketio(f):
    @wraps(f)
    def decorated(data=None):
        token = None
        
        # 从请求参数或消息数据中获取token
        if data and 'token' in data:
            token = data.get('token')
        elif 'token' in request.args:
            token = request.args.get('token')
        elif 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                emit('error', {'message': 'Token格式错误！'})
                return None
        
        if not token:
            emit('error', {'message': '缺少访问令牌！'})
            return None
        
        try:
            esdata = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = User.query.get(esdata['user_id'])
            
            if not current_user:
                emit('error', {'message': '用户不存在！'})
                return None
            
            # 调用原始函数，传递用户和data
            return f(current_user, data)
        except jwt.ExpiredSignatureError:
            emit('error', {'message': '令牌已过期！'})
            return None
        except jwt.InvalidTokenError:
            emit('error', {'message': '无效的令牌！'})
            return None
    
    return decorated

@app.route('/api/user', methods=['GET'])
@token_required
def get_current_user(current_user):
    return jsonify({'user': current_user.to_dict()}), 200

@app.route('/api/rooms', methods=['POST'])
@token_required
def create_room(current_user):
    data = request.get_json()
    
    if not data or not data.get('name'):
        return jsonify({'message': '房间名称是必需的！'}), 400
    
    if len(data['name']) < 2:
        return jsonify({'message': '房间名称至少需要2个字符！'}), 400
    
    try:
        # 退出所有其他房间（批量优化）
        other_memberships = RoomMember.query.filter_by(user_id=current_user.id).all()
        dissolve_room_ids = set()
        leave_membership_ids = []
        for membership in other_memberships:
            if membership.room.creator_id == current_user.id:
                dissolve_room_ids.add(membership.room.id)
            else:
                leave_membership_ids.append(membership.id)
        if dissolve_room_ids:
            Room.query.filter(Room.id.in_(dissolve_room_ids)).update({Room.is_active: False}, synchronize_session=False)
            RoomMember.query.filter(RoomMember.room_id.in_(dissolve_room_ids)).delete(synchronize_session=False)
        if leave_membership_ids:
            RoomMember.query.filter(RoomMember.id.in_(leave_membership_ids)).delete(synchronize_session=False)
        db.session.commit()

        # 创建新房间
        new_room = Room(
            name=data['name'],
            server_address=data.get('server_address', ''),
            description=data.get('description', ''),
            max_players=data.get('max_players', 4),
            creator_id=current_user.id,
            room_type=data.get('room_type', 'public'),
            password=data.get('password', None)  # 存储密码
        )
        db.session.add(new_room)
        current_user.created_room_count += 1
        db.session.flush()
        
        membership = RoomMember(
            user_id=current_user.id, 
            room_id=new_room.id,
            is_ready=True
        )
        db.session.add(membership)
        
        db.session.commit()
        tips_update_active_rooms()
        tips_update_total_rooms()
        room_with_details = Room.query.get(new_room.id)
        
        # 增量推送新房间
        socketio.emit('room_created', room_with_details.to_dict(), to='0')
        
        return jsonify({
            'message': '房间创建成功！',
            'room': room_with_details.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"创建房间错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': '创建房间失败，请稍后重试！'}), 500


@app.route('/api/rooms', methods=['GET'])
@token_required
def get_rooms(current_user):
    rooms = Room.query.filter_by(is_active=True).order_by(Room.created_at.desc()).all()
    #为每个room添加房主在线状态
    modify_rooms = []
    for room in rooms:
        modify_rooms.append({
            'id': room.id,
            'name': room.name,
            'server_address': room.server_address,
            'description': room.description,
            'creator': room.creator.username,
            'creator_id': room.creator_id,
            'creator_nickname': room.creator.nickname,
            'created_at': room.created_at.isoformat(),
            'member_count': len(room.members),
            'max_players': room.max_players,
            'room_type': room.room_type,
            'game_status': room.game_status,
            'is_owner_online': room.creator_id in online_user_list
        })
    return jsonify({
        'rooms': modify_rooms
    }), 200

@app.route('/api/rooms/<int:room_id>/join', methods=['POST'])
@token_required
def join_room_http(current_user, room_id):
    room = Room.query.get(room_id)
    
    if not room or not room.is_active:
        return jsonify({'message': '房间不存在！'}), 404
    
    if len(room.members) >= room.max_players:
        return jsonify({'message': '房间已满，无法加入！'}), 400
    
    data = request.get_json()

    password = data.get('password', '')

    # 检查密码（保持不变）
    if room.room_type == 'private':
        if not room.password:
            return jsonify({'message': '房间密码未设置！'}), 400
        if not password or room.password != password:
            return jsonify({'message': '密码错误！'}), 401
    
    # 检查用户是否已经在这个房间里
    existing_membership = RoomMember.query.filter_by(
        user_id=current_user.id, 
        room_id=room_id
    ).first()
    
    if existing_membership:
        return jsonify({
            'message': '您已经加入了这个房间！',
            'room': room.to_dict()
        }), 200
    
    try:
        # 退出所有其他房间（批量优化）
        other_memberships = RoomMember.query.filter_by(user_id=current_user.id).all()
        dissolve_room_ids = set()
        leave_membership_ids = []
        for membership in other_memberships:
            if membership.room.creator_id == current_user.id:
                dissolve_room_ids.add(membership.room.id)
            else:
                leave_membership_ids.append(membership.id)
        if dissolve_room_ids:
            Room.query.filter(Room.id.in_(dissolve_room_ids)).update({Room.is_active: False}, synchronize_session=False)
            RoomMember.query.filter(RoomMember.room_id.in_(dissolve_room_ids)).delete(synchronize_session=False)
        if leave_membership_ids:
            RoomMember.query.filter(RoomMember.id.in_(leave_membership_ids)).delete(synchronize_session=False)
        db.session.commit()

        # 加入新房间
        membership = RoomMember(
            user_id=current_user.id, 
            room_id=room_id,
            is_ready=False
        )
        db.session.add(membership)
        db.session.commit()
        
        # 发送系统消息（通过SocketIO）
        system_message = f"用户 {current_user.nickname} 加入了房间"
        system_chat = RoomChat(
            room_id=room_id,
            user_id=0,
            message_type='system',
            content=system_message
        )
        db.session.add(system_chat)
        current_user.joined_room_count += 1
        db.session.commit()
        

        # 通过SocketIO广播系统消息
        message_data = system_chat.to_dict()
            # 通知房间其他成员
        socketio.emit('message', message_data, to=str(room_id))
        socketio.emit('room_updated', room.to_dict(), to='0')

        room = Room.query.get(room_id)
        
        # 通知房间列表更新（成员数量变化）
        ()
        
        return jsonify({
            'message': '成功加入房间！',
            'room': room.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"加入房间错误: {str(e)}")
        return jsonify({'message': '加入房间失败，请稍后重试！'}), 500

    

@app.route('/api/rooms/<int:room_id>/toggle-ready', methods=['POST'])
@token_required
def toggle_ready_status(current_user, room_id):
    room = Room.query.get(room_id)
    
    if not room or not room.is_active:
        return jsonify({'message': '房间不存在！'}), 404
    
    membership = RoomMember.query.filter_by(
        user_id=current_user.id, 
        room_id=room_id
    ).first()
    
    if not membership:
        return jsonify({'message': '您不是这个房间的成员！'}), 403
    
    membership.is_ready = not membership.is_ready
    
    try:
        system_message = f"用户 {current_user.nickname} {'准备好了' if membership.is_ready else '取消了准备'}"
        system_chat = {
            'room_id': room_id,
            'user_id': current_user.id,
            'message_type': 'system',
            'content': system_message
        }
        db.session.commit()
        # 通过SocketIO广播系统消息
        socketio.emit('toggle-ready', system_chat, to=str(room_id))

        
        return jsonify({
            'message': f'已{"准备" if membership.is_ready else "取消准备"}！',
            'is_ready': membership.is_ready
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"切换准备状态错误: {str(e)}")
        return jsonify({'message': '操作失败，请稍后重试！'}), 500

@app.route('/api/rooms/<int:room_id>/kick/<int:user_id>', methods=['POST'])
@token_required
def kick_member(current_user, room_id, user_id):
    room = Room.query.get(room_id)
    
    if not room:
        return jsonify({'message': '房间不存在！'}), 404
    
    if room.creator_id != current_user.id:
        return jsonify({'message': '只有房间创建者可以踢出成员！'}), 403
    
    if user_id == current_user.id:
        return jsonify({'message': '不能踢出自己！'}), 400
    
    membership = RoomMember.query.filter_by(
        user_id=user_id, 
        room_id=room_id
    ).first()
    
    if not membership:
        return jsonify({'message': '该用户不在房间中！'}), 404
    
    try:

        system_message = f"用户 {membership.user.nickname} 被房主踢出房间"
        system_chat = RoomChat(
            room_id=room_id,
            user_id=0,
            message_type='system',
            content=system_message
        )
        db.session.delete(membership)
        db.session.add(system_chat)
        db.session.commit()
        # 通过SocketIO广播系统消息
        message_data = system_chat.to_dict()
        socketio.emit('message', message_data, to=str(room_id))

        return jsonify({
            'message': '成员已踢出！'
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"踢出成员错误: {str(e)}")
        return jsonify({'message': '踢出成员失败，请稍后重试！'}), 500
@app.route('/api/user/leave-all-rooms', methods=['POST'])
@token_required
def leave_all_rooms(current_user):
    try:
        memberships = RoomMember.query.filter_by(user_id=current_user.id).all()
        # 记录需要解散的房间id和需要离开的房间id
        dissolve_room_ids = set()
        leave_membership_ids = []
        for membership in memberships:
            if membership.room.creator_id == current_user.id:
                dissolve_room_ids.add(membership.room.id)
            else:
                leave_membership_ids.append(membership.id)

        # 批量解散房间（只更新is_active）
        if dissolve_room_ids:
            Room.query.filter(Room.id.in_(dissolve_room_ids)).update({Room.is_active: False}, synchronize_session=False)
            # 批量删除房间成员
            RoomMember.query.filter(RoomMember.room_id.in_(dissolve_room_ids)).delete(synchronize_session=False)

        # 批量删除普通成员关系
        if leave_membership_ids:
            RoomMember.query.filter(RoomMember.id.in_(leave_membership_ids)).delete(synchronize_session=False)

        db.session.commit()
        return jsonify({'message': '已退出所有房间！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"退出所有房间错误: {str(e)}")
        return jsonify({'message': '退出房间失败，请稍后重试！'}), 500

@app.route('/api/user/rooms', methods=['GET'])
@token_required
def get_user_rooms(current_user):
    memberships = RoomMember.query.filter_by(user_id=current_user.id).all()
    rooms = [membership.room for membership in memberships if membership.room.is_active]
    
    return jsonify({
        'rooms': [room.to_dict() for room in rooms]
    }), 200

@app.route('/api/rooms/<int:room_id>/leave', methods=['POST'])
@token_required
def leave_room_http(current_user, room_id):
    success, msg = leave_room_db(current_user, room_id)
    if success:
        return jsonify({'message': msg}), 200
    else:
        # leave_room_db 已经处理了不存在/非成员等情况，msg为错误提示
        return jsonify({'message': msg}), 400

@app.route('/api/rooms/<int:room_id>/description', methods=['PUT'])
@token_required
def update_description(current_user, room_id):
    room = Room.query.get(room_id)
    
    if not room:
        return jsonify({'message': '房间不存在！'}), 404
    
    if room.creator_id != current_user.id:
        return jsonify({'message': '只有房间创建者可以更新房间描述！'}), 403
    
    data = request.get_json()
    
    # 保存旧内容用于系统消息
    old_description = room.description
    new_description = data['description']
    # 检查内容是否真的发生了变化
    if old_description == new_description:
        return jsonify({'message': '房间描述未发生变化！'}), 400

    room.description = new_description
    # 增量推送房间更新
    socketio.emit('room_updated', room.to_dict(), to='0')
    try:
        system_message = new_description
        system_chat = {
            'room_id': room_id,
            'user_id': current_user.id,
            'message_type': 'system',
            'content': system_message
        }
        db.session.commit()
        # 通过SocketIO广播系统消息
        socketio.emit('description', system_chat, to=str(room_id))
        
        # 发送系统消息通知房间成员
        system_message = f"房主更新了房间描述：{old_description} → {new_description}"   
        _send_system_message(room_id, system_message)
        
        return jsonify({
            'message': '房间描述更新成功！',
            'room': room.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"更新房间描述错误: {str(e)}")
        return jsonify({'message': '更新房间描述失败，请稍后重试！'}), 500

#获取创建房间、加入房间数量、在线时长数量排行前5名用户nicknames、头像和对应数据
@app.route('/api/rankings', methods=['GET'])
@token_required
def get_rankings(current_user):
    print("获取排行榜请求")
    try:
        top_creators = User.query.order_by(User.created_room_count.desc()).limit(5).all()
        top_joiners = User.query.order_by(User.joined_room_count.desc()).limit(5).all()
        top_online_time = User.query.order_by(User.total_online_time.desc()).limit(5).all()

        # 统计每个用户的房间聊天数
        from collections import Counter
        chat_counts = Counter()
        for chat in RoomChat.query.all():
            chat_counts[chat.user_id] += 1

        # 获取用户信息并排序，直接用user.to_dict()
        user_chat_stats = [user.to_dict() for user_id, count in chat_counts.items() if (user_id != 0 and (user := User.query.get(user_id)))]
        top_chat_users = sorted(user_chat_stats, key=lambda x: x['chat_count'], reverse=True)[:5]

        return jsonify({
            'top_creators': [user.to_dict() for user in top_creators],
            'top_joiners': [user.to_dict() for user in top_joiners],
            'top_online_time': [user.to_dict() for user in top_online_time],
            'top_chat_users': top_chat_users,
        }), 200
    except Exception as e:
        print(f"获取排行榜错误: {str(e)}")
        return jsonify({'message': '获取排行榜失败！'}), 500

@app.route('/api/rooms/<int:room_id>/address', methods=['PUT'])
@token_required
def update_server_address(current_user, room_id):
    room = Room.query.get(room_id)
    
    if not room:
        return jsonify({'message': '房间不存在！'}), 404
    
    if room.creator_id != current_user.id:
        return jsonify({'message': '只有房间创建者可以更新房间内容！'}), 403
    
    data = request.get_json()
    
    # 保存旧内容用于系统消息
    old_address = room.server_address
    new_address = data['address']
    # 检查内容是否真的发生了变化
    if old_address == new_address:
        return jsonify({'message': '房间内容未发生变化！'}), 400

    room.server_address = new_address
    # 增量推送房间更新
    socketio.emit('room_updated', room.to_dict(), to='0')
    try:
        system_message = new_address
        system_chat = {
            'room_id': room_id,
            'user_id': current_user.id,
            'message_type': 'system',
            'content': system_message
        }
        db.session.commit()
        # 通过SocketIO广播系统消息
        socketio.emit('address', system_chat, to=str(room_id))
        
        # 发送系统消息通知房间成员
        system_message = f"房主更新了房间内容：{old_address} → {new_address}"   
        _send_system_message(room_id, system_message)
        
        return jsonify({
            'message': '房间内容更新成功！',
            'room': room.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"更新房间内容错误: {str(e)}")
        return jsonify({'message': '更新房间内容失败，请稍后重试！'}), 500


@app.route('/api/rooms/<int:room_id>/status', methods=['PUT'])
@token_required
def update_game_status(current_user, room_id):
    room = Room.query.get(room_id)
    
    if not room:
        return jsonify({'message': '房间不存在！'}), 404
    
    if room.creator_id != current_user.id:
        return jsonify({'message': '只有房间创建者可以更新游戏状态！'}), 403
    
    data = request.get_json()
    
    if not data or not data.get('game_status'):
        return jsonify({'message': '游戏状态是必需的！'}), 400
    
    allowed_statuses = ['waiting', 'playing', 'finished']
    if data['game_status'] not in allowed_statuses:
        return jsonify({'message': '无效的游戏状态！'}), 400
    
    room.game_status = data['game_status']
    try:
        system_message = room.game_status
        system_chat = {
            'room_id': room_id,
            'user_id': current_user.id,
            'message_type': 'system',
            'content': system_message
        }
        db.session.commit()
        # 通过SocketIO广播系统消息
        socketio.emit('update-game-status', system_chat, to=str(room_id))
        # 增量推送房间更新
        socketio.emit('room_updated', room.to_dict(), to='0')
        
        return jsonify({
            'message': '游戏状态更新成功！',
            'room': room.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"更新游戏状态错误: {str(e)}")
        return jsonify({'message': '更新游戏状态失败，请稍后重试！'}), 500

@app.route('/api/rooms/<int:room_id>/details', methods=['GET'])
@token_required
def get_room_details(current_user, room_id):
    room = Room.query.get(room_id)
    
    if not room or not room.is_active:
        return jsonify({'message': '房间不存在！'}), 404
    
    membership = RoomMember.query.filter_by(
        user_id=current_user.id, 
        room_id=room_id
    ).first()
    
    if not membership:
        return jsonify({'message': '您不是这个房间的成员！'}), 403
    
    room_dict = room.to_dict()
    
    for i, member in enumerate(room.members):
        member_membership = RoomMember.query.filter_by(
            user_id=member.user.id, 
            room_id=room_id
        ).first()
        room_dict['members'][i]['is_ready'] = member_membership.is_ready if member_membership else False
        room_dict['members'][i]['is_online'] = member.user.id in online_user_list
    
    return jsonify({
        'room': room_dict
    }), 200

@app.route('/api/rooms/<int:room_id>', methods=['DELETE'])
@token_required
def delete_room(current_user, room_id):
    room = Room.query.get(room_id)
    
    if not room:
        return jsonify({'message': '房间不存在！'}), 404
    
    if room.creator_id != current_user.id:
        return jsonify({'message': '只有房间创建者可以删除房间！'}), 403
    
    try:
        room.is_active = False
        db.session.commit()
        
        # 增量推送房间删除
        socketio.emit('room_deleted', {'room_id': room.id}, to='0')
        tips_update_active_rooms()
        return jsonify({'message': '房间删除成功！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"删除房间错误: {str(e)}")
        return jsonify({'message': '删除房间失败，请稍后重试！'}), 500

# app.py 中的 admin_required 装饰器部分

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'message': 'Token格式错误！'}), 401
        
        if not token:
            return jsonify({'message': '缺少访问令牌！'}), 401
        
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            # 修改这里：使用 User.query.get() 而不是 db.session.get()
            current_user = User.query.get(data['user_id'])
            
            if not current_user:
                return jsonify({'message': '用户不存在！'}), 401
                
            # 简单的管理员检查 - 在实际应用中应该使用更安全的角色系统
            # 这里假设用户名为 'admin' 的用户是管理员
            if current_user.username != 'admin':
                return jsonify({'message': '需要管理员权限！'}), 403
                
        except jwt.ExpiredSignatureError:
            return jsonify({'message': '令牌已过期！'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': '无效的令牌！'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated

# 管理员数据统计
@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def get_admin_stats(current_user):
    try:
        # 用户统计
        total_users = User.query.count()
        
        # 导入datetime
        from datetime import datetime, timedelta
        today_users = User.query.filter(
            User.created_at >= datetime.now(timezone.utc).date()
        ).count()
        
        # 修改字段名称和注释，反映这是最后活跃时间
        today_active_users = User.query.filter(
            User.last_login_at >= datetime.now(timezone.utc).date()
        ).count()
        
        # 修改字段名称和注释，反映这是最后活跃时间
        recent_active_users = User.query.filter(
            User.last_login_at >= datetime.now(timezone.utc) - timedelta(days=7)
        ).count()
        
        # 房间统计 - 只统计活跃房间
        total_rooms = Room.query.count()
        active_rooms = Room.query.filter_by(is_active=True).count()
        waiting_rooms = Room.query.filter_by(game_status='waiting', is_active=True).count()
        playing_rooms = Room.query.filter_by(game_status='playing', is_active=True).count()
        
        # 活跃度统计 - 只统计活跃房间的成员
        total_memberships = RoomMember.query.join(Room).filter(Room.is_active == True).count()
        avg_players_per_room = total_memberships / active_rooms if active_rooms > 0 else 0
        
        return jsonify({
            'user_stats': {
                'total_users': total_users,
                'today_users': today_users,
                'today_active_users': today_active_users,  # 现在基于最后活跃时间
                'recent_active_users': recent_active_users  # 现在基于最后活跃时间
            },
            'room_stats': {
                'total_rooms': total_rooms,
                'active_rooms': active_rooms,
                'waiting_rooms': waiting_rooms,
                'playing_rooms': playing_rooms,
                'total_memberships': total_memberships,
                'avg_players_per_room': round(avg_players_per_room, 2)
            }
        }), 200
    except Exception as e:
        print(f"获取管理员统计错误: {str(e)}")
        return jsonify({'message': '获取统计信息失败！'}), 500


# 获取所有用户列表
@app.route('/api/admin/users', methods=['GET'])
@admin_required
def get_all_users(current_user):
    try:
        users = User.query.all()
        return jsonify({
            'users': [user.to_dict() for user in users]
        }), 200
    except Exception as e:
        print(f"获取用户列表错误: {str(e)}")
        return jsonify({'message': '获取用户列表失败！'}), 500

@app.route('/api/admin/rooms', methods=['GET'])
@admin_required
def get_all_rooms(current_user):
    try:
        # 获取所有房间，包括非活跃的，但标记它们的状态
        rooms = Room.query.all()
        rooms_data = []
        for room in rooms:
            room_dict = room.to_dict()
            # 确保返回 game_status
            if not room.is_active:
                room_dict['game_status'] = 'closed'  # 添加一个特殊状态表示已关闭
            rooms_data.append(room_dict)
            
        return jsonify({
            'rooms': rooms_data
        }), 200
    except Exception as e:
        print(f"获取房间列表错误: {str(e)}")
        return jsonify({'message': '获取房间列表失败！'}), 500

@app.route('/api/rooms/<int:room_id>/name', methods=['PUT'])
@token_required
def update_room_name(current_user, room_id):
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'message': '房间名称是必需的！'}), 400

    new_name = data['name']
    if len(new_name) < 2:
        return jsonify({'message': '房间名称至少需要2个字符！'}), 400

    room = Room.query.get(room_id)
    if not room:
        return jsonify({'message': '房间不存在！'}), 404

    if room.creator_id != current_user.id:
        return jsonify({'message': '您没有权限修改此房间的名称！'}), 403

    old_name = room.name
    room.name = new_name
    ()
    try:
        system_message = room.name
        system_chat = {
            'room_id': room_id,
            'user_id': current_user.id,
            'message_type': 'system',
            'content': system_message
        }
        db.session.commit()
        # 通过SocketIO广播系统消息
        socketio.emit('update-name', system_chat, to=str(room_id))

        system_message = f"房主更新了房间名称：{old_name} → {new_name}"   
        _send_system_message(room_id, system_message)

        return jsonify({'message': '房间名称更新成功！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"更新房间名称错误: {str(e)}")
        return jsonify({'message': '更新房间名称失败，请稍后重试！'}), 500

@app.route('/api/rooms/<int:room_id>/update_max_players', methods=['POST'])
@token_required
def update_max_players(current_user, room_id):
    data = request.get_json()
    if not data or not data.get('max_players'):
        return jsonify({'message': '最大玩家数是必需的！'}), 400

    new_max_players = data['max_players']
    if not isinstance(new_max_players, int) or new_max_players < 2 or new_max_players > 50:
        return jsonify({'message': '最大玩家数必须是2到50之间的整数！'}), 400

    room = Room.query.get(room_id)
    if not room:
        return jsonify({'message': '房间不存在！'}), 404

    if room.creator_id != current_user.id:
        return jsonify({'message': '您没有权限修改此房间的最大玩家数！'}), 403

    old_max_players = room.max_players
    room.max_players = new_max_players
    ()
    try:
        system_message = room.max_players
        system_chat = {
            'room_id': room_id,
            'user_id': current_user.id,
            'message_type': 'system',
            'content': system_message
        }
        db.session.commit()
        # 通过SocketIO广播系统消息
        socketio.emit('update-max-players', system_chat, to=str(room_id))

        system_message = f"房主更新了房间最大玩家数：{old_max_players} → {new_max_players}"   
        _send_system_message(room_id, system_message)

        return jsonify({'message': '最大玩家数更新成功！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"更新最大玩家数错误: {str(e)}")
        return jsonify({'message': '更新最大玩家数失败，请稍后重试！'}), 500

@app.route('/api/user/update-password', methods=['PUT'])
@token_required
def update_password(current_user):
    data = request.get_json()
    
    if not data or not data.get('current_password') or not data.get('new_password'):
        return jsonify({'message': '当前密码和新密码是必需的！'}), 400
    
    # 验证当前密码
    if not check_password_hash(current_user.password_hash, data['current_password']):
        return jsonify({'message': '当前密码错误！'}), 401
    
    # 更新密码
    hashed_password = generate_password_hash(data['new_password'])
    current_user.password_hash = hashed_password
    
    try:
        db.session.commit()
        return jsonify({'message': '密码修改成功！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"修改密码错误: {str(e)}")
        return jsonify({'message': '修改密码失败，请稍后重试！'}), 500

@app.route('/api/rooms/<int:room_id>/add_password', methods=['POST'])
@token_required
def add_room_password(current_user, room_id):
    data = request.get_json()
    
    if not data or not data.get('new_password'):
        return jsonify({'message': '新密码是必需的！'}), 400
    
    room = Room.query.get(room_id)
    if not room:
        return jsonify({'message': '房间不存在！'}), 404

    # 检查用户是否有权限修改房间密码
    if room.creator_id != current_user.id:
        return jsonify({'message': '您没有权限修改此房间的密码！'}), 403

    room.password = data['new_password']
    room.room_type = 'private'  # 将房间类型改为私密
    ()

    try:
        system_message = room.room_type
        system_chat = {
            'room_id': room_id,
            'user_id': current_user.id,
            'message_type': 'system',
            'content': system_message
        }
        db.session.commit()
        # 通过SocketIO广播系统消息
        socketio.emit('update-room-type', system_chat, to=str(room_id))
        return jsonify({'message': '房间密码添加成功！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"添加房间密码错误: {str(e)}")
        return jsonify({'message': '添加房间密码失败，请稍后重试！'}), 500

@app.route('/api/rooms/<int:room_id>/delete_password', methods=['POST'])
@token_required
def delete_room_password(current_user, room_id):
    room = Room.query.get(room_id)
    if not room:
        return jsonify({'message': '房间不存在！'}), 404

    # 检查用户是否有权限修改房间密码
    if room.creator_id != current_user.id:
        return jsonify({'message': '您没有权限修改此房间的密码！'}), 403

    # 删除房间密码
    room.password = None
    room.room_type = 'public'  # 将房间类型改为公开
    ()
    try:
        system_message = room.room_type
        system_chat = {
            'room_id': room_id,
            'user_id': current_user.id,
            'message_type': 'system',
            'content': system_message
        }
        db.session.commit()
        # 通过SocketIO广播系统消息
        socketio.emit('update-room-type', system_chat, to=str(room_id))
        return jsonify({'message': '房间密码已删除！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"删除房间密码错误: {str(e)}")
        return jsonify({'message': '删除房间密码失败，请稍后重试！'}), 500


@app.route('/api/rooms/<int:room_id>/change_password', methods=['POST'])
@token_required
def change_room_password(current_user, room_id):
    data = request.get_json()
    
    if not data or not data.get('new_password'):
        return jsonify({'message': '新密码是必需的！'}), 400
    
    room = Room.query.get(room_id)
    if not room:
        return jsonify({'message': '房间不存在！'}), 404
    
    # 检查用户是否有权限修改房间密码
    if room.creator_id != current_user.id:
        return jsonify({'message': '您没有权限修改此房间的密码！'}), 403
    
    # 更新房间密码
    room.password = data['new_password']
    print(data)
    try:
        db.session.commit()
        return jsonify({'message': '房间密码修改成功！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"修改房间密码错误: {str(e)}")
        return jsonify({'message': '修改房间密码失败，请稍后重试！'}), 500

@app.route('/api/validate_token', methods=['POST'])
@token_required
def validate_token(current_user):
    return jsonify({'valid': True}), 200

@app.route('/api/user/delete-account', methods=['DELETE'])
@token_required
def delete_account(current_user):
    try:
        # 检查用户是否在活跃房间中
        memberships = RoomMember.query.filter_by(user_id=current_user.id).all()
        for membership in memberships:
            if membership.room.creator_id == current_user.id and membership.room.is_active:
                return jsonify({'message': '请先解散您创建的活跃房间！'}), 400
        
        # 删除用户账户
        db.session.delete(current_user)
        db.session.commit()
        
        return jsonify({'message': '账户已成功删除！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"删除账户错误: {str(e)}")
        return jsonify({'message': '删除账户失败，请稍后重试！'}), 500

@app.route('/api/user/delete', methods=['DELETE'])
@token_required
def admin_delete_own_account(current_user):
    try:
        # 检查用户是否在活跃房间中
        memberships = RoomMember.query.filter_by(user_id=current_user.id).all()
        for membership in memberships:
            if membership.room.creator_id == current_user.id and membership.room.is_active:
                return jsonify({'message': '请先解散您创建的活跃房间！'}), 400
        
        # 删除用户账户
        db.session.delete(current_user)
        db.session.commit()
        
        return jsonify({'message': '账户已成功删除！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"删除账户错误: {str(e)}")
        return jsonify({'message': '删除账户失败，请稍后重试！'}), 500

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': '用户名和密码是必需的！'}), 400
    
    if len(data['username']) < 3:
        return jsonify({'message': '用户名至少需要3个字符！'}), 400
    
    if len(data['password']) < 6:
        return jsonify({'message': '密码至少需要6个字符！'}), 400
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'message': '用户名已存在！'}), 409
    
    hashed_password = generate_password_hash(data['password'])
    new_user = User(
        nickname=data.get('nickname', ''),
        profile = 'null',
        username=data['username'],
        password_hash=hashed_password,
        last_login_at=datetime.now(east8)
    )
    
    # 处理昵称（如果有的话）
    try:
        db.session.add(new_user)
        db.session.commit()
        tips_update_total_users()
        token = new_user.generate_token()
        
        return jsonify({
            'message': '用户注册成功！',
            'token': token,
            'user': new_user.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        print(f"注册错误: {str(e)}")
        return jsonify({'message': '注册失败，请稍后重试！'}), 500
# 删除用户
@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(current_user, user_id):
    if user_id == current_user.id:
        return jsonify({'message': '不能删除自己！'}), 400
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'message': '用户不存在！'}), 404
    
    try:
        # 注意：由于设置了级联删除，删除用户会自动删除相关的房间和成员关系
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'message': '用户删除成功！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"删除用户错误: {str(e)}")
        return jsonify({'message': '删除用户失败！'}), 500

@app.route('/api/admin/rooms/<int:room_id>', methods=['DELETE'])
@admin_required
def admin_delete_room(current_user, room_id):
    room = Room.query.get(room_id)
    if not room:
        return jsonify({'message': '房间不存在！'}), 404
    
    try:
        # 发送系统消息
        _send_system_message(room_id, "管理员删除了房间")
        
        # 直接删除房间，由于级联设置，相关的聊天记录和成员关系会自动删除
        db.session.delete(room)
        db.session.commit()
        
        return jsonify({'message': '房间删除成功！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"删除房间错误: {str(e)}")
        return jsonify({'message': '删除房间失败！'}), 500


# 获取系统日志（简化版）
@app.route('/api/admin/logs', methods=['GET'])
@admin_required
def get_system_logs(current_user):
    # 在实际应用中，这里应该从日志文件或数据库读取
    # 这里返回一些模拟数据
    logs = [
        {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': 'INFO',
            'message': '系统启动完成'
        },
        {
            'timestamp': (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            'level': 'INFO',
            'message': '新用户注册: testuser'
        },
        {
            'timestamp': (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
            'level': 'WARNING',
            'message': '房间创建失败: 联机标识码格式错误'
        }
    ]
    
    return jsonify({'logs': logs}), 200

@app.route('/api/user/nickname', methods=['PUT'])
@token_required
def update_user_nickname(current_user):
    data = request.get_json()
    
    if not data:
        return jsonify({'message': '没有提供数据！'}), 400
    
    nickname = data.get('nickname', '')
    
    # 昵称长度限制
    if len(nickname) > 20:
        return jsonify({'message': '昵称长度不能超过20字符！'}), 400
    
    try:
        current_user.nickname = nickname
        db.session.commit()
        
        return jsonify({
            'message': '用户昵称更新成功！',
            'user': current_user.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"更新用户昵称错误: {str(e)}")
        return jsonify({'message': '更新昵称失败，请稍后重试！'}), 500

@app.route('/api/user/password', methods=['PUT'])
@token_required
def update_user_password(current_user):
    data = request.get_json()
    
    if not data:
        return jsonify({'message': '没有提供数据！'}), 400
    
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    
    # 验证当前密码
    if not check_password_hash(current_user.password_hash, current_password):
        return jsonify({'message': '当前密码不正确！'}), 400
    
    # 新密码长度限制
    if len(new_password) < 6:
        return jsonify({'message': '新密码长度不能少于6字符！'}), 400
    
    try:
        hashed_password = generate_password_hash(new_password)
        current_user.password_hash = hashed_password
        db.session.commit()
        
        return jsonify({
            'message': '用户密码更新成功！'
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"更新用户密码错误: {str(e)}")
        return jsonify({'message': '更新密码失败，请稍后重试！'}), 500

@app.route('/api/user/profile', methods=['PUT'])
@token_required
def update_user_profile(current_user):
    data = request.get_json()
    
    if not data:
        return jsonify({'message': '没有提供数据！'}), 400
    
    profile = data.get('profile', '')
    
    # 简介长度限制
    if len(profile) > 50:
        return jsonify({'message': '简介长度不能超过50字符！'}), 400
    
    try:
        current_user.profile = profile
        db.session.commit()
        
        return jsonify({
            'message': '用户简介更新成功！',
            'user': current_user.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"更新用户简介错误: {str(e)}")
        return jsonify({'message': '更新简介失败，请稍后重试！'}), 500

@app.route('/api/admin/rooms/<int:room_id>/status', methods=['PUT'])
@admin_required
def admin_update_room_status(current_user, room_id):
    room = Room.query.get(room_id)
    if not room:
        return jsonify({'message': '房间不存在！'}), 404

    data = request.get_json()
    if not data or not data.get('game_status'):
        return jsonify({'message': '游戏状态是必需的！'}), 400

    allowed_statuses = ['waiting', 'playing', 'finished']
    if data['game_status'] not in allowed_statuses:
        return jsonify({'message': '无效的游戏状态！'}), 400

    try:
        room.game_status = data['game_status']

        db.session.commit()

        return jsonify({
            'message': '游戏状态更新成功！',
            'room': room.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"更新游戏状态错误: {str(e)}")
        return jsonify({'message': '更新游戏状态失败，请稍后重试！'}), 500


@app.route('/api/user/profile', methods=['GET'])
@token_required
def get_user_profile(current_user):
    return jsonify({
        'user': current_user.to_dict()
    }), 200

@app.route('/api/rooms/<int:room_id>/chat', methods=['GET'])
@token_required
def get_room_chat(current_user, room_id):
    room = Room.query.get(room_id)
    if not room or not room.is_active:
        return jsonify({'message': '房间不存在！'}), 404
    # 检查用户是否在房间中
    membership = RoomMember.query.filter_by(
        user_id=current_user.id,
        room_id=room_id
    ).first()
    if not membership:
        return jsonify({'message': '您不是这个房间的成员！'}), 403
    try:
        # 分页参数
        before_id = request.args.get('before_id', type=int)
        query = RoomChat.query.filter_by(room_id=room_id)
        if before_id:
            # 只查比 before_id 更早的消息
            query = query.filter(RoomChat.id < before_id)
        # 按时间降序取50条
        messages = query.order_by(RoomChat.created_at.desc()).limit(50).all()
        messages.reverse()  # 最旧的在前
        latest_message_id = 0
        if messages:
            latest_message_id = messages[-1].id
        return jsonify({
            'messages': [message.to_dict() for message in messages],
            'latest_message_id': latest_message_id,
            'total_messages': len(messages)
        }), 200
    except Exception as e:
        print(f"获取聊天消息错误: {str(e)}")
        return jsonify({'message': '获取聊天消息失败！'}), 500

# 发送聊天消息
@app.route('/api/rooms/<int:room_id>/chat', methods=['POST'])
@token_required
def send_room_chat(current_user, room_id):
    room = Room.query.get(room_id)
    
    if not room or not room.is_active:
        return jsonify({'message': '房间不存在！'}), 404
    
    # 检查用户是否在房间中
    membership = RoomMember.query.filter_by(
        user_id=current_user.id, 
        room_id=room_id
    ).first()
    
    if not membership:
        return jsonify({'message': '您不是这个房间的成员！'}), 403
    
    data = request.get_json()
    
    if not data or not data.get('content'):
        return jsonify({'message': '消息内容不能为空！'}), 400
    
    content = data['content'].strip()
    if len(content) == 0:
        return jsonify({'message': '消息内容不能为空！'}), 400
    
    if len(content) > 500:
        return jsonify({'message': '消息内容不能超过500字符！'}), 400
    
    try:
        # 创建聊天消息
        chat_message = RoomChat(
            room_id=room_id,
            user_id=current_user.id,
            nickname = current_user.nickname,
            message_type='user',
            content=content
        )
        
        db.session.add(chat_message)
        db.session.commit()
        
        # 通过SocketIO广播消息
        message_data = chat_message.to_dict()
        socketio.emit('message', message_data, to=str(room_id))
        
        return jsonify({
            'message': '消息发送成功！',
            'chat_message': message_data
        }), 201
    except Exception as e:
        db.session.rollback()
        print(f"发送聊天消息错误: {str(e)}")
        return jsonify({'message': '发送消息失败！'}), 500

# 发送系统消息（内部使用）
def _send_system_message(room_id, content):
    try:
        system_message = RoomChat(
            room_id=room_id,
            user_id=0,  # 系统用户ID为0
            message_type='system',
            content=content
        )
        db.session.add(system_message)
        db.session.commit()
        message_data = system_message.to_dict()
        socketio.emit('message', message_data, to=str(room_id))

        return True
    except Exception as e:
        db.session.rollback()
        print(f"发送系统消息错误: {str(e)}")
        return False
    
def tips_update_online_users(user_id):
    # 向房间0发送提示：在线人数可以更新了
    socketio.emit('update-online-users', {'room_id': 0})
    # 批量获取用户所有活跃房间id
    active_room_ids = [m.room_id for m in RoomMember.query.filter_by(user_id=user_id).join(Room).filter(Room.is_active==True).all()]
    # 批量发送在线成员更新
    for room_id in set(active_room_ids):
        socketio.emit('update-online-members', {'room_id': room_id, 'user_id': user_id}, to=str(room_id))
    # 批量获取用户作为房主的活跃房间
    owned_rooms = Room.query.filter_by(creator_id=user_id, is_active=True).all()
    for room in owned_rooms:
        modify_room = {
            'id': room.id,
            'name': room.name,
            'server_address': room.server_address,
            'description': room.description,
            'creator': room.creator.username,
            'creator_id': room.creator_id,
            'creator_nickname': room.creator.nickname,
            'created_at': room.created_at.isoformat(),
            'member_count': len(room.members),
            'max_players': room.max_players,
            'room_type': room.room_type,
            'game_status': room.game_status,
            'is_owner_online': room.creator_id in online_user_list
        }
        socketio.emit('room_updated', modify_room, to='0')


def tips_update_active_rooms():
    #向房间0发送提示：活跃房间列表可以更新了
    socketio.emit('update-active-rooms', {'room_id': 0})

def tips_update_total_users():
    #向房间0发送提示：总用户数可以更新了
    socketio.emit('update-total-users', {'room_id': 0})

def tips_update_total_rooms():
    #向房间0发送提示：总房间数可以更新了
    socketio.emit('update-total-rooms', {'room_id': 0})

# 管理员获取所有聊天消息
@app.route('/api/admin/chat-messages', methods=['GET'])
@admin_required
def get_all_chat_messages(current_user):
    try:
        # 获取查询参数
        room_id = request.args.get('room_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        # 构建查询
        query = RoomChat.query
        
        # 如果提供了房间ID，过滤该房间的消息
        if room_id:
            query = query.filter_by(room_id=room_id)
        
        # 按时间倒序排列，最新的在前面
        messages = query.order_by(RoomChat.created_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        # 获取所有房间列表（包括非活跃的）
        all_rooms = Room.query.order_by(Room.is_active.desc(), Room.created_at.desc()).all()
        
        return jsonify({
            'messages': [message.to_dict() for message in messages.items],
            'pagination': {
                'page': messages.page,
                'per_page': messages.per_page,
                'total': messages.total,
                'pages': messages.pages
            },
            'rooms': [{
                'id': room.id, 
                'name': room.name,
                'is_active': room.is_active,
                'creator': room.creator.username
            } for room in all_rooms]
        }), 200
    except Exception as e:
        print(f"获取所有聊天消息错误: {str(e)}")
        return jsonify({'message': '获取聊天消息失败！'}), 500
# 获取房间成员信息
@app.route('/api/admin/rooms/<int:room_id>/members', methods=['GET'])
@admin_required
def get_room_members(current_user, room_id):
    room = Room.query.get(room_id)
    
    if not room:
        return jsonify({'message': '房间不存在！'}), 404
    
    try:
        members = []
        for member in room.members:
            membership = RoomMember.query.filter_by(
                user_id=member.user.id, 
                room_id=room_id
            ).first()
            
            members.append({
                'id': member.user.id,
                'username': member.user.username,
                'profile': member.user.profile,
                'is_ready': membership.is_ready if membership else False,
                'is_online': member.user.id in online_user_list 
            })
        
        return jsonify({
            'room': {
                'id': room.id,
                'name': room.name,
                'creator_id': room.creator_id
            },
            'members': members
        }), 200
    except Exception as e:
        print(f"获取房间成员错误: {str(e)}")
        return jsonify({'message': '获取房间成员失败！'}), 500

# 管理员删除聊天消息
@app.route('/api/admin/chat-messages/<int:message_id>', methods=['DELETE'])
@admin_required
def delete_chat_message(current_user, message_id):
    try:
        message = RoomChat.query.get(message_id)
        
        if not message:
            return jsonify({'message': '消息不存在！'}), 404
        
        db.session.delete(message)
        db.session.commit()
        
        tips_withdraw_message(message_id, message.room_id)
        return jsonify({'message': '消息删除成功！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"删除聊天消息错误: {str(e)}")
        return jsonify({'message': '删除消息失败！'}), 500

# 发送系统消息
@app.route('/api/admin/system-messages', methods=['POST'])
@admin_required
def send_system_message(current_user):
    data = request.get_json()
    
    if not data or not data.get('content'):
        return jsonify({'message': '消息内容不能为空！'}), 400
    
    content = data['content'].strip()
    if len(content) == 0:
        return jsonify({'message': '消息内容不能为空！'}), 400
    
    message_type = data.get('message_type', 'announcement')
    target = data.get('target', 'all')
    specific_room_id = data.get('specific_room_id')
    
    try:
        rooms_to_send = []
        
        if target == 'all':
            # 发送到所有活跃房间
            rooms_to_send = Room.query.filter_by(is_active=True).all()
        elif target == 'active':
            # 发送到所有活跃房间
            rooms_to_send = Room.query.filter_by(is_active=True).all()
        elif target == 'specific' and specific_room_id:
            # 发送到指定房间
            room = Room.query.get(specific_room_id)
            if room and room.is_active:
                rooms_to_send = [room]
            else:
                return jsonify({'message': '指定房间不存在或未激活！'}), 404
        
        success_count = 0
        failed_rooms = []
        
        for room in rooms_to_send:
            try:
                # 构建完整的消息内容
                full_content = content
                if message_type == 'maintenance':
                    full_content = f"🔧 系统维护: {content}"
                elif message_type == 'update':
                    full_content = f"🔄 系统更新: {content}"
                elif message_type == 'emergency':
                    full_content = f"🚨 紧急通知: {content}"
                elif message_type == 'announcement':
                    full_content = f"📢 系统公告: {content}"
                
                # 发送系统消息
                if _send_system_message(room.id, full_content):
                    success_count += 1
                else:
                    failed_rooms.append(room.id)
            except Exception as e:
                print(f"向房间 {room.id} 发送系统消息失败: {str(e)}")
                failed_rooms.append(room.id)
        
        # 记录系统消息发送日志
        system_message_log = {
            'admin_id': current_user.id,
            'message_type': message_type,
            'target': target,
            'specific_room_id': specific_room_id,
            'content': content,
            'success_count': success_count,
            'failed_count': len(failed_rooms),
            'failed_rooms': failed_rooms,
            'sent_at': datetime.now(east8).isoformat()
        }
        
        # 在实际应用中，这里应该将日志保存到数据库
        print(f"系统消息发送日志: {system_message_log}")
        
        message = f"系统消息发送完成！成功: {success_count} 个房间"
        if failed_rooms:
            message += f"，失败: {len(failed_rooms)} 个房间"
        
        return jsonify({
            'message': message,
            'success_count': success_count,
            'failed_count': len(failed_rooms),
            'failed_rooms': failed_rooms
        }), 200
        
    except Exception as e:
        print(f"发送系统消息错误: {str(e)}")
        return jsonify({'message': '发送系统消息失败！'}), 500

# 在 app.py 中添加管理员获取单个房间信息的路由

@app.route('/api/admin/rooms/<int:room_id>', methods=['GET'])
@admin_required
def admin_get_room(current_user, room_id):
    room = Room.query.get(room_id)
    
    if not room:
        return jsonify({'message': '房间不存在！'}), 404
    
    return jsonify({
        'room': room.to_dict()
    }), 200

@app.route('/api/admin/rooms/<int:room_id>/soft-delete', methods=['PUT'])
@admin_required
def admin_soft_delete_room(current_user, room_id):
    room = Room.query.get(room_id)
    if not room:
        return jsonify({'message': '房间不存在！'}), 404
    
    try:
        # 发送系统消息
        _send_system_message(room_id, "管理员关闭了房间")
        tips_update_active_rooms()
        ()
        # 软删除：将房间标记为非活跃
        room.is_active = False
        db.session.commit()
        
        return jsonify({'message': '房间已关闭！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"关闭房间错误: {str(e)}")
        return jsonify({'message': '关闭房间失败！'}), 500

@app.route('/api/admin/rooms/<int:room_id>/restore', methods=['PUT'])
@admin_required
def admin_restore_room(current_user, room_id):
    room = Room.query.get(room_id)
    if not room:
        return jsonify({'message': '房间不存在！'}), 404
    
    try:
        # 恢复房间
        room.is_active = True
        db.session.commit()
        
        return jsonify({'message': '房间已恢复！'}), 200
    except Exception as e:
        db.session.rollback()
        print(f"恢复房间错误: {str(e)}")
        return jsonify({'message': '恢复房间失败！'}), 500

# 获取最近发送的系统消息
@app.route('/api/admin/system-messages', methods=['GET'])
@admin_required
def get_recent_system_messages(current_user):
    try:
        # 在实际应用中，这里应该从数据库获取历史记录
        # 这里返回一些示例数据
        recent_messages = [
            {
                'id': 1,
                'content': '系统将于今晚24:00进行维护，预计耗时2小时',
                'message_type': 'maintenance',
                'target': 'all',
                'sent_at': (datetime.now(east8) - timedelta(hours=1)).isoformat(),
                'success_count': 15,
                'failed_count': 0
            },
            {
                'id': 2,
                'content': '新版本v1.2.0已发布，修复了若干已知问题',
                'message_type': 'update',
                'target': 'all',
                'sent_at': (datetime.now(east8) - timedelta(days=1)).isoformat(),
                'success_count': 12,
                'failed_count': 1
            }
        ]
        
        return jsonify({
            'recent_messages': recent_messages
        }), 200
    except Exception as e:
        print(f"获取最近系统消息错误: {str(e)}")
        return jsonify({'message': '获取最近系统消息失败！'}), 500

def socketio_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # 从请求中获取token
        if 'token' in request.args:
            token = request.args.get('token')
        
        if not token:
            # 尝试从headers获取
            if 'Authorization' in request.headers:
                auth_header = request.headers['Authorization']
                try:
                    token = auth_header.split(" ")[1]
                except IndexError:
                    return None
        
        if not token:
            return None
        
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = User.query.get(data['user_id'])
            return current_user
        except:
            return None
    
    return decorated

# SocketIO连接处理
@socketio.on('connect')
def handle_connect():
    emit('connected', {'status': 'connected', 'sid': request.sid})

@socketio.on('disconnect')
def handle_disconnect():
    user_id = None
    for index_ in range(len(online_user_sid_list)):
        if request.sid in online_user_sid_list[index_]:
            user_id = online_user_list[index_]
            online_user_sid_list[index_].remove(request.sid)
            # 计算在线时间：
            online_time = time.time() - online_start_time_list[index_]
            online_start_time_list[index_] = time.time()
            user = User.query.get(user_id)
            user.total_online_time += online_time
            db.session.commit()
            if len(online_user_sid_list[index_]) == 0:
                online_user_sid_list.pop(index_)
                online_user_list.pop(index_)
                online_start_time_list.pop(index_)
                if user_id is not None:
                    tips_update_online_users(user_id)
            break
            
            


def get_user_from_token(token):
    """从token获取用户"""
    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        current_user = User.query.get(data['user_id'])
        return current_user
    except Exception as e:
        print(f"Token验证失败: {str(e)}")
        return None

@socketio.on('authenticate')
def handle_authenticate(data):
    token = data.get('token')
    if token:
        user = get_user_from_token(token)
        if user:
            print(f"用户 {user.username} 验证成功")
            return True
    return False

@socketio.on('chat')
def handle_chat(current_user, data):
    room_id = data.get('room_id')
    message = data.get('message')
    
    if room_id and message:

        chat_message = RoomChat(
        room_id=room_id,
        user_id=current_user.get('id'),
        message_type='user',
        nickname = current_user.get('nickname'),
        content=message
        )
        db.session.add(chat_message)
        db.session.commit()
        emit('message', chat_message.to_dict(), to=str(room_id))

@socketio.on('withdraw_chat')
def handle_withdraw_chat(current_user, data):
    message_id = data.get('message_id')
    chat_message = RoomChat.query.get(message_id)
    if not chat_message:
        return {'success': False, 'message': '消息不存在'}

    isRoomCreator = False
    room = Room.query.get(chat_message.room_id)
    if room and room.creator_id == current_user.get('id'):
        isRoomCreator = True
    if chat_message.user_id != current_user.get('id') and not isRoomCreator:
        return {'success': False, 'message': '您没有权限撤回这条消息'}
    
    try:
        db.session.delete(chat_message)
        db.session.commit()
        tips_withdraw_message(message_id, chat_message.room_id)
        return {'success': True, 'message': '消息撤回成功'}
    except Exception as e:
        db.session.rollback()
        print(f"撤回消息错误: {str(e)}")
        return {'success': False, 'message': '消息撤回失败'}

def tips_withdraw_message(message_id, room_id):
    # 广播消息撤回事件
    socketio.emit('withdraw_message', {'message_id': message_id}, to=str(room_id))

# 加入房间的SocketIO事件
@socketio.on('join_room')
@token_required_for_socketio
def handle_join_room(current_user, data):
    """加入SocketIO房间"""
    room_id = data.get('room_id')

    if not room_id:
        return {'success': False, 'message': '房间ID不能为空'}
    # 验证用户是否有权加入此房间

    membership = RoomMember.query.filter_by(
        user_id=current_user.id, 
        room_id=room_id
    ).first()
    
    if not membership:
        return {'success': False, 'message': '您不是该房间的成员'}
    
    # 加入SocketIO房间
    join_room(str(room_id))
    print(f"用户 {current_user.nickname} 加入SocketIO房间 {room_id}")
    
    return {'success': True, 'message': '加入房间成功'}

# 离开房间的SocketIO事件
@socketio.on('leave_room')
@token_required_for_socketio
def handle_leave_room(current_user, data):
    """离开SocketIO房间"""
    room_id = data.get('room_id')
    if not room_id:
        return {'success': False, 'message': '房间ID不能为空'}
    
    # 离开SocketIO房间
    leave_room(str(room_id))
    
    return {'success': True, 'message': '离开房间成功'}

# 匹配相关的路由和SocketIO事件
@app.route('/api/Ismatching', methods=['GET'])
@token_required
def is_matching(current_user):
    """检查用户是否在匹配中"""
    try:
        match_user = MatchUser.query.filter_by(
            user_id=current_user.id, 
            is_matched=False
        ).first()
        
        if match_user:
            return jsonify({
                'is_matching': True,
                'match': match_user.to_dict()
            }), 200
        else:
            return jsonify({'is_matching': False}), 200
            
    except Exception as e:
        print(f"检查匹配状态错误: {str(e)}")
        return jsonify({'message': '检查匹配状态失败！'}), 500

@app.route('/api/match', methods=['POST'])
@token_required
def start_match(current_user):
    """开始匹配"""
    data = request.get_json()
    
    if not data or not data.get('match_text'):
        return jsonify({'message': '匹配文本不能为空！'}), 400
    
    match_text = data['match_text'].strip()
    player_required = data.get('player_required', 2)
    
    if len(match_text) == 0:
        return jsonify({'message': '匹配文本不能为空！'}), 400
    
    if player_required < 2 or player_required > 8:
        return jsonify({'message': '玩家人数必须在2-8之间！'}), 400
    
    try:
        # 检查用户是否已经在匹配中
        existing_match = MatchUser.query.filter_by(
            user_id=current_user.id, 
            is_matched=False
        ).first()
        
        if existing_match:
            return jsonify({'message': '您已经在匹配中！'}), 400
        
        # 创建匹配记录
        match_user = MatchUser(
            user_id=current_user.id,
            match_text=match_text,
            player_required=player_required
        )
        
        db.session.add(match_user)
        db.session.commit()
        
        # 检查是否可以匹配
        check_and_create_match(match_text, player_required)
        
        socketio.emit('match_started', {
            'user_id': current_user.id,
            'match_text': match_user.match_text
        }, to='0')

        return jsonify({
            'message': '开始匹配成功！',
            'match': match_user.to_dict()
        }), 201
            
    except Exception as e:
        db.session.rollback()
        print(f"开始匹配错误: {str(e)}")
        return jsonify({'message': '开始匹配失败，请稍后重试！'}), 500

@app.route('/api/match', methods=['DELETE'])
@token_required
def cancel_match(current_user):
    """取消匹配"""
    try:
        match_user = MatchUser.query.filter_by(
            user_id=current_user.id, 
            is_matched=False
        ).first()
        
        if not match_user:
            return jsonify({'message': '您当前没有在匹配中！'}), 404
        
        db.session.delete(match_user)
        db.session.commit()

        socketio.emit('match_cancelled', {
            'user_id': current_user.id,
            'match_text': match_user.match_text
        }, to='0')
        
        return jsonify({'message': '取消匹配成功！'}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"取消匹配错误: {str(e)}")
        return jsonify({'message': '取消匹配失败！'}), 500

@app.route('/api/user/match-records', methods=['GET'])
@token_required
def get_user_match_records(current_user):
    """获取用户的匹配记录"""
    try:
        # 获取所有匹配记录
        match_records = MatchUser.query.order_by(MatchUser.created_at.desc()).all()
        
        # 统计数据
        total_matches = len(match_records)
        successful_matches = len([r for r in match_records if r.is_matched])
        successful_rooms = len(set([r.room_id for r in match_records if r.room_id is not None]))
        
        records_data = []
        for record in match_records:
            record_data = {
                'id': record.id,
                'match_text': record.match_text,
                'player_required': record.player_required,
                'is_matched': record.is_matched,
                'created_at': record.created_at.isoformat() if record.created_at else None,
                'room_id': record.room_id
            }
            records_data.append(record_data)
        
        return jsonify({
            'records': records_data,
            'stats': {
                'total_matches': total_matches,
                'successful_matches': successful_matches,
                'successful_rooms': successful_rooms
            }
        }), 200
        
    except Exception as e:
        print(f"获取匹配记录错误: {str(e)}")
        return jsonify({'message': '获取匹配记录失败！'}), 500

def check_and_create_match(match_text, player_required):
    """检查并创建匹配"""
    try:
        # 只查前N个未匹配用户，避免全表扫描
        waiting_users = MatchUser.query.filter_by(
            match_text=match_text,
            player_required=player_required,
            is_matched=False
        ).order_by(MatchUser.created_at.asc()).limit(player_required).all()
        if len(waiting_users) < player_required:
            return  # 不足则直接返回

        # 批量获取用户对象，减少N+1
        user_ids = [u.user_id for u in waiting_users]
        users = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()}
        creator = users.get(waiting_users[0].user_id)
        room_name = f"匹配房间-{match_text}"
        new_room = Room(
            name=room_name,
            server_address='匹配服务器',
            description=f'自动匹配创建的房间，匹配项目：{match_text}',
            max_players=player_required,
            creator_id=creator.id if creator else None,
            room_type='public'
        )
        db.session.add(new_room)
        db.session.flush()

        # 批量插入成员
        memberships = [RoomMember(
            user_id=match_user.user_id,
            room_id=new_room.id,
            is_ready=(i == 0)
        ) for i, match_user in enumerate(waiting_users)]
        db.session.bulk_save_objects(memberships)

        # 批量更新匹配状态
        MatchUser.query.filter(MatchUser.id.in_([u.id for u in waiting_users])).update({
            MatchUser.is_matched: True,
            MatchUser.room_id: new_room.id
        }, synchronize_session=False)

        # 发送系统消息
        system_message = f"匹配成功！房间已创建，匹配项目：{match_text}"
        system_chat = RoomChat(
            room_id=new_room.id,
            user_id=0,
            message_type='system',
            content=system_message
        )
        db.session.add(system_chat)
        db.session.commit()

        # 通知所有匹配成功的用户（发送到匹配房间0）
        room_data = new_room.to_dict()
        socketio.emit('match_success', {
            'room': room_data,
            'match_text': match_text,
            'matched_users': user_ids
        }, to='0')
        ()
        print(f"匹配成功：{match_text}，创建房间 {new_room.id}，玩家数：{len(waiting_users)}")
    except Exception as e:
        db.session.rollback()
        print(f"创建匹配错误: {str(e)}")

@socketio.on('join_room_zero')
@token_required_for_socketio
def handle_join_room_zero(current_user, data):
    """加入匹配房间（房间0）"""
    join_room('0')
    print(f"用户 {current_user.nickname} 在其他界面加入房间0")
    room_users = socketio.server.manager.rooms.get('/', {}).get('0', set())
    
    # 更新在线用户列表
    if current_user.id not in online_user_list:
        online_user_list.append(current_user.id)
        online_user_sid_list.append([])  # 为新用户添加一个空的SID列表
        online_start_time_list.append(time.time())
    index_ = online_user_list.index(current_user.id)
    if request.sid not in online_user_sid_list[index_]:
        online_user_sid_list[index_].append(request.sid)  # 将当前SID添加到对应用户的SID列表
    
    tips_update_online_users(current_user.id)
    return {'success': True, 'message': '成功在其他界面加入房间0'}


# SocketIO匹配事件
@socketio.on('join_match_room')
@token_required_for_socketio
def handle_join_match_room(current_user, data):
    """加入匹配房间（房间0）"""
    join_room('0')
    print(f"用户 {current_user.nickname} 在匹配界面加入房间0")
    
    # 更新在线用户列表
    if current_user.id not in online_user_list:
        online_user_list.append(current_user.id)
        online_user_sid_list.append([])  # 为新用户添加一个空的SID列表
        online_start_time_list.append(time.time())
    index_ = online_user_list.index(current_user.id)
    if request.sid not in online_user_sid_list[index_]:
        online_user_sid_list[index_].append(request.sid)  # 将当前SID添加到对应用户的SID列表
    
    tips_update_online_users(current_user.id)
    return {'success': True, 'message': '成功在匹配界面加入房间0'}

@socketio.on('start_match')
@token_required_for_socketio
def handle_start_match(current_user, data):
    """处理开始匹配"""
    match_text = data.get('match_text')
    player_required = data.get('player_required', 2)
    
    if not match_text:
        return {'success': False, 'message': '匹配文本不能为空'}
    
    try:
        # 检查用户是否已经在匹配中
        existing_match = MatchUser.query.filter_by(
            user_id=current_user.id, 
            is_matched=False
        ).first()
        
        if existing_match:
            return {'success': False, 'message': '您已经在匹配中'}
        
        # 创建匹配记录
        match_user = MatchUser(
            user_id=current_user.id,
            match_text=match_text,
            player_required=player_required
        )
        
        db.session.add(match_user)
        db.session.commit()
        
        # 检查是否可以匹配
        check_and_create_match(match_text, player_required)
        
        return {'success': True, 'message': '开始匹配成功', 'match': match_user.to_dict()}
        
    except Exception as e:
        db.session.rollback()
        print(f"开始匹配错误: {str(e)}")
        return {'success': False, 'message': '开始匹配失败'}

@socketio.on('cancel_match')
@token_required_for_socketio
def handle_cancel_match(current_user, data):
    """处理取消匹配"""
    try:
        match_user = MatchUser.query.filter_by(
            user_id=current_user.id, 
            is_matched=False
        ).first()
        
        if not match_user:
            return {'success': False, 'message': '您当前没有在匹配中'}
        
        db.session.delete(match_user)
        db.session.commit()
        
        return {'success': True, 'message': '取消匹配成功'}
        
    except Exception as e:
        db.session.rollback()
        print(f"取消匹配错误: {str(e)}")
        return {'success': False, 'message': '取消匹配失败'}

# 房间列表更新相关的SocketIO事件
@socketio.on('join_room_list')
@token_required_for_socketio
def handle_join_room_list(current_user, data):
    """加入房间列表更新房间（房间0）"""
    join_room('0')
    print(f"用户 {current_user.nickname} 在房间列表更新界面加入房间0")
    
    # 更新在线用户列表
    if current_user.id not in online_user_list:
        online_user_list.append(current_user.id)
        online_user_sid_list.append([])  # 为新用户添加一个空的SID列表
        online_start_time_list.append(time.time())


    index_ = online_user_list.index(current_user.id)
    if request.sid not in online_user_sid_list[index_]:
        online_user_sid_list[index_].append(request.sid)  # 将当前SID添加到对应用户的SID列表
    tips_update_online_users(current_user.id)
    return {'success': True, 'message': '成功在房间列表更新界面加入房间0'}

@socketio.on('leave_room_list')
@token_required_for_socketio
def handle_leave_room_list(current_user, data):
    """离开房间列表更新房间（房间0）"""
    leave_room('0')
    print(f"用户 {current_user.nickname} 离开房间列表更新房间")
    
    return {'success': True, 'message': '离开房间列表更新房间成功'}

#admin删除头像，image+1
@app.route('/api/admin/delete_avatar/<int:user_id>', methods=['POST'])
@admin_required
def delete_avatar(current_user, user_id):
    pic_path = os.path.join('instance', 'pic', f'{user_id}.png')
    if os.path.exists(pic_path):
        os.remove(pic_path)
        user = User.query.get(user_id)
        if user:
            user.image = (user.image or 0) + 1
            db.session.commit()
    return jsonify({'message': '头像删除成功！'}), 200

# 返回len(online_user_list)作为在线人数
@app.route('/api/online_count', methods=['GET'])
def get_online_count():
    return jsonify({'online_count': len(online_user_list)}), 200

#返回is_active=true的房间总数：
@app.route('/api/active_rooms', methods=['GET'])
def get_active_room_count():
    active_room_count = Room.query.filter_by(is_active=True).count()
    return jsonify({'active_room_count': active_room_count}), 200

@app.route('/api/total_users', methods=['GET'])
def get_total_user_count():
    total_user_count = User.query.count()
    return jsonify({'total_user_count': total_user_count}), 200

@app.route('/api/total_rooms', methods=['GET'])
def get_total_room_count():
    total_room_count = Room.query.count()
    return jsonify({'total_room_count': total_room_count}), 200

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False)
