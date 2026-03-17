// global-bg.js
// 全局背景图片功能，所有页面可复用
(function(){
    if (window.__globalBgInjected) return; // 防止重复注入
    window.__globalBgInjected = true;
    function ready(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }
    ready(function() {
        // 创建背景容器
        let bgDiv = document.getElementById('global-bg-image');
        if (!bgDiv) {
            bgDiv = document.createElement('div');
            bgDiv.id = 'global-bg-image';
            document.body.appendChild(bgDiv);
        }

        // IndexedDB读取工具
        function loadBgImageFromDB(cb) {
            const request = window.indexedDB.open('starstCustomDB', 1);
            request.onupgradeneeded = function(event) {
                const db = event.target.result;
                if (!db.objectStoreNames.contains('customStore')) {
                    db.createObjectStore('customStore');
                }
            };
            request.onsuccess = function(event) {
                const db = event.target.result;
                const tx = db.transaction('customStore', 'readonly');
                const store = tx.objectStore('customStore');
                const req = store.get('globalBgImage');
                req.onsuccess = function() {
                    cb(req.result);
                    db.close();
                };
                req.onerror = function() {
                    cb(null);
                    db.close();
                };
            };
            request.onerror = function() { cb(null); };
        }

        // 读取本地存储的图片和透明度，支持IndexedDB
        function setBgFromStorage() {
            const imgData = localStorage.getItem('globalBgImage');
            const opacity = localStorage.getItem('globalBgOpacity') || '1';
            if (imgData === 'indexeddb') {
                // 从IndexedDB读取
                loadBgImageFromDB(function(dataUrl) {
                    if (dataUrl) {
                        bgDiv.style.backgroundImage = `url(${dataUrl})`;
                        bgDiv.style.display = '';
                    } else {
                        bgDiv.style.backgroundImage = '';
                        bgDiv.style.display = 'none';
                    }
                    bgDiv.style.opacity = opacity;
                });
            } else if (imgData) {
                bgDiv.style.backgroundImage = `url(${imgData})`;
                bgDiv.style.display = '';
                bgDiv.style.opacity = opacity;
            } else {
                bgDiv.style.backgroundImage = '';
                bgDiv.style.display = 'none';
                bgDiv.style.opacity = opacity;
            }
        }
        setBgFromStorage();
        window.addEventListener('storage', function(e){
            if (e.key === 'globalBgImage' || e.key === 'globalBgOpacity') setBgFromStorage();
        });
    });
})();
