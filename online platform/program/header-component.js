// header-component.js - 公共头部组件
class HeaderComponent extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.render();
    }
    
    render() {
        this.shadowRoot.innerHTML = `
            <style>
                :host {
                    display: block;
                }
                
                header {
                    background-color: var(--primary-color, #4a6fa5);
                    color: white;
                    padding: 1rem 0;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                    position: sticky;
                    top: 0;
                    z-index: 1000;
                }
                
                .header-content {
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 0 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                
                .logo {
                    font-size: 1.5rem;
                    font-weight: bold;
                    cursor: pointer;
                }
                
                .nav-menu {
                    display: flex;
                    gap: 20px;
                    margin-left: 30px;
                    flex: 1;
                }
                
                .nav-link {
                    color: white;
                    text-decoration: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    transition: all 0.3s ease;
                    font-weight: 500;
                }
                
                .nav-link:hover {
                    background-color: rgba(255, 255, 255, 0.1);
                }
                
                .nav-link.active {
                    background-color: rgba(255, 255, 255, 0.2);
                    font-weight: bold;
                }
                
                .auth-section {
                    display: flex;
                    align-items: center;
                    gap: 15px;
                }
                
                #user-info {
                    font-weight: 500;
                }
                
                .btn {
                    padding: 8px 16px;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-weight: 600;
                    transition: all 0.3s ease;
                }
                
                .btn-primary {
                    background-color: var(--accent-color, #ff7e5f);
                    color: white;
                }
                
                .btn-secondary {
                    background-color: var(--secondary-color, #6b8cbc);
                    color: white;
                }
                
                .hidden {
                    display: none !important;
                }
                
                @media (max-width: 768px) {
                    .header-content {
                        flex-direction: column;
                        gap: 10px;
                    }
                    
                    .nav-menu {
                        flex-wrap: wrap;
                        justify-content: center;
                        margin-left: 0;
                    }
                    
                    .auth-section {
                        flex-wrap: wrap;
                        justify-content: center;
                    }
                }
            </style>
            
            <header>
                <div class="header-content">
                    <div class="logo" id="home-logo">Starst联机系统</div>
                    <nav class="nav-menu">
                        <a href="room.html" class="nav-link" id="nav-room">房间</a>
                        <a href="match.html" class="nav-link" id="nav-match">匹配</a>
                        <a href="rank.html" class="nav-link" id="nav-rank">排行榜</a>
                        <a href="info.html" class="nav-link" id="nav-info">关于</a>
                    </nav>
                    <div class="auth-section">
                        <span id="user-info"></span>
                        <button id="my-btn" class="btn btn-secondary hidden">我的</button>
                        <button id="login-btn" class="btn btn-primary">登录/注册</button>
                        <button id="logout-btn" class="btn btn-secondary hidden">退出</button>
                        <button id="skin-btn" class="btn btn-secondary">外观</button>
                    </div>
                </div>
            </header>
        `;
        
        this.bindEvents();
    }
    
    
    bindEvents() {
        // 绑定logo点击事件
        const logo = this.shadowRoot.getElementById('home-logo');
        logo.addEventListener('click', () => {
            window.location.href = 'index.html';
        });
        
        // 绑定"我的"按钮事件
        const myBtn = this.shadowRoot.getElementById('my-btn');
        myBtn.addEventListener('click', () => {
            window.location.href = 'user';
        });
        
        // 绑定“更改外观”按钮事件
        const skinBtn = this.shadowRoot.getElementById('skin-btn');
        skinBtn.addEventListener('click', () => {
            window.location.href = 'skin';
        });

        // 绑定登录按钮事件
        const loginBtn = this.shadowRoot.getElementById('login-btn');
        loginBtn.addEventListener('click', () => {
            window.location.href = 'login';
        });
        
        // 绑定登出按钮事件
        const logoutBtn = this.shadowRoot.getElementById('logout-btn');
        logoutBtn.addEventListener('click', () => {
            // 清除本地存储
            localStorage.removeItem('token');
            localStorage.removeItem('currentUser');
            // 刷新页面
            window.location.reload();
        });
        
        // 设置当前页面导航高亮
        this.setActiveNav();
    }
    
    setActiveNav() {
        const currentPage = window.location.pathname.split('/').pop();
        const navLinks = this.shadowRoot.querySelectorAll('.nav-link');

        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href === currentPage) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }
    
    // 更新用户信息
    updateUserInfo(user) {
        const userInfo = this.shadowRoot.getElementById('user-info');
        const loginBtn = this.shadowRoot.getElementById('login-btn');
        const logoutBtn = this.shadowRoot.getElementById('logout-btn');
        const myBtn = this.shadowRoot.getElementById('my-btn');

        if (user) {
            userInfo.textContent = `欢迎，${user.nickname}`;
            loginBtn.classList.add('hidden');
            logoutBtn.classList.remove('hidden');
            myBtn.classList.remove('hidden');
        } else {
            userInfo.textContent = '';
            loginBtn.classList.remove('hidden');
            logoutBtn.classList.add('hidden');
            myBtn.classList.add('hidden');
        }
    }
}


