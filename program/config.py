import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    CORS_ORIGINS = "*"
    
    # 添加静态文件配置
    STATIC_FOLDER = '.'
    
    # SocketIO配置
    SOCKETIO_ASYNC_MODE = 'eventlet'
    SOCKETIO_PING_TIMEOUT = 60
    SOCKETIO_PING_INTERVAL = 25
    SOCKETIO_CORS_ALLOWED_ORIGINS = '*'