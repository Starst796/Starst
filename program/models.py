from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone, timedelta
import jwt
import time
from config import Config
from flask_socketio import SocketIO, join_room, leave_room, emit

socketio = None

def init_socketio(app_socketio):
    global socketio
    socketio = app_socketio

def send_chat_message_via_socketio(room_id, message_data):
    """通过SocketIO发送聊天消息"""
    if socketio:
        socketio.emit('new_chat_message', message_data, to=str(room_id))
        return True
    return False

db = SQLAlchemy()

# 东八区时区
east8 = timezone(timedelta(hours=8))

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    # 添加简介字段
    nickname = db.Column(db.String(80), nullable=True)
    profile = db.Column(db.Text, nullable=True)
    # 修改为东八区时间
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(east8))
    # 添加上次登录时间字段
    last_login_at = db.Column(db.DateTime, nullable=True)
    # 头像版本号，上传一次+1，默认0
    image = db.Column(db.Integer, default=0)
    #在线时间总和，单位秒
    total_online_time = db.Column(db.Integer, default=0)
    created_room_count = db.Column(db.Integer, default=0)  # 创建的房间数量
    joined_room_count = db.Column(db.Integer, default=0)  # 加入的房间数量

    rooms_created = db.relationship('Room', backref='creator', lazy=True, cascade='all, delete-orphan')
    room_memberships = db.relationship('RoomMember', backref='user', lazy=True, cascade='all, delete-orphan')
    chat_messages = db.relationship('RoomChat', backref='user_chat', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'nickname': self.nickname,
            'profile': self.profile,
            'image': self.image,
            'created_at': self.created_at.isoformat(),
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'total_online_time':self.total_online_time,
            'created_room_count': self.created_room_count,
            'joined_room_count': self.joined_room_count,
            'chat_count': len(self.chat_messages)
        }
    
    def generate_token(self):
        payload = {
            'user_id': self.id,
            'username': self.username,
            'exp': time.time() + 86400
        }
        return jwt.encode(payload, Config.SECRET_KEY, algorithm='HS256')

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    server_address = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # 修改为东八区时间
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(east8))
    is_active = db.Column(db.Boolean, default=True)
    max_players = db.Column(db.Integer, default=4)
    game_status = db.Column(db.String(20), default='waiting')  # waiting, playing, finished
    password = db.Column(db.String(100), nullable=True)  # 新增密码字段
    room_type = db.Column(db.String(20), default='public')  # public, private
    members = db.relationship('RoomMember', backref='room', lazy=True, cascade='all, delete-orphan')
    chat_messages = db.relationship('RoomChat', backref='room_chat', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'server_address': self.server_address,
            'description': self.description,
            'creator': self.creator.username,
            'creator_id': self.creator_id,
            'creator_nickname': self.creator.nickname,
            'created_at': self.created_at.isoformat(),
            'member_count': len(self.members),
            'max_players': self.max_players,
            'is_full': len(self.members) >= self.max_players,
            'game_status': self.game_status,
            'is_active': self.is_active,
            'has_password': self.password is not None and self.password != '',
            'room_type': self.room_type,
            'members': [member.user.to_dict() for member in self.members]
        }

class RoomMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    # 修改为东八区时间
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(east8))
    is_ready = db.Column(db.Boolean, default=False)  # 准备状态
    
    __table_args__ = (db.UniqueConstraint('user_id', 'room_id', name='unique_user_room'),)

class RoomChat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    nickname = db.Column(db.String(80), nullable=True)
    message_type = db.Column(db.String(20), default='user')
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(east8))
    
    def to_dict(self):
        # 处理可能的用户不存在情况
        username = "系统"
        nickname = "system"
        if self.user_id != 0:
            user = User.query.get(self.user_id)
            username = user.username if user else "未知用户"
            nickname = user.nickname if user else ""
        return {
            'id': self.id,
            'room_id': self.room_id,
            'user_id': self.user_id,
            'username': username,
            'nickname': nickname,
            'image' : user.image if self.user_id != 0 and user else 0,
            'message_type': self.message_type,
            'content': self.content,
            'created_at': self.created_at.isoformat(),
            'formatted_time': self.created_at.strftime('%H:%M:%S')
        }

class MatchUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    match_text = db.Column(db.String(200), nullable=False)
    player_required = db.Column(db.Integer, default=2)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(east8))
    is_matched = db.Column(db.Boolean, default=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=True)
    
    user = db.relationship('User', backref='match_users', lazy=True)
    room = db.relationship('Room', backref='match_users', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username,
            'match_text': self.match_text,
            'player_required': self.player_required,
            'created_at': self.created_at.isoformat(),
            'is_matched': self.is_matched,
            'room_id': self.room_id
        }