let usingdark = false;
let colorlist = ['#4a6fa5', '#6b8cbc', '#ff7e5f', '#2c3e50', '#ffffff', '230,230,240'];
window.colorlist = colorlist;
const savedTheme = localStorage.getItem('theme');
const now_version = 'default';

function setLightTheme() {
  document.documentElement.style.setProperty('--primary-color', '#4a6fa5');
  document.documentElement.style.setProperty('--secondary-color', '#6b8cbc');
  document.documentElement.style.setProperty('--accent-color', '#ff7e5f');
  document.documentElement.style.setProperty('--background-color', '230,230,240');
  document.documentElement.style.setProperty('--front-color', '#2c3e50');
  document.documentElement.style.setProperty('--panel-color', '#ffffff');
  document.documentElement.style.setProperty('--my-chat-color', '#eaffff');
  document.documentElement.style.setProperty('--other-chat-color', '#ffffff');
  document.documentElement.style.setProperty('--system-chat-color', '#fff3cd');
  document.documentElement.style.setProperty('--shadow-color', '0,0,0');
  localStorage.setItem('customized', 'false');
  localStorage.setItem('theme', 'light');
  window.colorlist = ['#4a6fa5', '#6b8cbc', '#ff7e5f', '#2c3e50', '#ffffff', '230,230,240'];
  localStorage.setItem('savedColors', JSON.stringify(window.colorlist));
}

function setDarkTheme() {
  document.documentElement.style.setProperty('--primary-color', '#030303');
  document.documentElement.style.setProperty('--secondary-color', '#252f4d');
  document.documentElement.style.setProperty('--accent-color', '#5b799b');
  document.documentElement.style.setProperty('--background-color', '17,17,17');
  document.documentElement.style.setProperty('--front-color', '#ffffff');
  document.documentElement.style.setProperty('--panel-color', '#202020');
  document.documentElement.style.setProperty('--my-chat-color', '#1a2e4d');
  document.documentElement.style.setProperty('--other-chat-color', '#383838');
  document.documentElement.style.setProperty('--system-chat-color', '#474747');
  document.documentElement.style.setProperty('--shadow-color', '255,255,255');
  localStorage.setItem('customized', 'false')
  localStorage.setItem('theme', 'dark');
  window.colorlist = ['#030303', '#252f4d', '#5b799b', '#ffffff', '#202020', '17,17,17'];
  localStorage.setItem('savedColors', JSON.stringify(window.colorlist));
}

