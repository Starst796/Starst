# Starst 联机平台

## 项目简介

Starst 联机平台是一个基于 Flask + Flask-SocketIO 的在线实时互动平台，支持用户注册、登录、房间管理、实时聊天、排行榜、皮肤商城等功能。前端采用 HTML5、CSS3、JavaScript（jQuery & Socket.IO）实现，后端基于 Flask 框架，使用 Flask-SQLAlchemy 进行数据库管理，支持 WebSocket 实时通信。

## 主要功能
- 用户注册与登录
- 房间创建、加入、离开、解散
- 实时聊天室（基于 Socket.IO）
- 管理员后台
- 排行榜、皮肤商城、用户信息页
- 支持多端访问，响应式设计

## 技术栈
- Python 3
- Flask
- Flask-SocketIO
- Flask-SQLAlchemy
- Flask-CORS
- PyJWT
- eventlet
- HTML5/CSS3/JavaScript
- jQuery
- Socket.IO

## 目录结构
```
program/
  app.py                # 主后端应用入口
  config.py             # 配置文件
  models.py             # 数据库模型与SocketIO集成
  requirements.txt      # Python依赖
  wsgi.py               # WSGI启动入口
  static/               # 静态资源
    js/
      global-bg.js      # 全局背景脚本
  *.html                # 前端页面
  *.js                  # 前端脚本
  styles.css            # 样式表
  ...
```

## 快速开始
1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 启动服务：
   ```bash
   python app.py
   # 或
   python wsgi.py
   ```
3. 访问前端页面：
   在浏览器中打开 `index.html` 或通过服务器访问。

## 配置说明
- 配置项见 `config.py`，支持自定义数据库、密钥、CORS等。
- 默认数据库为 SQLite。
- 其他个性化配置文件说明：
   - `default.json`：全局主题与配色、背景图片等前端个性化设置，支持自定义主题色、背景透明度等。
   - `match.txt`：匹配相关的自定义选项或内容，可用于房间匹配、选项配置等。
   - `favicon.png`：网站/平台的网页图标（favicon），用于浏览器标签页显示。
   - `now_version.txt`：当前平台或系统的版本号标识，便于前端或用户识别当前部署版本。
   - 其他如 `emoji.txt`、`updates.txt` 等文件也可用于扩展表情、更新日志等个性化内容。

## 依赖列表
见 `requirements.txt`。

## 贡献与反馈
如有建议或问题，欢迎提交 issue 或 PR。

## 版权信息
本项目仅供学习与交流使用，禁止用于商业用途。