function saveBgImageToDB(dataUrl, cb) {
    openCustomDB(function(db) {
        const tx = db.transaction('customStore', 'readwrite');
        const store = tx.objectStore('customStore');
        const req = store.put(dataUrl, 'globalBgImage');
        req.onsuccess = function() { if (cb) cb(true); db.close(); };
        req.onerror = function() { if (cb) cb(false); db.close(); };
    });
}

function loadBgImageFromDB(cb) {
    openCustomDB(function(db) {
        const tx = db.transaction('customStore', 'readonly');
        const store = tx.objectStore('customStore');
        const req = store.get('globalBgImage');
        req.onsuccess = function() { cb(req.result); db.close(); };
        req.onerror = function() { cb(null); db.close(); };
    });
}

// ====== IndexedDB工具函数 ======
function openCustomDB(callback) {
    const request = indexedDB.open('starstCustomDB', 1);
    request.onupgradeneeded = function(event) {
        const db = event.target.result;
        if (!db.objectStoreNames.contains('customStore')) {
            db.createObjectStore('customStore');
        }
    };
    request.onsuccess = function(event) {
        callback(event.target.result);
    };
    request.onerror = function() {
        alert('无法打开自定义数据数据库');
    };
}

function saveCustomToDB(key, data, cb) {
    openCustomDB(function(db) {
        const tx = db.transaction('customStore', 'readwrite');
        const store = tx.objectStore('customStore');
        const req = store.put(data, key);
        req.onsuccess = function() {
            if (cb) cb(true);
            db.close();
        };
        req.onerror = function() {
            if (cb) cb(false);
            db.close();
        };
    });
}

function loadCustomFromDB(key, cb) {
    openCustomDB(function(db) {
        const tx = db.transaction('customStore', 'readonly');
        const store = tx.objectStore('customStore');
        const req = store.get(key);
        req.onsuccess = function() {
            cb(req.result);
            db.close();
        };
        req.onerror = function() {
            cb(null);
            db.close();
        };
    });
}

function rgbToHex(rgb) {
                            const arr = rgb.split(',').map(x=>parseInt(x));
                            if (arr.length!==3) return '#dcdcde';
                            return '#' + arr.map(x=>x.toString(16).padStart(2,'0')).join('');
                        }
async function setDefaultTheme() {
    localStorage.setItem('Version',now_version);
    fetch(now_version + '.json')
        .then(response => {
            if (!response.ok) throw new Error('无法获取主题配置文件');
            return response.json();
        })
        .then(data => {
            if (data.theme && data.colorlist) {
                if (data.theme === 'light') {
                    setLightTheme();
                    window.usingdark = false;
                } else if (data.theme === 'dark') {
                    setDarkTheme();
                    window.usingdark = true;
                }
                window.colorlist = data.colorlist;
                localStorage.setItem('savedColors', JSON.stringify(window.colorlist));
                localStorage.setItem('customized', 'true');
                document.documentElement.style.setProperty('--primary-color', data.colorlist[0]);
                document.documentElement.style.setProperty('--secondary-color', data.colorlist[1]);
                document.documentElement.style.setProperty('--accent-color', data.colorlist[2]);
                document.documentElement.style.setProperty('--front-color', data.colorlist[3]);
                document.documentElement.style.setProperty('--panel-color', data.colorlist[4]);
                document.documentElement.style.setProperty('--background-color', data.colorlist[5]);
                if (window.updatePickers) window.updatePickers();
                // 恢复背景图片
                if (data.globalBgImage) {
                    // 如果是dataURL，写入IndexedDB并设置localStorage为indexeddb
                    if (typeof data.globalBgImage === 'string' && data.globalBgImage.startsWith('data:image/')) {
                        saveBgImageToDB(data.globalBgImage, function(success) {
                            if (success) {
                                localStorage.setItem('globalBgImage', 'indexeddb');
                                window.dispatchEvent(new StorageEvent('storage', {key:'globalBgImage'}));
                            } else {
                                alert('导入的背景图片写入数据库失败');
                            }
                        });
                    } else {
                        // 兼容旧格式
                        localStorage.setItem('globalBgImage', data.globalBgImage);
                        window.dispatchEvent(new StorageEvent('storage', {key:'globalBgImage'}));
                    }
                }
                if (data.globalBgOpacity) {
                    localStorage.setItem('globalBgOpacity', data.globalBgOpacity);
                    window.dispatchEvent(new StorageEvent('storage', {key:'globalBgOpacity'}));
                    const range = document.getElementById('bg-opacity-range');
                    const value = document.getElementById('bg-opacity-value');
                    if (range && value) {
                        range.value = Math.round(Number(data.globalBgOpacity) * 100);
                        value.textContent = `${Math.round(Number(data.globalBgOpacity) * 100)}%`;
                    }
                }
            } else {
                alert('主题配置文件格式不正确');
            }
        })
        .catch(err => {
            alert('主题切换失败：' + err.message);
        });
}

function customizeColors(hex,name) {
  if (name === 'background'){
    const rgb = hexToRgba(hex, 0.5).match(/\d+/g).slice(0,3).join(',');
    document.documentElement.style.setProperty(`--background-color`, rgb);
    window.colorlist[5] = rgb;
  }else if (name === 'primary'){
    document.documentElement.style.setProperty(`--primary-color`, hex);
    window.colorlist[0] = hex;
  }else if (name === 'secondary'){
    document.documentElement.style.setProperty(`--secondary-color`, hex);
    window.colorlist[1] = hex;
  }else if (name === 'accent'){
    document.documentElement.style.setProperty(`--accent-color`, hex);
    window.colorlist[2] = hex;
  }else if (name === 'front'){
    document.documentElement.style.setProperty(`--front-color`, hex);
    window.colorlist[3] = hex;
  }else if (name === 'panel'){
    document.documentElement.style.setProperty(`--panel-color`, hex);
    window.colorlist[4] = hex;
  }
    localStorage.setItem('customized', 'true');
    localStorage.setItem('savedColors', JSON.stringify(window.colorlist));
}

// 注册自定义元素
customElements.define('header-component', HeaderComponent);

const savedCustomized = localStorage.getItem('customized');
const savedColors = JSON.parse(localStorage.getItem('savedColors'));

if (savedCustomized === 'false' || !savedCustomized) {
    if (savedTheme) {
        if (savedTheme === 'dark') {
            setDarkTheme();
            usingdark = true;
        } else if (savedTheme === 'light') {
            setLightTheme();
            usingdark = false;
        }
    } else {
        _version = localStorage.getItem('Version');
        if (_version !== now_version) {
            setDefaultTheme();
        }
    }
}

if (savedCustomized=='true' && savedTheme) {
    if (savedTheme === 'dark') {
        setDarkTheme();
        usingdark = true;
    } else if (savedTheme === 'light') {
        setLightTheme();
        usingdark = false;
    }
    if (savedColors && savedColors.length === 6) {
        window.colorlist = savedColors;
        localStorage.setItem('savedColors', JSON.stringify(window.colorlist));
        localStorage.setItem('customized', 'true');
        document.documentElement.style.setProperty('--primary-color', savedColors[0]);
        document.documentElement.style.setProperty('--secondary-color', savedColors[1]);
        document.documentElement.style.setProperty('--accent-color', savedColors[2]);
        document.documentElement.style.setProperty('--front-color', savedColors[3]);
        document.documentElement.style.setProperty('--panel-color', savedColors[4]);
        document.documentElement.style.setProperty('--background-color', savedColors[5]);
    }
}


function hexToRgba(hex, alpha = 1) {
  hex = hex.replace('#', '');
  if (hex.length === 3) {
    hex = hex.split('').map(x => x + x).join('');
  }
  const r = parseInt(hex.substring(0,2), 16);
  const g = parseInt(hex.substring(2,4), 16);
  const b = parseInt(hex.substring(4,6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}